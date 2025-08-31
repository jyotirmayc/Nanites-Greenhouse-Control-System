import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
import joblib, os, json, argparse

parser = argparse.ArgumentParser()
parser.add_argument("--data", default=os.getenv("DATA_PATH", "../data/synthetic.csv"),
                    help="Path to input CSV with telemetry")
parser.add_argument("--outdir", default=os.getenv("MODEL_DIR", "../models"),
                    help="Directory to save trained model + metadata")
args = parser.parse_args()

os.makedirs(args.outdir, exist_ok=True)

df = pd.read_csv(args.data, parse_dates=['ts']).sort_values('ts').reset_index(drop=True)

horizon = 36  # 6h lookahead (36*10min)
df['soil_lag1'] = df['soil_theta'].shift(1)
df['soil_roll_6'] = df['soil_theta'].rolling(6).mean()
df['ppfd_roll_6'] = df['PPFD'].rolling(6).mean()
df['hour'] = df['ts'].dt.hour + df['ts'].dt.minute/60.0
df['target_6h'] = df['soil_theta'].shift(-horizon)
df = df.dropna().reset_index(drop=True)

features = ['soil_lag1','soil_roll_6','ppfd_roll_6','T','RH','ext_T','hour']
X, y = df[features], df['target_6h']
split = int(len(df)*0.8)
X_train, X_test = X.iloc[:split], X.iloc[split:]
y_train, y_test = y.iloc[:split], y.iloc[split:]

rf = RandomForestRegressor(n_estimators=150, max_depth=8, random_state=42, n_jobs=-1)
rf.fit(X_train, y_train)

pred = rf.predict(X_test)
meta = {
    "mae_test": float(mean_absolute_error(y_test, pred)),
    "r2_test": float(r2_score(y_test, pred)),
    "rows_train": len(X_train)
}

model_path = os.path.join(args.outdir, "irrigation_rf.pkl")
meta_path = os.path.join(args.outdir, "irrigation_rf_meta.json")
joblib.dump(rf, model_path)
with open(meta_path, "w") as f: json.dump(meta, f, indent=2)

print(f"Saved model → {model_path}")
print("Meta:", meta)
