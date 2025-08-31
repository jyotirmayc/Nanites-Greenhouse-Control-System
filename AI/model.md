# Greenhouse AI Demo: Codebase Overview

## Data Generation & Loading
- **generate_synthetic.py**: Generates synthetic greenhouse sensor data for 7 days at 10-minute intervals, simulating temperature, humidity, light, CO₂, soil moisture, and irrigation events. Uses config for output path. Saves to the path specified in `config.yaml` (e.g., `AI/data/synthetic_greenhouse_7days_10min.csv`).
- **Dataset_10min.py**: Downloads a real greenhouse sensor dataset from Kaggle for experimentation.

## Model Training
- **train_irrigation.py**: Loads synthetic data (path from config or CLI), engineers features (lags, rolling averages, hour), and trains a Random Forest regressor to predict soil moisture 6 hours ahead. Saves model and test metrics to `models/irrigation_rf.pkl` and `irrigation_rf_meta.json` (location from config or CLI).
- **train_anomaly.py**: Loads data (path from config or CLI), trains Isolation Forest model to detect anomalies (features: T, RH, soil_theta, PPFD, CO₂). Saves model and metadata to `models/anomaly_iforest.pkl` and `anomaly_iforest_meta.json`.

## Real-Time Inference & Streaming
- **infer_service.py**: Loads trained models (paths from config), runs an MQTT-based inference service. Subscribes to telemetry, predicts future soil moisture, checks for anomalies, and publishes results/alerts/commands to MQTT topics (topics from config).
- **mqtt_publisher_demo.py**: Publishes synthetic telemetry data row-by-row to the MQTT broker, simulating real-time sensor streaming for demo/testing. Data path and MQTT settings from config.

## Visualization
- **streamlit_dashboard.py**: Streamlit app for visualizing recent greenhouse data (last 200 rows) and live MQTT data. Loads CSV using a robust path resolution (now works regardless of launch directory).
## Prediction Scripts
- **predict_irrigation.py**: Loads irrigation model and features from config, predicts on sample input.
- **predict_anomaly.py**: Loads anomaly model and features from config, predicts on sample input.
## Utilities
- **utils.py**: Contains helper functions for path resolution, saving models, etc.

## Workflow Summary
1. Generate synthetic data or download real data.
2. Train irrigation and anomaly detection models.
3. Start MQTT broker (Docker or public broker).
4. Run inference service to process live telemetry.
5. Publish demo telemetry data.
6. Visualize results in Streamlit dashboard.

## File Structure
- `AI/data/`: Contains synthetic and real datasets.
- `models/`: Stores trained models and metadata.
- `AI/src/`: Contains all scripts for data, training, inference, streaming, and visualization.

---
This codebase demonstrates a full pipeline for greenhouse sensor analytics: data simulation, ML model training, real-time inference, anomaly detection, MQTT streaming, dashboard visualization, and prediction/testing utilities.

# Greenhouse AI Demo (Simulated)

## Setup & Run Instructions (Windows, PowerShell)

1. **Create and activate Python virtual environment:**
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

2. **Install dependencies:**
   ```powershell
   pip install -r requirements.txt
   ```

3. **Start MQTT broker (Docker, with config):**
   ```powershell
   docker run -d --name mosquitto -p 1883:1883 -v ${PWD}\mosquitto\config\mosquitto.conf:/mosquitto/config/mosquitto.conf eclipse-mosquitto:latest
   ```

4. **Generate synthetic data:**
   ```powershell
   cd AI/src
   python generate_synthetic.py
   ```

5. **Train models:**
   ```powershell
   python train_irrigation.py --data ../data/synthetic_greenhouse_7days_10min.csv --outdir ../models
   python train_anomaly.py --data ../data/synthetic_greenhouse_7days_10min.csv --outdir ../models
   ```

6. **Start inference service:**
   ```powershell
   python infer_service.py
   ```

7. **Publish simulated telemetry (in another terminal):**
   ```powershell
   python mqtt_publisher_demo.py
   ```

8. **Run dashboard:**
   ```powershell
   streamlit run streamlit_dashboard.py
   ```

---
*On Raspberry Pi or edge device, run `infer_service.py` for local inference.*