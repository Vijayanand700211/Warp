import polars as pl
import numpy as np
import argparse
import sys
import os
import torch
from pathlib import Path

# Add src directory to Python path so 'import wmstse' works
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from wmstse.data.stream import build_flow_records, build_binned_stream, build_windows
from wmstse.data.splits import split_pa_in_session
from wmstse.features import WMSTSEFeatureExtractor
from wmstse.models.networks import WMSTSEModel
from wmstse.models.train import WMSTSETrainer
from wmstse.eval.metrics import compute_window_metrics, block_bootstrap_ci

def run_final_evaluation(dataset_dir: str, backbone: str):
    print(f"Loading CSVs from {dataset_dir} for final evaluation...")
    
    csv_files = sorted(list(Path(dataset_dir).glob("*.csv")))
    if not csv_files:
        print("No CSV files found.")
        return
        
    print(f"Found {len(csv_files)} files. Processing one by one to save memory...")
    
    all_X_train, all_y_train = [], []
    all_X_val, all_y_val = [], []
    all_X_test, all_y_test = [], []
    
    extractor = WMSTSEFeatureExtractor(T=256, wavelet="db4", level=4, K_bins=16)
    extractor_fitted = False
    
    for i, file_path in enumerate(csv_files):
        print(f"\n[{i+1}/{len(csv_files)}] Processing {file_path.name}...")
        try:
            df = pl.scan_csv(str(file_path), ignore_errors=True, infer_schema_length=10000)
            flows_df = build_flow_records(df).collect()
            
            if len(flows_df) == 0:
                print("  Skipping (no valid flows).")
                continue
                
            binned_df = build_binned_stream(flows_df.lazy(), bin_width_s=1.0).collect()
            windows_df, dense_binned = build_windows(binned_df, T=256, stride=8)
            
            if len(windows_df) == 0:
                print("  Skipping (no valid windows).")
                continue
                
            windows_df = split_pa_in_session(windows_df)
            
            train_w = windows_df.filter(pl.col("split") == "train")
            val_w = windows_df.filter(pl.col("split") == "val")
            test_w = windows_df.filter(pl.col("split") == "test")
            
            print(f"  Extracted Windows - Train: {len(train_w)}, Val: {len(val_w)}, Test: {len(test_w)}")
            
            if not extractor_fitted and len(train_w) > 0:
                print("  Fitting feature extractor on this file's train split...")
                extractor.fit(dense_binned, train_w)
                extractor_fitted = True
                
            if len(train_w) > 0 and extractor_fitted:
                all_X_train.append(extractor.transform(dense_binned, train_w))
                all_y_train.append(train_w["label"].to_numpy())
                
            if len(val_w) > 0 and extractor_fitted:
                all_X_val.append(extractor.transform(dense_binned, val_w))
                all_y_val.append(val_w["label"].to_numpy())
                
            if len(test_w) > 0 and extractor_fitted:
                all_X_test.append(extractor.transform(dense_binned, test_w))
                all_y_test.append(test_w["label"].to_numpy())
                
            import gc
            del df, flows_df, binned_df, windows_df, dense_binned, train_w, val_w, test_w
            gc.collect()
            
        except Exception as e:
            print(f"  Error processing {file_path.name}: {e}")
            
    if not all_X_train or not all_X_test:
        print("Not enough windows extracted to train and evaluate!")
        return
        
    print("\nConcatenating tensors...")
    X_train = np.concatenate(all_X_train, axis=0)
    y_train = np.concatenate(all_y_train, axis=0)
    X_val = np.concatenate(all_X_val, axis=0) if all_X_val else np.array([])
    y_val = np.concatenate(all_y_val, axis=0) if all_y_val else np.array([])
    X_test = np.concatenate(all_X_test, axis=0)
    y_test = np.concatenate(all_y_test, axis=0)
    
    print(f"Total Windows - Train: {len(X_train)}, Val: {len(X_val)}, Test: {len(X_test)}")
    
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
- **Dataset Dir:** {dataset_dir}
- **Window Size:** 256
- **Test Windows:** {len(X_test)}

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
    
    # Export ONNX model for Phase P8
    os.makedirs("artifacts/models", exist_ok=True)
    onnx_path = f"artifacts/models/{backbone}.onnx"
    dummy_input = torch.randn(1, 3, 5, 256).to(device)
    torch.onnx.export(
        model, 
        dummy_input, 
        onnx_path,
        export_params=True,
        opset_version=14,
        do_constant_folding=True,
        input_names=['input'],
        output_names=['output'],
        dynamic_axes={'input': {0: 'batch_size'}, 'output': {0: 'batch_size'}}
    )
    print(f"Model exported to ONNX format at {onnx_path}")
    
    # Save feature extractor state (e.g. dynamic entropy bucket edges)
    extractor_path = f"artifacts/models/{backbone}_extractor.pkl"
    extractor.save_state(extractor_path)
    print(f"Feature extractor state saved to {extractor_path}")

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
