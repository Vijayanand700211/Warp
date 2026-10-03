import polars as pl
import numpy as np
import argparse
import sys
import os
import json
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
from sklearn.linear_model import LogisticRegression

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wmstse.data.stream import build_flow_records, build_binned_stream, build_windows
from wmstse.data.splits import split_pa_in_session
from wmstse.features import WMSTSEFeatureExtractor
from wmstse.eval.metrics import compute_window_metrics, block_bootstrap_ci

def run_baselines(csv_path: str):
    print(f"Loading {csv_path}...")
    df = pl.scan_csv(csv_path, ignore_errors=True, infer_schema_length=10000)
    flows_df = build_flow_records(df).collect()
    
    # We also need stream and windows
    binned_df = build_binned_stream(flows_df.lazy(), bin_width_s=1.0).collect()
    windows_df, dense_binned = build_windows(binned_df, T=256, stride=8)
    windows_df = split_pa_in_session(windows_df)
    
    train_windows = windows_df.filter(pl.col("split") == "train")
    val_windows = windows_df.filter(pl.col("split") == "val")
    test_windows = windows_df.filter(pl.col("split") == "test")
    
    print(f"Windows - Train: {len(train_windows)}, Val: {len(val_windows)}, Test: {len(test_windows)}")
    
    if len(train_windows) == 0 or len(test_windows) == 0:
        print("Not enough windows to evaluate baselines!")
        return

    # Baseline A0: Flow-level RF
    print("\n--- Running A0 (Per-Flow RF) ---")
    # To aggregate flow predictions to windows, we need to map flows to windows.
    # For simplicity in this script, we'll train on flows, predict on flows, 
    # and average probabilities for flows falling within a window's time span.
    # This is a bit complex for a quick script, let's just train an RF on flow features
    X_flows = flows_df.select(["duration_ms", "byte_count", "packet_count"]).to_numpy()
    y_flows = flows_df["label_binary"].to_numpy()
    
    rf = RandomForestClassifier(n_estimators=50, max_depth=10, random_state=42)
    rf.fit(X_flows, y_flows)
    
    def eval_a0_on_windows(win_df):
        preds = []
        for row in win_df.iter_rows(named=True):
            start = row["window_start_bin"]
            end = start + 256  # T=256 bins
            # Find flows in this time range (using bins as seconds since bin_width=1.0)
            in_window = flows_df.filter(
                (pl.col("event_ts") / 1e6 >= start) & 
                (pl.col("event_ts") / 1e6 < end)
            )
            if len(in_window) == 0:
                preds.append(0.0)
            else:
                X_w = in_window.select(["duration_ms", "byte_count", "packet_count"]).to_numpy()
                probs = rf.predict_proba(X_w)[:, 1]
                preds.append(float(np.mean(probs)))
        return np.array(preds)
    
    a0_val_probs = eval_a0_on_windows(val_windows)
    a0_test_probs = eval_a0_on_windows(test_windows)
    
    a0_val_preds = (a0_val_probs >= 0.5).astype(int)
    a0_test_preds = (a0_test_probs >= 0.5).astype(int)
    
    a0_metrics = compute_window_metrics(test_windows["label"].to_numpy(), a0_test_preds, a0_test_probs)
    print(f"A0 Test Macro-F1: {a0_metrics.get('macro_f1', 0):.4f}")
    
    # Baseline A3: Flattened W-MSTSE Tensor -> XGBoost
    print("\n--- Running A3 (Flattened Tensor -> XGBoost) ---")
    extractor = WMSTSEFeatureExtractor(T=256, wavelet="db4", level=4, K_bins=16)
    extractor.fit(dense_binned, train_windows)
    
    X_train_tensor = extractor.transform(dense_binned, train_windows)
    X_val_tensor = extractor.transform(dense_binned, val_windows)
    X_test_tensor = extractor.transform(dense_binned, test_windows)
    
    # Flatten: (N, C, B, T) -> (N, C*B*T)
    X_train_flat = X_train_tensor.reshape(X_train_tensor.shape[0], -1)
    X_val_flat = X_val_tensor.reshape(X_val_tensor.shape[0], -1)
    X_test_flat = X_test_tensor.reshape(X_test_tensor.shape[0], -1)
    
    y_train = train_windows["label"].to_numpy()
    y_test = test_windows["label"].to_numpy()
    
    try:
        xgb = XGBClassifier(n_estimators=100, max_depth=4, random_state=42)
        
        # XGBoost requires some positive samples
        if y_train.sum() == 0 or y_train.sum() == len(y_train):
            print("Warning: Train set has only 1 class. Training LogisticRegression as fallback.")
            xgb = LogisticRegression()
            
        xgb.fit(X_train_flat, y_train)
        
        a3_test_probs = xgb.predict_proba(X_test_flat)[:, 1] if hasattr(xgb, "predict_proba") else xgb.predict(X_test_flat)
        a3_test_preds = (a3_test_probs >= 0.5).astype(int)
        
        a3_metrics = compute_window_metrics(y_test, a3_test_preds, a3_test_probs)
        print(f"A3 Test Macro-F1: {a3_metrics.get('macro_f1', 0):.4f}")
    except Exception as e:
        print(f"A3 failed: {e}")
        a3_metrics = {}

    print("\n--- Generating P5 Baselines Report ---")
    report = f"""# Phase P5: Baselines Report

## Split Distribution
- **Train Windows:** {len(train_windows)}
- **Val Windows:** {len(val_windows)}
- **Test Windows:** {len(test_windows)}

## A0: Per-Flow RF Aggregated
- **Macro-F1:** {a0_metrics.get('macro_f1', 0):.4f}
- **Attack F1:** {a0_metrics.get('attack_f1', 0):.4f}
- **PR-AUC (Attack):** {a0_metrics.get('pr_auc_attack', 0):.4f}

## A3: Flattened W-MSTSE Tensor -> XGBoost
- **Macro-F1:** {a3_metrics.get('macro_f1', 0):.4f}
- **Attack F1:** {a3_metrics.get('attack_f1', 0):.4f}
- **PR-AUC (Attack):** {a3_metrics.get('pr_auc_attack', 0):.4f}
"""

    os.makedirs("reports", exist_ok=True)
    with open("reports/P5_baselines.md", "w") as f:
        f.write(report)
        
    print("Report saved to reports/P5_baselines.md")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=str, default="")
    args = parser.parse_args()
    
    csv_path = args.csv
    if not csv_path:
        d = Path("dataset/CIC-DDoS2019/01-12")
        if d.exists():
            csv_path = str(list(d.glob("*.csv"))[0])
        else:
            csv_path = "DrDoS_DNS.csv"
            
    run_baselines(csv_path)
