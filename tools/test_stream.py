import os
import sys
from pathlib import Path
import polars as pl

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from wmstse.data.stream import build_flow_records, build_binned_stream, build_windows

def main():
    # Find a test file
    d = Path("dataset/CIC-DDoS2019/01-12")
    if not d.exists():
        print("Dataset not found locally, skipping test.")
        return
        
    test_file = list(d.glob("*.csv"))[0]
    print(f"Testing stream parser on {test_file.name}...")
    
    lf = pl.scan_csv(test_file, ignore_errors=True, infer_schema_length=10000)
    
    # 1. Flow Records
    flows_lf = build_flow_records(lf)
    flows = flows_lf.head(100).collect()
    print("Flow Records Schema:", flows.schema)
    print(f"Sample flows:\n{flows.head(2)}")
    
    # 2. Binned Stream
    binned_lf = build_binned_stream(flows_lf, bin_width_s=1.0)
    binned = binned_lf.head(100).collect()
    print("\nBinned Stream Schema:", binned.schema)
    print(f"Sample bins:\n{binned.head(2)}")
    
    # 3. Windowing
    # collect all to do windowing (for a single file this is fine)
    full_binned = binned_lf.collect()
    print(f"\nExtracted {len(full_binned)} active bins. Running windowing (T=256)...")
    windows, dense_bins = build_windows(full_binned, T=256, stride=8)
    print(f"Generated {len(windows)} windows from {len(dense_bins)} total spanned bins.")
    if len(windows) > 0:
        print(windows.head())

if __name__ == "__main__":
    main()
