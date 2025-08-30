import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
import joblib, os, json

os.makedirs("../models", exist_ok=True)
df = pd.read_csv("../data/synthetic_greenhouse_7days_10min.csv", parse_dates=['ts'])
horizon = 36  # 6 hours (36 * 10min)

df = df.sort_values('ts').reset_index(drop=True)
df['soil_lag1'] = df['soil_theta'].shift(1)
df['soil_roll_6'] = df['soil_theta'].rolling(6).mean()
df['ppfd_roll_6'] = df['PPFD'].rolling(6).mean()
df['hour'] = df['ts'].dt.hour + df['ts'].dt.minute/60.0
df = df.dropna().reset_index(drop=True)
df['target_6h'] = df['soil_theta'].shift(-horizon)
df = df.dropna().reset_index(drop=True)

features = ['soil_lag1','soil_roll_6','ppfd_roll_6','T','RH','ext_T','hour']
X = df[features].copy()
y = df['target_6h'].copy()

split_idx = int(len(df)*0.8)
X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

rf = RandomForestRegressor(n_estimators=150, max_depth=8, random_state=42, n_jobs=-1)
rf.fit(X_train, y_train)
pred_test = rf.predict(X_test)
mae_test = mean_absolute_error(y_test, pred_test)
r2_test = r2_score(y_test, pred_test)

joblib.dump(rf, "../models/irrigation_rf.pkl")
meta = {"mae_test": float(mae_test), "r2_test": float(r2_test), "rows_train": len(X_train)}
with open("../models/irrigation_rf_meta.json","w") as f:
    json.dump(meta, f, indent=2)
print("Saved ../models/irrigation_rf.pkl and meta:", meta)
