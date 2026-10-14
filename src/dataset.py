from pathlib import Path

from PIL import Image
from torch.utils.data import Dataset
from torchvision import transforms


CLASS_NAMES = ("diseased", "healthy")
IMAGE_SIZE = (224, 224)
data_transforms = transforms.Compose(
    [
        transforms.Resize(IMAGE_SIZE),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225],
        ),
    ]
)


class PlantDataset(Dataset):
    def __init__(self, root_dir, transform=None):
        self.root_dir = Path(root_dir)
        self.transform = transform or data_transforms
        self.classes = list(CLASS_NAMES)
        self.image_paths = []
        self.labels = []

        if not self.root_dir.is_dir():
            raise FileNotFoundError(f"Dataset directory not found: {self.root_dir}")

        actual_classes = sorted(
            path.name for path in self.root_dir.iterdir() if path.is_dir()
        )
        if actual_classes != sorted(CLASS_NAMES):
            raise ValueError(
                f"Expected class directories {sorted(CLASS_NAMES)} in {self.root_dir}; "
                f"found {actual_classes}"
            )

        for label, class_name in enumerate(self.classes):
            class_dir = self.root_dir / class_name
            for image_path in sorted(class_dir.iterdir()):
                if image_path.is_file() and image_path.suffix.lower() in {
                    ".png",
                    ".jpg",
                    ".jpeg",
                }:
                    self.image_paths.append(image_path)
                    self.labels.append(label)

    def __len__(self):
        return len(self.image_paths)

    def __getitem__(self, idx):
        with Image.open(self.image_paths[idx]) as source_image:
            image = source_image.convert("RGB")
        return self.transform(image), self.labels[idx]


CropDataset = PlantDataset


if __name__ == "__main__":
    dataset = PlantDataset(root_dir=Path(__file__).resolve().parent.parent / "data" / "train")
    print(f"Dataset successfully created! Total images found: {len(dataset)}")
