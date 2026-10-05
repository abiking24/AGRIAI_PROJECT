from pathlib import Path

import torch
from PIL import Image

from src.dataset import CLASS_NAMES, data_transforms
from src.model import CropDiseaseModel


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class DiseasePredictor:
    def __init__(self, model_path=None, num_classes=len(CLASS_NAMES)):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model_path = (
            Path(model_path) if model_path else PROJECT_ROOT / "crop_disease_model.pth"
        )
        if not self.model_path.is_absolute():
            self.model_path = PROJECT_ROOT / self.model_path

        self.classes = list(CLASS_NAMES)
        self.transform = data_transforms
        self.model = CropDiseaseModel(num_classes=num_classes).to(self.device)
        self.is_ready = False
        self.status_message = (
            f"የሞዴል ፋይል አልተገኘም፦ {self.model_path}. "
            "ሞዴሉን ለማሰልጠን `venv/bin/python train_main.py` ያሂዱ።"
        )

        if not self.model_path.is_file():
            return

        try:
            try:
                state_dict = torch.load(
                    self.model_path,
                    map_location=self.device,
                    weights_only=True,
                )
            except TypeError:
                state_dict = torch.load(self.model_path, map_location=self.device)
            self.model.load_state_dict(state_dict)
        except Exception as error:
            self.status_message = f"ሞዴሉን መጫን አልተቻለም፦ {error}"
            return

        self.model.eval()
        self.is_ready = True
        self.status_message = "Success"

    def predict(self, image: Image.Image):
        if not self.is_ready:
            return None, self.status_message

        image_tensor = self.transform(image.convert("RGB")).unsqueeze(0).to(self.device)
        with torch.inference_mode():
            outputs = self.model(image_tensor)
            predicted_index = outputs.argmax(dim=1).item()

        return self.classes[predicted_index], "Success"