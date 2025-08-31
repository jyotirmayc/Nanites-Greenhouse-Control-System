import joblib
import pandas as pd

# Example input for anomaly detection (update columns/features as needed)
anom_features = ['T','RH','soil_theta','PPFD','CO2']
sample = pd.DataFrame([[26, 65, 0.32, 800, 420]], columns=anom_features)
model = joblib.load("../models/anomaly_iforest.pkl")
pred = model.predict(sample)
print("Anomaly detected:" if pred[0] == -1 else "Normal reading.")
