import torch
import torch.nn as nn
import torch.nn.functional as F

class WMSTSEInputMapper(nn.Module):
    def __init__(self, 
                 input_size: int = 64, 
                 mode: str = "nearest"):
        """
        Maps (N, C, B, T_out) tensor to (N, C, input_size, input_size) 
        for ImageNet-pretrained backbones.
        
        Args:
            input_size: The target spatial size (e.g., 64 for 64x64).
            mode: 'nearest' or 'bilinear'.
        """
        super().__init__()
        self.input_size = input_size
        self.mode = mode
        
        if mode not in ["nearest", "bilinear"]:
            raise ValueError(f"Unknown mode: {mode}")
            
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        x: shape (N, C, B, T_out)
        Returns: shape (N, C, input_size, input_size)
        """
        # F.interpolate expects (N, C, H, W)
        return F.interpolate(x, size=(self.input_size, self.input_size), mode=self.mode)
