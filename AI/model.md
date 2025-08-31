# Greenhouse AI Demo: Codebase Overview

## Data Generation & Loading
- **generate_synthetic.py**: Generates synthetic greenhouse sensor data for 7 days at 10-minute intervals, simulating temperature, humidity, light, CO₂, soil moisture, and irrigation events. Saves to `data/synthetic_greenhouse_7days_10min.csv`.
- **Dataset_10min.py**: Downloads a real greenhouse sensor dataset from Kaggle for experimentation.

## Model Training
- **train_irrigation.py**: Loads synthetic data, engineers features (lags, rolling averages, hour), and trains a Random Forest regressor to predict soil moisture 6 hours ahead. Saves model and test metrics to `models/irrigation_rf.pkl` and `irrigation_rf_meta.json`.
- **train_anomaly.py**: Trains an Isolation Forest model to detect anomalies in greenhouse sensor data (using temperature, humidity, soil moisture, light, CO₂). Saves model and metadata to `models/anomaly_iforest.pkl` and `anomaly_iforest_meta.json`.

## Real-Time Inference & Streaming
- **infer_service.py**: Loads trained models and runs an MQTT-based inference service. Subscribes to telemetry, predicts future soil moisture, checks for anomalies, and publishes results/alerts to MQTT topics.
- **mqtt_publisher_demo.py**: Publishes synthetic telemetry data row-by-row to the MQTT broker, simulating real-time sensor streaming for demo/testing.

## Visualization
- **streamlit_dashboard.py**: Streamlit app for visualizing recent greenhouse data (last 200 rows) and instructs users to run the publisher and inference service for live MQTT demo.

## Workflow Summary
1. Generate synthetic data or download real data.
2. Train irrigation and anomaly detection models.
3. Start MQTT broker (Docker or public broker).
4. Run inference service to process live telemetry.
5. Publish demo telemetry data.
6. Visualize results in Streamlit dashboard.

## File Structure
- `data/`: Contains synthetic and real datasets.
- `models/`: Stores trained models and metadata.
- `AI/src/`: Contains all scripts for data, training, inference, streaming, and visualization.

---
This codebase demonstrates a full pipeline for greenhouse sensor analytics: data simulation, ML model training, real-time inference, anomaly detection, MQTT streaming, and dashboard visualization.

# Greenhouse AI Demo (Simulated)
Steps:
1. Create and activate Python venv:
   python -m venv venv
   .\venv\Scripts\Activate.ps1

2. Install dependencies:
   pip install -r requirements.txt

3. Create synthetic data:
   cd src
   python generate_synthetic.py

4. Train models:
   python train_irrigation.py
   python train_anomaly.py

5. Start MQTT broker (Docker recommended):
   docker run -it -p 1883:1883 --name mosquitto eclipse-mosquitto
   OR use test.mosquitto.org as broker (set env var MQTT_BROKER).

6. Start inference service:
   python infer_service.py

7. In another terminal publish simulated telemetry:
   python mqtt_publisher_demo.py

8. Run dashboard:
   streamlit run src/streamlit_dashboard.py
   raspberry Pi the infer_service.py is the script you'd run for local inference.

