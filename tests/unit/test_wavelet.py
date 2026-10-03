import numpy as np
import pytest
from wmstse.wavelet.transform import WaveletTransform

def test_wavelet_reconstruction():
    """Test perfect reconstruction for DWT."""
    T = 256
    signal = np.random.randn(T)
    
    transform = WaveletTransform(wavelet="db4", level=4, mode="periodization", kind="dwt")
    coeffs = transform.transform(signal)
    
    # 5 sub-bands for level 4
    assert len(coeffs) == 5
    
    reconstructed = transform.inverse(coeffs)
    np.testing.assert_allclose(signal, reconstructed, atol=1e-10)

def test_wavelet_energy_preservation():
    """
    Test Parseval's theorem: Energy of signal == Energy of coefficients
    under orthogonal wavelets (e.g. db4) and periodization.
    """
    T = 256
    signal = np.random.randn(T)
    energy_signal = np.sum(signal ** 2)
    
    transform = WaveletTransform(wavelet="db4", level=4, mode="periodization", kind="dwt")
    coeffs = transform.transform(signal)
    
    energy_coeffs = sum(np.sum(c ** 2) for c in coeffs)
    
    np.testing.assert_allclose(energy_signal, energy_coeffs, rtol=1e-10)

def test_wavelet_synthetic_signals():
    """Test that synthetic signals land in expected sub-bands."""
    T = 256
    t = np.arange(T)
    
    # High frequency sine wave (Nyquist/2)
    # This should have most energy in the first detail band cD_1 (the last element in coeffs list)
    freq = np.pi / 2 
    high_freq_signal = np.sin(freq * t)
    
    transform = WaveletTransform(wavelet="db4", level=4, mode="periodization", kind="dwt")
    coeffs = transform.transform(high_freq_signal)
    
    # Calculate energy per band
    energies = [np.sum(c ** 2) for c in coeffs]
    
    # cD_1 is at index 4 (last)
    assert energies[-1] > np.sum(energies[:-1]), "High freq energy should be mostly in cD_1"

def test_wavelet_invalid_constraints():
    """Test assertions for max levels and divisibility."""
    with pytest.raises(ValueError):
        # Level too high for T=32 with db4
        WaveletTransform(wavelet="db4", level=5).transform(np.zeros(32))
        
    with pytest.raises(ValueError):
        # T not divisible by 2^4
        WaveletTransform(wavelet="db4", level=4).transform(np.zeros(255))
