#!/usr/bin/env python3
import joblib
import pandas as pd
import yaml
from pathlib import Path
import sys

# --- Load config ---
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR.parent / "config.yaml"

if not CONFIG_PATH.exists():
    sys.exit(f"Config file not found: {CONFIG_PATH}")

with CONFIG_PATH.open("r") as f:
    config = yaml.safe_load(f) or {}

# --- Load model ---
model_path = Path(config.get('model', {}).get('irrigation', {}).get('path', ''))
if not model_path.is_absolute():
    model_path = SCRIPT_DIR.parent / model_path

if not model_path.exists():
    sys.exit(f"Model file not found: {model_path}")

model = joblib.load(model_path)

# --- Prepare input features ---
anom_features = config.get('training', {}).get('irrigation_features', ['T','RH','soil_theta','PPFD','CO2'])
# Example sample (replace with real telemetry values)
sample_values = [[26, 65, 0.32, 800, 420]]  # match feature order
if len(sample_values[0]) != len(anom_features):
    sys.exit("Sample input length does not match expected features")

sample = pd.DataFrame(sample_values, columns=anom_features)

# --- Predict ---
try:
    pred = model.predict(sample)
    if pred[0] == -1:
        print("Anomaly detected.")
    else:
        print("Normal reading.")
except Exception as e:
    print(f"Prediction failed: {e}")
