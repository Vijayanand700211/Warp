import pytest
import numpy as np
import polars as pl
from wmstse.features import WMSTSEFeatureExtractor

def test_feature_extractor_pipeline():
    T = 256
    
    # Create a mock binned_df
    # We need n_flows, sum_bytes, sum_packets
    bins = np.arange(0, 1000, dtype=np.int64)
    binned_df = pl.DataFrame({
        "bin_id": bins,
        "n_flows": np.random.randint(0, 10, size=1000).astype(np.float64),
        "sum_bytes": np.random.randint(100, 10000, size=1000).astype(np.float64),
        "sum_packets": np.random.randint(10, 100, size=1000).astype(np.float64)
    })
    
    # Create windows_df
    windows_df = pl.DataFrame({
        "window_start_bin": [0, 256, 512],
        "split": ["train", "train", "val"]
    })
    
    train_windows = windows_df.filter(pl.col("split") == "train")
    
    extractor = WMSTSEFeatureExtractor(T=T, wavelet="db4", level=4, K_bins=16)
    
    # Must fail without fit
    with pytest.raises(ValueError):
        extractor.transform(binned_df, windows_df)
        
    # Fit on train
    extractor.fit(binned_df, train_windows)
    
    # Transform all
    X = extractor.transform(binned_df, windows_df)
    
    # N=3 windows, C=3 channels, B=5 subbands (level=4 -> 5), T=256
    assert X.shape == (3, 3, 5, 256)
    assert X.dtype == np.float32
    
    # Features should be non-negative (entropy is >= 0)
    assert np.all(X >= 0)
