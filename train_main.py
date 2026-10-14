import argparse
from pathlib import Path

from src.trainer import ModelTrainer


PROJECT_ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="Train the AgriAI crop disease model.")
    parser.add_argument("--train-dir", type=Path, default=PROJECT_ROOT / "data" / "train")
    parser.add_argument("--val-dir", type=Path, default=PROJECT_ROOT / "data" / "val")
    parser.add_argument(
        "--model-path",
        type=Path,
        default=PROJECT_ROOT / "crop_disease_model.pth",
    )
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--learning-rate", type=float, default=0.001)
    args = parser.parse_args()

    trainer = ModelTrainer(
        model_path=args.model_path,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
    )
    trainer.train(
        train_dir=args.train_dir,
        val_dir=args.val_dir,
        epochs=args.epochs,
    )


if __name__ == "__main__":
    main()