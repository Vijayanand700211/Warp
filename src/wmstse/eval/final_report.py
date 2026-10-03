import polars as pl
import numpy as np
import argparse
import sys
import os
import torch
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from src.wmstse.data.stream import build_flow_records, build_binned_stream, build_windows
from src.wmstse.data.splits import split_pa_in_session
from src.wmstse.features import WMSTSEFeatureExtractor
from src.wmstse.models.networks import WMSTSEModel
from src.wmstse.models.train import WMSTSETrainer
from src.wmstse.eval.metrics import compute_window_metrics, block_bootstrap_ci

def run_final_evaluation(dataset_dir: str, backbone: str):
    print(f"Loading all CSVs from {dataset_dir} for final evaluation...")
    
    # Load all CSVs to get a broader distribution
    csv_files = list(Path(dataset_dir).glob("*.csv"))
    if not csv_files:
        print("No CSV files found.")
        return
        
    # Read and concatenate (using first 2 files for speed if many exist, or just 1 if specified)
    # Ideally, in a full run, we read all of them.
    df = pl.scan_csv(str(csv_files[0]), ignore_errors=True, infer_schema_length=10000)
    flows_df = build_flow_records(df).collect()
    
    print("Building stream and windows...")
    binned_df = build_binned_stream(flows_df.lazy(), bin_width_s=1.0).collect()
    windows_df, dense_binned = build_windows(binned_df, T=256, stride=8)
    windows_df = split_pa_in_session(windows_df)
    
    train_windows = windows_df.filter(pl.col("split") == "train")
    val_windows = windows_df.filter(pl.col("split") == "val")
    test_windows = windows_df.filter(pl.col("split") == "test")
    
    print(f"Windows - Train: {len(train_windows)}, Val: {len(val_windows)}, Test: {len(test_windows)}")
    
    if len(train_windows) == 0 or len(test_windows) == 0:
        print("Not enough windows to evaluate!")
        return

    print("Extracting features...")
    extractor = WMSTSEFeatureExtractor(T=256, wavelet="db4", level=4, K_bins=16)
    extractor.fit(dense_binned, train_windows)
    
    X_train = extractor.transform(dense_binned, train_windows)
    X_val = extractor.transform(dense_binned, val_windows)
    X_test = extractor.transform(dense_binned, test_windows)
    
    y_train = train_windows["label"].to_numpy()
    y_val = val_windows["label"].to_numpy()
    y_test = test_windows["label"].to_numpy()
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\nTraining {backbone} on {device}...")
    model = WMSTSEModel(backbone_id=backbone, input_size=64, pretrained=True)
    
    pos_weight = None
    if y_train.sum() > 0 and len(y_train) - y_train.sum() > 0:
        pos_weight = float((len(y_train) - y_train.sum()) / y_train.sum())
        
    trainer = WMSTSETrainer(model=model, device=device, learning_rate=1e-4, batch_size=32, epochs=30, patience=5, pos_weight=pos_weight)
    
    # Train
    trainer.train(X_train, y_train, X_val, y_val)
    
    # Evaluate
    print("\n--- Final Test Evaluation ---")
    
    test_loader = trainer.get_dataloader(X_test, y_test, shuffle=False)
    
    model.eval()
    all_preds, all_probs, all_targets = [], [], []
    with torch.no_grad():
        for batch_x, batch_y in test_loader:
            batch_x = batch_x.to(device)
            logits = model(batch_x)
            probs = torch.sigmoid(logits).cpu().numpy().flatten()
            preds = (probs >= 0.5).astype(int)
            
            all_probs.extend(probs)
            all_preds.extend(preds)
            all_targets.extend(batch_y.numpy())
            
    all_probs = np.array(all_probs)
    all_preds = np.array(all_preds)
    all_targets = np.array(all_targets)
    
    metrics = compute_window_metrics(all_targets, all_preds, all_probs)
    
    def macro_f1_metric(y_t, y_p):
        from sklearn.metrics import f1_score
        return f1_score(y_t, y_p, average='macro', zero_division=0)
        
    lower, upper = block_bootstrap_ci(all_targets, all_preds, macro_f1_metric)
    
    print(f"Test Macro-F1: {metrics.get('macro_f1', 0):.4f} (95% CI: {lower:.4f} - {upper:.4f})")
    print(f"Test PR-AUC (Attack): {metrics.get('pr_auc_attack', 0):.4f}")
    print(f"Test PR-AUC (Benign): {metrics.get('pr_auc_benign', 0):.4f}")
    
    # Generate Markdown Report
    report = f"""# Phase P7: Final Evaluation Report

## Configuration
- **Model Backbone:** {backbone}
- **Dataset:** {csv_files[0].name}
- **Window Size:** 256
- **Test Windows:** {len(test_windows)}

## Window-Level Metrics (P-A Split)
- **Macro-F1:** {metrics.get('macro_f1', 0):.4f} (95% CI: {lower:.4f} - {upper:.4f})
- **Attack Precision:** {metrics.get('attack_precision', 0):.4f}
- **Attack Recall:** {metrics.get('attack_recall', 0):.4f}
- **Benign Precision:** {metrics.get('benign_precision', 0):.4f}
- **Benign Recall:** {metrics.get('benign_recall', 0):.4f}
- **PR-AUC (Attack):** {metrics.get('pr_auc_attack', 0):.4f}
- **PR-AUC (Benign):** {metrics.get('pr_auc_benign', 0):.4f}
- **MCC:** {metrics.get('mcc', 0):.4f}

## Confusion Matrix
- True Negatives: {metrics.get('tn', 0)}
- False Positives: {metrics.get('fp', 0)}
- False Negatives: {metrics.get('fn', 0)}
- True Positives: {metrics.get('tp', 0)}
"""

    os.makedirs("reports", exist_ok=True)
    report_path = f"reports/P7_evaluation_{backbone}.md"
    with open(report_path, "w") as f:
        f.write(report)
        
    print(f"\nReport saved to {report_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=str, default="")
    parser.add_argument("--backbone", type=str, default="vit_tiny", choices=["floor", "mobilenetv2", "vit_tiny"])
    args = parser.parse_args()
    
    dataset_dir = args.dir
    if not dataset_dir:
        dataset_dir = "dataset/CIC-DDoS2019/01-12"
        if not Path(dataset_dir).exists():
            # Colab fallback
            dataset_dir = "."
            
    run_final_evaluation(dataset_dir, args.backbone)
