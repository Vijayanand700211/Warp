import polars as pl
import numpy as np
import argparse
import time
import sys
import os

# Add src to Python path so we can import wmstse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wmstse.data.stream import build_flow_records, build_binned_stream, build_windows
from wmstse.data.splits import split_pa_in_session
from wmstse.features import WMSTSEFeatureExtractor

def test_features(csv_path: str):
    print(f"Testing feature extraction on {csv_path}...")
    
    t0 = time.time()
    
    # 1. Build stream
    df = pl.scan_csv(csv_path, ignore_errors=True, infer_schema_length=10000)
    flows_df = build_flow_records(df)
    binned_df = build_binned_stream(flows_df, bin_width_s=1.0).collect()
    
    # 2. Windowing
    windows_df = build_windows(binned_df, T=256, stride=8)
    
    # 3. Splits
    windows_df = split_pa_in_session(windows_df)
    
    train_windows = windows_df.filter(pl.col("split") == "train")
    
    # 4. Feature Extraction
    print("Fitting feature extractor (Wavelet + Rolling Entropy) on train split...")
    extractor = WMSTSEFeatureExtractor(T=256, wavelet="db4", level=4, K_bins=16)
    extractor.fit(binned_df, train_windows)
    
    print("Transforming all windows...")
    X = extractor.transform(binned_df, windows_df)
    
    t1 = time.time()
    
    print(f"Feature tensor shape: {X.shape} (N, C, B, T)")
    print(f"Feature tensor dtype: {X.dtype}")
    print(f"Extracted in {t1 - t0:.2f} seconds.")
    
    print("\nSummary statistics of features:")
    print(f"Min: {X.min():.4f}")
    print(f"Max: {X.max():.4f}")
    print(f"Mean: {X.mean():.4f}")
    print(f"Std: {X.std():.4f}")
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=str, default="")
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
            
    test_features(csv_path)
