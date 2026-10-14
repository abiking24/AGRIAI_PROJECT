import torch
from PIL import Image
from torchvision import transforms
from model import CropDiseaseModel

def predict():
    # 1. Label Mapping
    classes = ['Healthy', 'Diseased']

    # 2. Load Model & Weights
    model = CropDiseaseModel(num_classes=2)
    model.load_state_dict(torch.load("crop_disease_model.pth"))
    model.eval()

    # 3. Simulate an Image Tensor (3 channels, 224x224)
    dummy_image = torch.randn(1, 3, 224, 224)

    # 4. Predict
    with torch.no_grad():
        output = model(dummy_image)
        _, predicted_class = torch.max(output, 1)

    result = classes[predicted_class.item()]
    print(f"Prediction Result: Crop status is '{result}'")

if __name__ == "__main__":
    predict()
