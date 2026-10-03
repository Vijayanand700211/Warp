import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import TensorDataset, DataLoader
import numpy as np
import time
from sklearn.metrics import f1_score, precision_score, recall_score, average_precision_score

from wmstse.models.networks import WMSTSEModel

def compute_class_weights(y: np.ndarray) -> torch.Tensor:
    """
    Computes class weights based on inverse class frequency.
    """
    y_int = y.astype(int)
    counts = np.bincount(y_int, minlength=2)
    # Avoid division by zero
    counts = np.maximum(counts, 1)
    total = len(y_int)
    weights = total / (2.0 * counts)
    return torch.tensor(weights, dtype=torch.float32)

class WMSTSETrainer:
    def __init__(self, 
                 model: nn.Module, 
                 device: torch.device,
                 learning_rate: float = 1e-3,
                 weight_decay: float = 1e-4,
                 batch_size: int = 32,
                 patience: int = 5,
                 epochs: int = 50,
                 pos_weight: float = None):
        self.model = model.to(device)
        self.device = device
        self.learning_rate = learning_rate
        self.weight_decay = weight_decay
        self.batch_size = batch_size
        self.patience = patience
        self.epochs = epochs
        
        self.optimizer = optim.AdamW(self.model.parameters(), lr=self.learning_rate, weight_decay=self.weight_decay)
        
        if pos_weight is not None:
            pos_weight_tensor = torch.tensor([pos_weight], dtype=torch.float32).to(self.device)
            self.criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight_tensor)
        else:
            self.criterion = nn.BCEWithLogitsLoss()
            
    def get_dataloader(self, X: np.ndarray, y: np.ndarray, shuffle: bool = False) -> DataLoader:
        tensor_x = torch.tensor(X, dtype=torch.float32)
        tensor_y = torch.tensor(y, dtype=torch.float32).unsqueeze(1)
        dataset = TensorDataset(tensor_x, tensor_y)
        return DataLoader(dataset, batch_size=self.batch_size, shuffle=shuffle, num_workers=0)

    def train_epoch(self, dataloader: DataLoader) -> float:
        self.model.train()
        total_loss = 0.0
        
        for batch_x, batch_y in dataloader:
            batch_x = batch_x.to(self.device)
            batch_y = batch_y.to(self.device)
            
            self.optimizer.zero_grad()
            logits = self.model(batch_x)
            loss = self.criterion(logits, batch_y)
            loss.backward()
            self.optimizer.step()
            
            total_loss += loss.item() * batch_x.size(0)
            
        return total_loss / len(dataloader.dataset)

    def evaluate(self, dataloader: DataLoader) -> dict:
        self.model.eval()
        total_loss = 0.0
        all_preds = []
        all_labels = []
        all_probs = []
        
        with torch.no_grad():
            for batch_x, batch_y in dataloader:
                batch_x = batch_x.to(self.device)
                batch_y = batch_y.to(self.device)
                
                logits = self.model(batch_x)
                loss = self.criterion(logits, batch_y)
                total_loss += loss.item() * batch_x.size(0)
                
                probs = torch.sigmoid(logits)
                preds = (probs >= 0.5).float()
                
                all_probs.extend(probs.cpu().numpy())
                all_preds.extend(preds.cpu().numpy())
                all_labels.extend(batch_y.cpu().numpy())
                
        all_probs = np.array(all_probs)
        all_preds = np.array(all_preds)
        all_labels = np.array(all_labels)
        
        # Calculate metrics
        avg_loss = total_loss / len(dataloader.dataset)
        macro_f1 = f1_score(all_labels, all_preds, average='macro', zero_division=0)
        precision = precision_score(all_labels, all_preds, zero_division=0)
        recall = recall_score(all_labels, all_preds, zero_division=0)
        pr_auc = average_precision_score(all_labels, all_probs)
        
        return {
            "loss": avg_loss,
            "macro_f1": macro_f1,
            "precision": precision,
            "recall": recall,
            "pr_auc": pr_auc
        }

    def train(self, X_train: np.ndarray, y_train: np.ndarray, X_val: np.ndarray, y_val: np.ndarray) -> dict:
        train_loader = self.get_dataloader(X_train, y_train, shuffle=True)
        val_loader = self.get_dataloader(X_val, y_val, shuffle=False)
        
        # Cosine learning rate scheduler
        self.scheduler = optim.lr_scheduler.CosineAnnealingLR(self.optimizer, T_max=self.epochs)
        
        best_val_f1 = -1.0
        best_state = None
        patience_counter = 0
        
        history = {"train_loss": [], "val_loss": [], "val_macro_f1": []}
        
        for epoch in range(self.epochs):
            t0 = time.time()
            train_loss = self.train_epoch(train_loader)
            val_metrics = self.evaluate(val_loader)
            
            self.scheduler.step()
            
            history["train_loss"].append(train_loss)
            history["val_loss"].append(val_metrics["loss"])
            history["val_macro_f1"].append(val_metrics["macro_f1"])
            
            print(f"Epoch {epoch+1}/{self.epochs} [{time.time()-t0:.1f}s]: "
                  f"Train Loss={train_loss:.4f}, Val Loss={val_metrics['loss']:.4f}, "
                  f"Val Macro-F1={val_metrics['macro_f1']:.4f}")
            
            if val_metrics["macro_f1"] > best_val_f1:
                best_val_f1 = val_metrics["macro_f1"]
                best_state = {k: v.cpu().clone() for k, v in self.model.state_dict().items()}
                patience_counter = 0
            else:
                patience_counter += 1
                
            if patience_counter >= self.patience:
                print(f"Early stopping at epoch {epoch+1} (No improvement for {self.patience} epochs)")
                break
                
        # Restore best model
        if best_state is not None:
            self.model.load_state_dict(best_state)
            
        print(f"Training completed. Best Val Macro-F1: {best_val_f1:.4f}")
        return history
