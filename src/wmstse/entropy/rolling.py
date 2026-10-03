import numpy as np
from typing import List, Optional

class RollingEntropy:
    def __init__(self, K: int = 16, T_out: int = 256):
        """
        Computes rolling Shannon entropy on wavelet sub-bands.
        
        Args:
            K: Number of bins for histogram discretization.
            T_out: Target output length (resampling to canonical T).
        """
        self.K = K
        self.T_out = T_out
        self.bin_edges_per_level: List[np.ndarray] = []
        
    def fit(self, coeffs_list: List[List[np.ndarray]]):
        """
        Fits global histogram bin edges for each sub-band based on training coefficients.
        
        Args:
            coeffs_list: A list (across windows) of lists (across sub-bands) of coefficient arrays.
        """
        if not coeffs_list:
            raise ValueError("No coefficients provided to fit.")
            
        n_levels = len(coeffs_list[0])
        self.bin_edges_per_level = []
        
        for j in range(n_levels):
            # Flatten all coefficients for this sub-band across all windows
            all_coeffs = np.concatenate([np.abs(window[j]) for window in coeffs_list])
            
            # Create K equal-width bins between min and max (or percentiles for robustness)
            c_min, c_max = np.min(all_coeffs), np.max(all_coeffs)
            if c_min == c_max:
                edges = np.linspace(c_min - 1, c_max + 1, self.K + 1)
            else:
                edges = np.linspace(c_min, c_max, self.K + 1)
                
            # To catch values slightly outside [min, max] during test time, expand ends to inf
            edges[0] = -np.inf
            edges[-1] = np.inf
            
            self.bin_edges_per_level.append(edges)

    def _rolling_entropy_1d(self, x: np.ndarray, w: int, edges: np.ndarray) -> np.ndarray:
        """Computes rolling Shannon entropy of a 1D array using given bin edges."""
        n = len(x)
        if n == 0:
            return np.array([])
            
        # Digitize x into bins (1-indexed)
        # digitize returns bins 1 to K for edges 0 to K
        binned_x = np.digitize(x, edges) - 1 
        
        # Clip to [0, K-1] just in case
        binned_x = np.clip(binned_x, 0, self.K - 1)
        
        entropy = np.zeros(n)
        
        # Compute sliding window entropy
        # A more optimal way exists, but for small w and n it's fine.
        for i in range(n):
            start = max(0, i - w + 1)
            end = i + 1
            window = binned_x[start:end]
            
            # Count frequencies
            counts = np.bincount(window, minlength=self.K)
            probs = counts / np.sum(counts)
            
            # Shannon entropy: -sum(p * log2(p))
            p = probs[probs > 0]
            ent = -np.sum(p * np.log2(p))
            entropy[i] = ent
            
        return entropy

    def transform_window(self, coeffs: List[np.ndarray]) -> np.ndarray:
        """
        Transforms a single window's sub-bands into rolling entropy features.
        
        Args:
            coeffs: List of sub-band coefficient arrays [cA_L, cD_L, cD_{L-1}, ..., cD_1]
            
        Returns:
            features: A 2D array of shape (n_levels, T_out).
        """
        if not self.bin_edges_per_level:
            raise ValueError("Must call fit() before transform().")
            
        n_levels = len(coeffs)
        if n_levels != len(self.bin_edges_per_level):
            raise ValueError(f"Expected {len(self.bin_edges_per_level)} sub-bands, got {n_levels}.")
            
        features = np.zeros((n_levels, self.T_out))
        
        for j, c in enumerate(coeffs):
            # w_j = max(8, round(span / 2^j))
            # Wait, standard DWT length halves each level. 
            # The exact level of each sub-band:
            # For 5 subbands (level 4), lengths are T/16, T/16, T/8, T/4, T/2.
            c_len = len(c)
            # We want rolling window size relative to current band length
            # Let's say w_j = max(8, len(c) // 4)
            w_j = max(8, c_len // 4)
            
            ent = self._rolling_entropy_1d(np.abs(c), w_j, self.bin_edges_per_level[j])
            
            # Resample to T_out
            if c_len != self.T_out:
                # Interpolate
                x_old = np.linspace(0, 1, c_len)
                x_new = np.linspace(0, 1, self.T_out)
                features[j] = np.interp(x_new, x_old, ent)
            else:
                features[j] = ent
                
        return features

    def transform(self, coeffs_list: List[List[np.ndarray]]) -> np.ndarray:
        """
        Transforms multiple windows into features.
        
        Args:
            coeffs_list: List of windows, where each window is a list of sub-bands.
            
        Returns:
            X: Array of shape (n_windows, n_levels, T_out)
        """
        if not coeffs_list:
            return np.array([])
            
        out = []
        for coeffs in coeffs_list:
            out.append(self.transform_window(coeffs))
            
        return np.stack(out, axis=0)
