import argparse
import os
import pandas as pd
import numpy as np
from datetime import datetime
import yaml
from utils import load_config


def parse_args():
    p = argparse.ArgumentParser(description='Generate synthetic greenhouse telemetry')
    p.add_argument('--days', type=int, default=7, help='Number of days to simulate')
    p.add_argument('--bays', type=str, default='A1', help='Comma-separated bay IDs, e.g. A1,A2,A3,A4')
    p.add_argument('--seed', type=int, default=42, help='Random seed')
    p.add_argument('--start', type=str, default='2025-08-24 00:00', help='Start datetime')
    p.add_argument('--out', type=str, default=None, help='Output CSV path (overrides config)')
    return p.parse_args()


def simulate_bay(bay_id, start, days, seed, soil_min=0.28):
    rng = np.random.default_rng(seed)
    periods = days * 24 * 6
    ts = pd.date_range(start=start, periods=periods, freq='10min')
    n = len(ts)

    hours = ts.hour + ts.minute / 60.0
    T_ext = 30 + 6 * np.sin(2 * np.pi * (hours - 14) / 24)
    T = T_ext - 4 + rng.normal(0, 0.6, n)
    RH = 60 + 15 * np.cos(2 * np.pi * (hours - 6) / 24) + rng.normal(0, 2, n)
    PPFD = 1000 * np.maximum(0, np.sin(2 * np.pi * (hours - 6) / 24)) + rng.normal(0, 30, n)
    CO2 = 420 + 30 * np.sin(2 * np.pi * (hours - 9) / 24) + rng.normal(0, 8, n)

    soil = np.zeros(n)
    soil[0] = 0.35
    evap_coeff = 0.0006
    irrigation_liters = np.zeros(n)
    pump_on = np.zeros(n, dtype=int)

    for i in range(1, n):
        evap = evap_coeff * (1 + PPFD[i] / 1000) * (1 + max(0, (T[i] - 20)) / 15)
        soil[i] = soil[i - 1] - evap + rng.normal(0, 0.0005)

        if soil[i] < soil_min and rng.random() < 0.9:  # ponytail: threshold from config
            liters = rng.uniform(0.5, 2.5)
            irrigation_liters[i] = liters
            pump_on[i] = 1
            soil[i] += 0.01 * liters

        soil[i] = np.clip(soil[i], 0.12, 0.50)

    return pd.DataFrame({
        'ts': ts,
        'bayId': bay_id,
        'T': np.round(T, 2),
        'RH': np.round(RH, 2),
        'soil_theta': np.round(soil, 4),
        'PPFD': np.round(PPFD, 1),
        'CO2': np.round(CO2, 1),
        'ext_T': np.round(T_ext, 2),
        'irrigation_liters': np.round(irrigation_liters, 3),
        'pump_on': pump_on,
    })


def main():
    args = parse_args()

    config = load_config("../config.yaml")  # ponytail: resolve_path makes this CWD-independent

    bays = [b.strip() for b in args.bays.split(',') if b.strip()]
    start = datetime.fromisoformat(args.start)

    frames = []
    soil_min = config.get('control', {}).get('soil_min', 0.28)
    for i, bay in enumerate(bays):
        bay_seed = args.seed + i
        print(f"Simulating bay {bay} (seed={bay_seed})...")
        frames.append(simulate_bay(bay, start, args.days, bay_seed, soil_min=soil_min))

    df = pd.concat(frames, ignore_index=True)

    output_path = args.out or config['training']['data_path']
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    df.to_csv(output_path, index=False)

    print(f"Saved synthetic data to: {output_path}")
    print(f"Shape: {df.shape}  |  Bays: {bays}  |  Days: {args.days}")
    print(f"Rows per bay: {args.days * 24 * 6}")


if __name__ == '__main__':
    main()
