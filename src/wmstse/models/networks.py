import torch
import torch.nn as nn
import timm

from wmstse.models.input_mapping import WMSTSEInputMapper

class CNNFloor(nn.Module):
    def __init__(self, in_channels: int = 3, num_classes: int = 1):
        """
        Tiny custom CNN from scratch (sanity floor).
        Input is expected to be (N, 3, 64, 64).
        """
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(in_channels, 16, kernel_size=3, padding=1),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2), # 32x32
            
            nn.Conv2d(16, 32, kernel_size=3, padding=1),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2), # 16x16
            
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d((1, 1))
        )
        self.classifier = nn.Linear(64, num_classes)
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        x = torch.flatten(x, 1)
        return self.classifier(x)

class WMSTSEModel(nn.Module):
    def __init__(self, 
                 backbone_id: str = "floor", 
                 input_size: int = 64, 
                 mapping_mode: str = "nearest",
                 num_classes: int = 1,
                 pretrained: bool = True):
        """
        Main model wrapper for WMSTSE.
        
        Args:
            backbone_id: 'floor', 'mobilenetv2', or 'vit_tiny'.
            input_size: Size for the square input representation (e.g. 64).
            mapping_mode: Interpolation mode ('nearest' or 'bilinear').
            num_classes: Number of output classes (1 for binary classification).
        """
        super().__init__()
        self.mapper = WMSTSEInputMapper(input_size=input_size, mode=mapping_mode)
        
        if backbone_id == "floor":
            self.backbone = CNNFloor(in_channels=3, num_classes=num_classes)
        elif backbone_id == "mobilenetv2":
            # Using timm for mobilenetv2 
            self.backbone = timm.create_model('mobilenetv2_100', pretrained=pretrained, num_classes=num_classes)
        elif backbone_id == "vit_tiny":
            # timm vit_tiny_patch16_224 is a common tiny vit.
            # But we are passing 64x64. ViT patch embedding needs to match image size.
            # timm supports dynamic img_size for many ViTs.
            self.backbone = timm.create_model('vit_tiny_patch16_224', pretrained=pretrained, num_classes=num_classes, img_size=input_size)
        else:
            raise ValueError(f"Unknown backbone_id: {backbone_id}")
            
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        x: (N, C, B, T_out) raw feature tensor.
        Returns: (N, num_classes) logits.
        """
        x = self.mapper(x)
        return self.backbone(x)
