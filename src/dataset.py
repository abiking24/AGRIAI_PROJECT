import os
from PIL import Image
import torch
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms

# የምስል መጠኖችን እና Color values ማስተካከያ (Normalization)
data_transforms = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])

class CropDataset(Dataset):
    def __init__(self, root_dir, transform=None):
        self.root_dir = root_dir
        self.transform = transform
        self.image_paths = []
        self.labels = []
        
        # ፎልደሮችን መፈለግ ( healthy = 0, diseased = 1 )
        if os.path.exists(root_dir):
            self.classes = sorted(os.listdir(root_dir))
            for label, class_name in enumerate(self.classes):
                class_dir = os.path.join(root_dir, class_name)
                if os.path.isdir(class_dir):
                    for img_name in os.listdir(class_dir):
                        if img_name.lower().endswith(('.png', '.jpg', '.jpeg')):
                            self.image_paths.append(os.path.join(class_dir, img_name))
                            self.labels.append(label)
        else:
            self.classes = []

    def __len__(self):
        return len(self.image_paths)

    def __getitem__(self, idx):
        img_path = self.image_paths[idx]
        image = Image.open(img_path).convert('RGB')
        label = self.labels[idx]

        if self.transform:
            image = self.transform(image)

        return image, label

if __name__ == "__main__":
    # Test dataset pipeline
    dataset = CropDataset(root_dir="data/train", transform=data_transforms)
    print(f"Dataset successfully created! Total images found: {len(dataset)}")
