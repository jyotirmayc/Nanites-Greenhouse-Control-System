#!/usr/bin/env python3
import os
import json
import argparse
from pathlib import Path
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
import joblib
import yaml

# ---------------- Arguments ----------------
parser = argparse.ArgumentParser()
# Load config first to get the correct default path
CONFIG_PATH = Path("../config.yaml")
if not CONFIG_PATH.exists():
    # Try alternative paths for Docker deployment
    for alt_path in ["config.yaml", "../../AI/config.yaml", "/app/AI/config.yaml"]:
        if Path(alt_path).exists():
            CONFIG_PATH = Path(alt_path)
            break

print(f"Loading config from: {CONFIG_PATH}")
with CONFIG_PATH.open() as f:
    config = yaml.safe_load(f)

default_data_path = config.get('training', {}).get('data_path', "../data/synthetic.csv")
print(f"Default data path from config: {default_data_path}")

parser.add_argument("--data", default=os.getenv("DATA_PATH", default_data_path),
                    help="Path to input CSV with telemetry")
parser.add_argument("--outdir", default=os.getenv("MODEL_DIR", "../models"),
                    help="Directory to save trained model + metadata")
args = parser.parse_args()
os.makedirs(args.outdir, exist_ok=True)

print(f"Using data path: {args.data}")
print(f"Using output directory: {args.outdir}")

# ---------------- Load config (already loaded above) ----------------
# Config already loaded for default path

DATA_PATH = Path(args.data)
if not DATA_PATH.exists():
    raise FileNotFoundError(f"CSV data file not found: {DATA_PATH}")

# ---------------- Load data ----------------
df = pd.read_csv(DATA_PATH, parse_dates=['ts'])

# ---------------- Feature engineering ----------------
horizon = 36  # 6h ahead (36*10min)
df['soil_lag1'] = df['soil_theta'].shift(1)
df['soil_roll_6'] = df['soil_theta'].rolling(6).mean()
df['ppfd_roll_6'] = df['PPFD'].rolling(6).mean()
df['hour'] = df['ts'].dt.hour + df['ts'].dt.minute / 60.0
df['target_6h'] = df['soil_theta'].shift(-horizon)
df = df.dropna().reset_index(drop=True)

# ---------------- Prepare train/test ----------------
features = config.get('training', {}).get('irrigation_features',
          ['soil_lag1','soil_roll_6','ppfd_roll_6','T','RH','ext_T','hour'])
X, y = df[features], df['target_6h']
split = int(len(df) * 0.8)
X_train, X_test = X.iloc[:split], X.iloc[split:]
y_train, y_test = y.iloc[:split], y.iloc[split:]

# ---------------- Train model ----------------
rf = RandomForestRegressor(n_estimators=150, max_depth=8, random_state=42, n_jobs=-1)
rf.fit(X_train, y_train)

# ---------------- Evaluate ----------------
pred = rf.predict(X_test)
meta = {
    "mae_test": float(mean_absolute_error(y_test, pred)),
    "r2_test": float(r2_score(y_test, pred)),
    "rows_train": len(X_train)
}

# ---------------- Save model and metadata ----------------
model_path = Path(args.outdir) / "irrigation_rf.pkl"
meta_path = Path(args.outdir) / "irrigation_rf_meta.json"
joblib.dump(rf, model_path)
with meta_path.open("w") as f:
    json.dump(meta, f, indent=2)

print(f"Saved model → {model_path}")
print("Meta:", meta)
