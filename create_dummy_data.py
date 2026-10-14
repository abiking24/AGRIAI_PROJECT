import os
from PIL import Image

def create_sample_images():
    paths = [
        "data/train/healthy/healthy_1.jpg",
        "data/train/healthy/healthy_2.jpg",
        "data/train/diseased/diseased_1.jpg",
        "data/train/diseased/diseased_2.jpg",
    ]
    
    for path in paths:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        img = Image.new('RGB', (224, 224), color='green' if 'healthy' in path else 'brown')
        img.save(path)
    
    print("Sample test images created successfully in data/train/!")

if __name__ == "__main__":
    create_sample_images()
