import polars as pl
import numpy as np
import argparse
import time
import sys
import os
import torch

# Add src to Python path so we can import wmstse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wmstse.data.stream import build_flow_records, build_binned_stream, build_windows
from wmstse.data.splits import split_pa_in_session
from wmstse.features import WMSTSEFeatureExtractor
from wmstse.models.networks import WMSTSEModel
from wmstse.models.train import WMSTSETrainer, compute_class_weights

def train_model(csv_path: str, backbone: str, epochs: int):
    print(f"Training {backbone} on {csv_path}...")
    
    t0 = time.time()
    
    # 1. Build stream
    df = pl.scan_csv(csv_path, ignore_errors=True, infer_schema_length=10000)
    flows_df = build_flow_records(df)
    binned_df = build_binned_stream(flows_df, bin_width_s=1.0).collect()
    
    # 2. Windowing
    windows_df, dense_binned = build_windows(binned_df, T=256, stride=8)
    
    # 3. Splits
    windows_df = split_pa_in_session(windows_df)
    
    train_windows = windows_df.filter(pl.col("split") == "train")
    val_windows = windows_df.filter(pl.col("split") == "val")
    test_windows = windows_df.filter(pl.col("split") == "test")
    
    print(f"Train windows: {len(train_windows)}")
    print(f"Val windows: {len(val_windows)}")
    print(f"Test windows: {len(test_windows)}")
    
    # 4. Feature Extraction
    print("Fitting feature extractor (Wavelet + Rolling Entropy) on train split...")
    extractor = WMSTSEFeatureExtractor(T=256, wavelet="db4", level=4, K_bins=16)
    extractor.fit(dense_binned, train_windows)
    
    print("Transforming train windows...")
    X_train = extractor.transform(dense_binned, train_windows)
    y_train = train_windows["label"].to_numpy()
    
    print("Transforming val windows...")
    X_val = extractor.transform(dense_binned, val_windows)
    y_val = val_windows["label"].to_numpy()
    
    print("Transforming test windows...")
    X_test = extractor.transform(dense_binned, test_windows)
    y_test = test_windows["label"].to_numpy()
    
    print(f"Feature tensor shape: {X_train.shape} (N, C, B, T)")
    
    # 5. Model Initialization
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    
    model = WMSTSEModel(backbone_id=backbone, input_size=64, pretrained=True)
    
    pos_weight = None
    if y_train.sum() > 0 and len(y_train) - y_train.sum() > 0:
        pos_weight = float((len(y_train) - y_train.sum()) / y_train.sum())
    
    trainer = WMSTSETrainer(
        model=model,
        device=device,
        learning_rate=1e-3 if backbone == "floor" else 1e-4,
        batch_size=32,
        epochs=epochs,
        patience=5,
        pos_weight=pos_weight
    )
    
    # 6. Training
    history = trainer.train(X_train, y_train, X_val, y_val)
    
    # 7. Final Evaluation on Test
    test_loader = trainer.get_dataloader(X_test, y_test, shuffle=False)
    test_metrics = trainer.evaluate(test_loader)
    
    print("\n--- Test Metrics ---")
    print(f"Loss: {test_metrics['loss']:.4f}")
    print(f"Macro-F1: {test_metrics['macro_f1']:.4f}")
    print(f"Precision: {test_metrics['precision']:.4f}")
    print(f"Recall: {test_metrics['recall']:.4f}")
    print(f"PR-AUC: {test_metrics['pr_auc']:.4f}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=str, default="")
    parser.add_argument("--backbone", type=str, default="floor", choices=["floor", "mobilenetv2", "vit_tiny"])
    parser.add_argument("--epochs", type=int, default=10)
    args = parser.parse_args()
    
    csv_path = args.csv
    if not csv_path:
        from pathlib import Path
        d = Path("dataset/CIC-DDoS2019/01-12")
        if d.exists():
            csv_path = str(list(d.glob("*.csv"))[0])
        else:
            # Fallback for colab root
            csv_path = "DrDoS_DNS.csv"
            
    train_model(csv_path, args.backbone, args.epochs)
