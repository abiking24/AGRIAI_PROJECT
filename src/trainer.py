from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader

from src.dataset import CLASS_NAMES, PlantDataset
from src.model import CropDiseaseModel


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ModelTrainer:
    def __init__(
        self,
        model_path=PROJECT_ROOT / "crop_disease_model.pth",
        batch_size=2,
        learning_rate=0.001,
        device=None,
    ):
        self.device = torch.device(
            device or ("cuda" if torch.cuda.is_available() else "cpu")
        )
        self.model_path = Path(model_path)
        if not self.model_path.is_absolute():
            self.model_path = PROJECT_ROOT / self.model_path
        self.batch_size = batch_size
        self.learning_rate = learning_rate
        self.model = CropDiseaseModel(num_classes=len(CLASS_NAMES)).to(self.device)
        self.criterion = nn.CrossEntropyLoss()
        self.optimizer = optim.Adam(self.model.parameters(), lr=self.learning_rate)

    def train(self, train_dir, val_dir=None, epochs=5):
        train_dataset = PlantDataset(train_dir)
        if len(train_dataset) == 0:
            raise ValueError(f"No training images found in {train_dir}")

        train_loader = DataLoader(
            train_dataset,
            batch_size=self.batch_size,
            shuffle=True,
        )
        val_loader = None
        if val_dir is not None:
            val_dataset = PlantDataset(val_dir)
            if val_dataset.classes != train_dataset.classes:
                raise ValueError("Training and validation class mappings do not match")
            if len(val_dataset) > 0:
                val_loader = DataLoader(
                    val_dataset,
                    batch_size=self.batch_size,
                    shuffle=False,
                )
            else:
                print(f"No validation images found in {val_dir}; skipping evaluation.")

        history = []
        for epoch in range(1, epochs + 1):
            self.model.train()
            total_loss = 0.0
            sample_count = 0

            for images, labels in train_loader:
                images = images.to(self.device)
                labels = labels.to(self.device)

                self.optimizer.zero_grad()
                outputs = self.model(images)
                loss = self.criterion(outputs, labels)
                loss.backward()
                self.optimizer.step()

                batch_size = labels.size(0)
                total_loss += loss.item() * batch_size
                sample_count += batch_size

            epoch_result = {
                "epoch": epoch,
                "train_loss": total_loss / sample_count,
                "validation": self.evaluate(val_loader) if val_loader is not None else None,
            }
            history.append(epoch_result)
            validation = epoch_result["validation"]
            if validation is not None:
                print(
                    f"Epoch {epoch}/{epochs}: train_loss={epoch_result['train_loss']:.4f}, "
                    f"val_loss={validation['loss']:.4f}, "
                    f"val_accuracy={validation['accuracy']:.2%}"
                )
            else:
                print(
                    f"Epoch {epoch}/{epochs}: "
                    f"train_loss={epoch_result['train_loss']:.4f}"
                )

        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(self.model.state_dict(), self.model_path)
        print(f"Model weights saved to {self.model_path}")
        return history

    def evaluate(self, data_loader):
        if data_loader is None:
            return None

        self.model.eval()
        total_loss = 0.0
        correct_predictions = 0
        sample_count = 0

        with torch.inference_mode():
            for images, labels in data_loader:
                images = images.to(self.device)
                labels = labels.to(self.device)
                outputs = self.model(images)
                loss = self.criterion(outputs, labels)

                batch_size = labels.size(0)
                total_loss += loss.item() * batch_size
                correct_predictions += (outputs.argmax(dim=1) == labels).sum().item()
                sample_count += batch_size

        if sample_count == 0:
            return None

        return {
            "loss": total_loss / sample_count,
            "accuracy": correct_predictions / sample_count,
        }