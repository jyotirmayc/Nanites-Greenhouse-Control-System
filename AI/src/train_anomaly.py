# train_anomaly.py
import pandas as pd, joblib, os, json
from sklearn.ensemble import IsolationForest

os.makedirs("../models", exist_ok=True)
df = pd.read_csv("../data/synthetic_greenhouse_7days_10min.csv", parse_dates=['ts'])
df = df.sort_values('ts').reset_index(drop=True)
anom_features = ['T','RH','soil_theta','PPFD','CO2']
X = df[anom_features].fillna(method='ffill')

split_idx = int(len(X)*0.8)
iso = IsolationForest(contamination=0.01, random_state=42)
iso.fit(X.iloc[:split_idx])

joblib.dump(iso, "../models/anomaly_iforest.pkl")
meta = {"model":"IsolationForest","contamination":0.01}
with open("../models/anomaly_iforest_meta.json","w") as f:
    json.dump(meta, f, indent=2)
print("Saved ../models/anomaly_iforest.pkl")
