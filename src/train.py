from pathlib import Path

from src.trainer import ModelTrainer


def train():
    project_root = Path(__file__).resolve().parent.parent
    trainer = ModelTrainer()
    return trainer.train(
        train_dir=project_root / "data" / "train",
        val_dir=project_root / "data" / "val",
    )


if __name__ == "__main__":
    train()
