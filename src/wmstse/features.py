import numpy as np
import polars as pl
from typing import List, Dict, Tuple
from wmstse.wavelet.transform import WaveletTransform
from wmstse.entropy.rolling import RollingEntropy

class WMSTSEFeatureExtractor:
    def __init__(self, 
                 T: int = 256,
                 wavelet: str = "db4",
                 level: int = 4,
                 mode: str = "periodization",
                 kind: str = "dwt",
                 K_bins: int = 16):
        """
        Extracts WMSTSE features from binned windows.
        Outputs a tensor of shape (N, C, B, T).
        Where N = num windows, C = channels (3), B = sub-bands, T = sequence length.
        """
        self.T = T
        self.channels = ["n_flows", "sum_bytes", "sum_packets"]
        self.C = len(self.channels)
        
        self.wavelet_transform = WaveletTransform(wavelet=wavelet, level=level, mode=mode, kind=kind)
        # We need an independent entropy extractor for each channel (and each channel has multiple sub-bands)
        self.entropy_extractors = [RollingEntropy(K=K_bins, T_out=T) for _ in range(self.C)]
        self.B = level + 1 # Number of sub-bands
        
    def _extract_windows_from_df(self, binned_df: pl.DataFrame, windows_df: pl.DataFrame) -> List[np.ndarray]:
        """
        Extracts raw (C, T) windows from the DataFrames.
        Returns a list of arrays of shape (C, T).
        """
        windows = []
        
        # Sort just in case
        binned_df = binned_df.sort("bin_id")
        
        for row in windows_df.iter_rows(named=True):
            start_bin = row["window_start_bin"]
            end_bin = start_bin + self.T
            
            # Extract T bins
            win_data = binned_df.filter(
                (pl.col("bin_id") >= start_bin) & 
                (pl.col("bin_id") < end_bin)
            )
            
            # In a perfectly binned stream, win_data should have exactly T rows.
            # However, if there are missing bins (which shouldn't happen if we padded), 
            # we must ensure we align them.
            # Assuming build_binned_stream already padded with 0s.
            if len(win_data) != self.T:
                # Pad to T
                full_bins = pl.DataFrame({"bin_id": np.arange(start_bin, end_bin, dtype=np.int64)})
                win_data = full_bins.join(win_data, on="bin_id", how="left").fill_null(0)
                
            # Extract channels
            c_data = []
            for col in self.channels:
                c_data.append(win_data[col].to_numpy())
                
            windows.append(np.stack(c_data, axis=0)) # Shape (C, T)
            
        return windows

    def fit(self, binned_train_df: pl.DataFrame, windows_train_df: pl.DataFrame):
        """
        Fits the histogram bins globally on the training split.
        """
        train_windows = self._extract_windows_from_df(binned_train_df, windows_train_df)
        if not train_windows:
            raise ValueError("No training windows available to fit.")
            
        # train_windows is a list of (C, T) arrays
        # We need to decompose each channel and fit the entropy extractors
        for c_idx in range(self.C):
            c_coeffs_list = []
            for win in train_windows:
                signal = win[c_idx]
                coeffs = self.wavelet_transform.transform(signal)
                c_coeffs_list.append(coeffs)
                
            self.entropy_extractors[c_idx].fit(c_coeffs_list)

    def transform(self, binned_df: pl.DataFrame, windows_df: pl.DataFrame) -> np.ndarray:
        """
        Transforms windows into the final feature tensor (N, C, B, T).
        """
        if not self.entropy_extractors[0].bin_edges_per_level:
            raise ValueError("Must call fit() with training data before transform().")
            
        windows = self._extract_windows_from_df(binned_df, windows_df)
        N = len(windows)
        
        if N == 0:
            return np.empty((0, self.C, self.B, self.T))
            
        X = np.zeros((N, self.C, self.B, self.T), dtype=np.float32)
        
        for i, win in enumerate(windows):
            for c_idx in range(self.C):
                signal = win[c_idx]
                coeffs = self.wavelet_transform.transform(signal)
                features = self.entropy_extractors[c_idx].transform_window(coeffs) # Shape (B, T)
                X[i, c_idx] = features
                
        return X
