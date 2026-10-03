import pytest
import torch
from wmstse.models.networks import WMSTSEModel

def test_model_floor():
    model = WMSTSEModel(backbone_id="floor", input_size=64, num_classes=1)
    # Batch = 2, C=3, B=5, T_out=64
    x = torch.randn(2, 3, 5, 64)
    logits = model(x)
    assert logits.shape == (2, 1)

def test_model_mobilenetv2():
    # Set pretrained=False to avoid downloading weights during fast unit tests
    model = WMSTSEModel(backbone_id="mobilenetv2", input_size=64, num_classes=1, pretrained=False)
    x = torch.randn(2, 3, 5, 64)
    logits = model(x)
    assert logits.shape == (2, 1)

def test_model_vit_tiny():
    # Set pretrained=False for unit testing
    model = WMSTSEModel(backbone_id="vit_tiny", input_size=64, num_classes=1, pretrained=False)
    x = torch.randn(2, 3, 5, 64)
    logits = model(x)
    assert logits.shape == (2, 1)

def test_input_mapping_nearest():
    model = WMSTSEModel(backbone_id="floor", input_size=64, mapping_mode="nearest")
    x = torch.randn(2, 3, 5, 64)
    # The intermediate mapped tensor shape can be verified by hooking or directly calling mapper
    mapped_x = model.mapper(x)
    assert mapped_x.shape == (2, 3, 64, 64)

def test_input_mapping_bilinear():
    model = WMSTSEModel(backbone_id="floor", input_size=64, mapping_mode="bilinear")
    x = torch.randn(2, 3, 5, 64)
    mapped_x = model.mapper(x)
    assert mapped_x.shape == (2, 3, 64, 64)
