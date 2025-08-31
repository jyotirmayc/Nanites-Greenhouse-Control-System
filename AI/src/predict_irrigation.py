#!/usr/bin/env python3
import joblib
import pandas as pd
import yaml
from pathlib import Path
import sys

# --- Load config ---
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
if not CONFIG_PATH.exists():
    sys.exit(f"Config file not found: {CONFIG_PATH}")

with CONFIG_PATH.open("r") as f:
    config = yaml.safe_load(f) or {}

# --- Load irrigation model ---
irr_model_path = Path(config.get('model', {}).get('irrigation', {}).get('path', ''))
if not irr_model_path.is_absolute():
    irr_model_path = CONFIG_PATH.parent / irr_model_path

if not irr_model_path.exists():
    sys.exit(f"Irrigation model file not found: {irr_model_path}")

irr_model = joblib.load(irr_model_path)

# --- Load irrigation features from config ---
irr_features = config.get('training', {}).get('irrigation_features', 
                ['soil_lag1','soil_roll_6','ppfd_roll_6','T','RH','ext_T','hour'])

# --- Example input ---
sample_values = [[0.32, 0.33, 800, 26, 65, 30, 14.5]]  # match feature order
if len(sample_values[0]) != len(irr_features):
    sys.exit("Sample input length does not match irrigation features")

sample = pd.DataFrame(sample_values, columns=irr_features)

# --- Predict ---
try:
    pred = irr_model.predict(sample)
    print("Predicted soil moisture in 6h:", pred)
except Exception as e:
    print(f"Irrigation prediction failed: {e}")
