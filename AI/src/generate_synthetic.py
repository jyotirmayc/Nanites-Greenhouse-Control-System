import os
import pandas as pd
import numpy as np
from datetime import datetime
import yaml

# Reproducibility
np.random.seed(42)

# Time setup
start = datetime(2025, 8, 24, 0, 0)
periods = 7 * 24 * 6  # 7 days, 10-min intervals
ts = pd.date_range(start=start, periods=periods, freq='10T')
n = len(ts)

# Environmental variables
hours = np.array([t.hour + t.minute/60.0 for t in ts])
T_ext = 30 + 6 * np.sin(2 * np.pi * (hours - 14) / 24)
T = T_ext - 4 + np.random.normal(0, 0.6, n)
RH = 60 + 15 * np.cos(2 * np.pi * (hours - 6) / 24) + np.random.normal(0, 2, n)
PPFD = 1000 * np.maximum(0, np.sin(2 * np.pi * (hours - 6) / 24)) + np.random.normal(0, 30, n)
CO2 = 420 + 30 * np.sin(2 * np.pi * (hours - 9) / 24) + np.random.normal(0, 8, n)

# Soil moisture + irrigation
soil = np.zeros(n)
soil[0] = 0.35
evap_coeff = 0.0006
irrigation_liters = np.zeros(n)
pump_on = np.zeros(n, dtype=int)

for i in range(1, n):
    evap = evap_coeff * (1 + PPFD[i]/1000) * (1 + max(0, (T[i]-20))/15)
    soil[i] = soil[i-1] - evap + np.random.normal(0, 0.0005)

    if soil[i] < 0.28 and np.random.rand() < 0.9:
        liters = np.random.uniform(0.5, 2.5)
        irrigation_liters[i] = liters
        pump_on[i] = 1
        soil[i] += 0.01 * liters  # clearer scaling: 0.5–2.5 L → +0.005–0.025

    soil[i] = np.clip(soil[i], 0.12, 0.50)

# DataFrame
df = pd.DataFrame({
    'ts': ts,
    'bayId': ['A1'] * n,
    'T': np.round(T, 2),
    'RH': np.round(RH, 2),
    'soil_theta': np.round(soil, 4),
    'PPFD': np.round(PPFD, 1),
    'CO2': np.round(CO2, 1),
    'ext_T': np.round(T_ext, 2),
    'irrigation_liters': np.round(irrigation_liters, 3),
    'pump_on': pump_on
})

# Load config
with open(os.path.join("..", "config.yaml"), "r") as f:
    config = yaml.safe_load(f)

# Save using config path
output_path = config['training']['data_path']
df.to_csv(output_path, index=False)
print(f"Saved {output_path}")
