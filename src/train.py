import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from model import CropDiseaseCNN
from dataset import CropDataset, data_transforms

def train():
    # 1. Dataset እና DataLoader ማዘጋጀት
    train_dataset = CropDataset(root_dir="data/train", transform=data_transforms)
    train_loader = DataLoader(train_dataset, batch_size=2, shuffle=True)

    if len(train_dataset) == 0:
        print("No training images found! Please add images to data/train/")
        return

    # 2. Model, Loss Function እና Optimizer ማዘጋጀት
    model = CropDiseaseCNN(num_classes=2)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)

    print(f"Starting training on {len(train_dataset)} images...")

    # 3. Training Loop
    model.train()
    for epoch in range(1, 6):
        running_loss = 0.0
        for images, labels in train_loader:
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            running_loss += loss.item()

        epoch_loss = running_loss / len(train_loader)
        print(f"Epoch [{epoch}/5] - Loss: {epoch_loss:.4f}")

    # 4. ያሰለጠናቸውን Weights ማስቀመጥ
    torch.save(model.state_dict(), "crop_disease_model.pth")
    print("Training finished successfully! Model updated and saved as 'crop_disease_model.pth'.")

if __name__ == "__main__":
    train()
