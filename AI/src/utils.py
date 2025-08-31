import joblib
import os
import logging
from typing import Any

def save_model(model: Any, path: str):
    """Save model to path."""
    dir_path = os.path.dirname(path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)
    try:
        joblib.dump(model, path)
    except Exception as e:
        raise RuntimeError(f"Failed to save model to {path}: {e}")

def load_model(path: str) -> Any:
    """Load model from path."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Model file not found: {path}")
    try:
        return joblib.load(path)
    except Exception as e:
        raise RuntimeError(f"Failed to load model from {path}: {e}")

def setup_logger(log_path: str) -> logging.Logger:
    """Set up a dedicated file logger."""
    dir_path = os.path.dirname(log_path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

    logger = logging.getLogger("anomaly_logger")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        fh = logging.FileHandler(log_path, mode="a")
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    return logger
