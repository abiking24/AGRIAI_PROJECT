import torch
import torch.nn as nn
from torchvision import models

class CropDiseaseModel(nn.Module):
    def __init__(self, num_classes=2):
        super(CropDiseaseModel, self).__init__()
        # Pre-trained ResNet18 ሞዴልን መጫን
        self.resnet = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
        
        # የመጨረሻውን layer ለኛ የክላስ ብዛት ማስተካከል
        in_features = self.resnet.fc.in_features
        self.resnet.fc = nn.Linear(in_features, num_classes)

    def forward(self, x):
        return self.resnet(x)