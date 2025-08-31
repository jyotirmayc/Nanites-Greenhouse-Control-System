import joblib
import pandas as pd

# Example input for irrigation model (update columns/features as needed)
features = ['soil_lag1','soil_roll_6','ppfd_roll_6','T','RH','ext_T','hour']
sample = pd.DataFrame([[0.32, 0.33, 800, 26, 65, 30, 14.5]], columns=features)
model = joblib.load("../models/irrigation_rf.pkl")
pred = model.predict(sample)
print("Predicted soil moisture in 6h:", pred)
