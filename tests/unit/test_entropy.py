import numpy as np
import pytest
from wmstse.entropy.rolling import RollingEntropy

def test_rolling_entropy_fit_transform():
    T_out = 256
    # 2 windows, 3 subbands each
    # Window 1
    w1 = [
        np.random.randn(32),
        np.random.randn(64),
        np.random.randn(128)
    ]
    # Window 2
    w2 = [
        np.random.randn(32),
        np.random.randn(64),
        np.random.randn(128)
    ]
    
    coeffs_list = [w1, w2]
    
    re = RollingEntropy(K=8, T_out=T_out)
    
    # Must raise error if transform called before fit
    with pytest.raises(ValueError):
        re.transform(coeffs_list)
        
    re.fit(coeffs_list)
    assert len(re.bin_edges_per_level) == 3
    for edges in re.bin_edges_per_level:
        assert len(edges) == 9 # K+1
        assert edges[0] == -np.inf
        assert edges[-1] == np.inf
        
    features = re.transform(coeffs_list)
    assert features.shape == (2, 3, T_out)
    
    # Entropy should be non-negative
    assert np.all(features >= 0)

def test_rolling_entropy_constant_signal():
    """If the signal is constant, entropy should be zero."""
    # A single window with 1 subband
    w1 = [np.ones(64)]
    
    re = RollingEntropy(K=8, T_out=64)
    re.fit([w1])
    
    features = re.transform([w1])
    assert features.shape == (1, 1, 64)
    
    # Since it's all ones, the histogram puts all points in a single bin
    # -1 * log2(1) = 0
    np.testing.assert_allclose(features, 0.0, atol=1e-10)
