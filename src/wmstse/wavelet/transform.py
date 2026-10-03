import pywt
import numpy as np
from typing import List, Literal

class WaveletTransform:
    def __init__(self, 
                 wavelet: str = "db4", 
                 level: int = 4, 
                 mode: str = "periodization",
                 kind: Literal["dwt", "swt"] = "dwt"):
        """
        Wrapper for Discrete and Stationary Wavelet Transforms.
        """
        self.wavelet = pywt.Wavelet(wavelet)
        self.level = level
        self.mode = mode
        self.kind = kind
        
        # We enforce a maximum of 6 levels for practical reasons (T usually 256)
        if not (3 <= self.level <= 6):
            raise ValueError("Level must be between 3 and 6 to yield 4-7 sub-bands.")

    def _check_constraints(self, T: int):
        if self.kind == "dwt":
            max_level = pywt.dwt_max_level(T, self.wavelet.dec_len)
            if self.level > max_level:
                raise ValueError(f"Requested level {self.level} exceeds dwt_max_level {max_level} for T={T}")
            if T % (2 ** self.level) != 0:
                raise ValueError(f"For DWT, T={T} must be divisible by 2^{self.level} ({2 ** self.level})")
        else:
            # SWT requires T to be divisible by 2^level, and no dec_len constraint
            if T % (2 ** self.level) != 0:
                raise ValueError(f"For SWT, T={T} must be divisible by 2^{self.level} ({2 ** self.level})")

    def transform(self, signal: np.ndarray) -> List[np.ndarray]:
        """
        Decomposes a 1D signal into sub-bands.
        Returns a list of arrays: [cA_L, cD_L, cD_{L-1}, ..., cD_1]
        """
        signal = np.asarray(signal)
        if signal.ndim != 1:
            raise ValueError("Signal must be 1D")
            
        T = len(signal)
        self._check_constraints(T)
        
        if self.kind == "dwt":
            # wavedec returns [cA_n, cD_n, cD_{n-1}, ..., cD_1]
            coeffs = pywt.wavedec(signal, self.wavelet, mode=self.mode, level=self.level)
        elif self.kind == "swt":
            # swt returns [(cA_1, cD_1), (cA_2, cD_2), ..., (cA_n, cD_n)]
            # We want to match the wavedec format: [cA_n, cD_n, cD_{n-1}, ..., cD_1]
            swt_coeffs = pywt.swt(signal, self.wavelet, level=self.level, start_level=0)
            
            # swt_coeffs[-1] is (cA_n, cD_n)
            coeffs = [swt_coeffs[-1][0]]  # cA_n
            for i in range(len(swt_coeffs)-1, -1, -1):
                coeffs.append(swt_coeffs[i][1]) # cD_n down to cD_1
        else:
            raise ValueError(f"Unknown kind: {self.kind}")
            
        return coeffs
        
    def inverse(self, coeffs: List[np.ndarray]) -> np.ndarray:
        """
        Reconstructs the signal from sub-bands.
        """
        if self.kind == "dwt":
            return pywt.waverec(coeffs, self.wavelet, mode=self.mode)
        elif self.kind == "swt":
            # Reconstruct the swt format from [cA_n, cD_n, cD_{n-1}, ..., cD_1]
            n = len(coeffs) - 1
            swt_coeffs = []
            
            # It's tricky to build the full swt tuple chain just from the details and the final approximation
            # since pywt.iswt expects [(cA_1, cD_1), ..., (cA_n, cD_n)] where ALL cA_i are provided.
            # Actually, pywt.iswt can reconstruct from just (cA_n, cD_n) recursively, or we must provide the intermediate cA.
            # DWT is the primary path, but we support iswt if needed by calculating the intermediate cA's.
            # For our pipeline, we only use forward transform for features, so inverse is mainly for testing.
            raise NotImplementedError("Inverse SWT not yet implemented.")
