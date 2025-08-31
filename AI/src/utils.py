# src/utils.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

import joblib
import pandas as pd
import yaml

PathLike = Union[str, Path]


def resolve_path(path: PathLike, base: Optional[Path] = None) -> Path:
    """Return an absolute Path for `path`.

    If `path` is absolute, returns Path(path).expanduser().resolve().
    Otherwise, resolves relative to `base` (defaults to this file's parent).
    """
    p = Path(path)
    if p.is_absolute():
        return p.expanduser().resolve()
    base = base or Path(__file__).parent
    return (base / p).expanduser().resolve()


def load_config(path: PathLike) -> Dict[str, Any]:
    """Load a YAML config file and return as dict."""
    p = resolve_path(path)
    with open(p, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg or {}


def read_csv(path: PathLike, **pd_kwargs) -> pd.DataFrame:
    """Read CSV into a pandas DataFrame. pd_kwargs forwarded to pandas.read_csv."""
    p = resolve_path(path)
    return pd.read_csv(p, **pd_kwargs)


def ensure_dir(path: PathLike) -> Path:
    """Ensure a directory exists and return its Path.

    If `path` points to an existing directory, return it. If it looks like a directory
    (no suffix) or is explicitly passed as a directory, mkdir parents as needed.
    If `path` looks like a file, ensure its parent directory exists and return the file Path.
    """
    p = Path(path)

    # If path already exists and is a directory -> return resolved dir
    if p.exists() and p.is_dir():
        return p.resolve()

    # If the path ends with a path separator or has no suffix, treat as directory
    if (str(path).endswith(("/", "\\")) or p.suffix == ""):
        p.mkdir(parents=True, exist_ok=True)
        return p.resolve()

    # Otherwise ensure parent exists (treat as file path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p.resolve()


def save_model(model: Any, path: PathLike) -> None:
    """Save model to disk using joblib; ensure parent dir exists."""
    p = resolve_path(path)
    ensure_dir(p.parent)
    joblib.dump(model, p)


def load_model(path: PathLike) -> Any:
    """Load a model from disk using joblib."""
    p = resolve_path(path)
    return joblib.load(p)


def setup_logger(name: str = "iot", level: int = logging.INFO, log_file: Optional[PathLike] = None) -> logging.Logger:
    """Create and return a logger configured with stream and optional file handlers."""
    logger = logging.getLogger(name)
    if logger.handlers:
        # already configured — just set the level and return
        logger.setLevel(level)
        return logger

    logger.setLevel(level)
    fmt = "%(asctime)s %(levelname)-8s %(name)s:%(lineno)d - %(message)s"
    formatter = logging.Formatter(fmt)

    sh = logging.StreamHandler()
    sh.setLevel(level)
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    if log_file is not None:
        lf = Path(log_file)
        ensure_dir(lf.parent)
        fh = logging.FileHandler(lf)
        fh.setLevel(level)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    return logger


__all__ = [
    "resolve_path",
    "load_config",
    "read_csv",
    "ensure_dir",
    "save_model",
    "load_model",
    "setup_logger",
]
