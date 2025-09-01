# src/train_anomaly.py
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List
import yaml

import pandas as pd
from sklearn.ensemble import IsolationForest

from utils import ensure_dir, save_model, resolve_path


def parse_args():
    # Load config to get default data path
    config_path = Path("../config.yaml")
    if not config_path.exists():
        config_path = Path("config.yaml") if Path("config.yaml").exists() else Path("../config.yaml")
    
    with config_path.open() as f:
        config = yaml.safe_load(f)
    
    default_data_path = config.get('training', {}).get('data_path', '../data/synthetic.csv')
    
    p = argparse.ArgumentParser(description='Train IsolationForest anomaly detector')
    p.add_argument('--data', type=str, default=default_data_path, help='Path to telemetry CSV')
    p.add_argument('--outdir', type=str, default='../models', help='Directory to write model and metadata')
    p.add_argument('--features', type=str, default='T,RH,soil_theta,PPFD,CO2',
                   help='Comma-separated list of feature column names to train on')
    p.add_argument('--contamination', type=float, default=0.01)
    p.add_argument('--random-state', type=int, default=42)
    return p.parse_args()


def main():
    args = parse_args()
    data_path = resolve_path(args.data)
    outdir = resolve_path(args.outdir)
    ensure_dir(outdir)

    df = pd.read_csv(data_path)

    features: List[str] = [f.strip() for f in args.features.split(',') if f.strip()]
    missing = [c for c in features if c not in df.columns]
    if missing:
        raise ValueError(f'Missing features in CSV: {missing}')

    X = df[features].copy()
    X = X.apply(pd.to_numeric, errors='coerce')
    X = X.fillna(method='ffill').fillna(method='bfill').fillna(0)

    iso = IsolationForest(contamination=float(args.contamination), random_state=int(args.random_state))
    iso.fit(X.values)

    model_path = outdir / 'anomaly_iforest.pkl'
    meta_path = outdir / 'anomaly_iforest_meta.json'

    save_model(iso, model_path)

    meta = {
        'model': 'IsolationForest',
        'features': features,
        'contamination': float(args.contamination),
        'n_samples': int(X.shape[0]),
        'n_features': int(X.shape[1]),
    }
    with open(meta_path, 'w', encoding='utf-8') as fh:
        json.dump(meta, fh, indent=2)

    print(f'Saved anomaly model -> {model_path}')
    print(f'Saved metadata -> {meta_path}')

if __name__ == '__main__':
    main()