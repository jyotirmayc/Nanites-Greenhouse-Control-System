# IOTricity\_Nanites

**IoT Smart Greenhouse Control System** — the Nanites project.

---

## Project summary

An IoT-powered Smart Greenhouse Control System that monitors and automates greenhouse conditions using distributed sensors, actuators, and AI-driven decision making. The system focuses on keeping crops in their optimal bands (temperature, humidity, VPD, soil moisture, PPFD, CO₂) while conserving resources (water, energy) and providing remote monitoring & alerts.

The repository contains the AI components (training, inference services, demo pipelines) for irrigation optimization, anomaly detection, and support for climate control and yield prediction.

---

## Quick features

* **Real-time monitoring:** Temperature, humidity, soil moisture, light (PPFD/lux), CO₂.
* **AI-powered automation:** Models suggest irrigation timing/volume, detect anomalies, and recommend climate setpoints.
* **Automated irrigation & ventilation:** Actuators triggered automatically, with manual override via dashboard.
* **Remote access & alerts:** Web/mobile dashboard, push/SMS/Telegram alerts for critical events.
* **Resilient design:** ESP32 handles local safety rules; Raspberry Pi acts as edge inference and gateway; Cloud for heavy ML and model training.

---

## System architecture (edge → gateway → cloud)

* **Sensors / Actuators:** ESP32-based sensor nodes or other microcontrollers read sensor arrays (BME280/SHT31, capacitive soil probes, PAR/BH1750, SCD30 CO₂) and control relays/MOSFETs for pumps, fans, heaters, and lights.
* **Edge Gateway (Raspberry Pi / Jetson):** subscribes to MQTT telemetry, runs lightweight ML inference (irrigation advisor, anomaly detector), acts as fallback when cloud is unavailable, and controls actuators via MQTT commands.
* **Cloud AI Server:** trains heavier models (yield forecasting, RL/MPC optimizers, large CNNs for vision), stores time-series data, and serves dashboards and OTA model updates.
* **User Interface:** Grafana/Streamlit/React dashboard for visualization, configuration, and manual overrides.

---

## Responsibilities & recommended hardware

(Condensed table — full details in `docs/full-hardware.md`.)

| Responsibility                | Hardware (sensors & actuators)                                        | Smart models / control algorithms                                        |
| ----------------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| Climate control               | BME280/SHT31, SCD30, fans, heaters, vents (MOSFET/SSR)                | PID + MPC (cloud), VPD control, anomaly detection (IsolationForest)      |
| Irrigation & water management | Capacitive soil probes, flow meters (YF-S201), solenoid valves, pumps | ET₀-aware scheduling (FAO-56), RandomForest/XGBoost irrigation regressor |
| Lighting control              | BH1750 / PAR sensor, LED driver (PWM/0–10V)                           | DLI-driven scheduler, energy-aware optimizer                             |
| Crop monitoring & vision      | ESP32-CAM / Pi Camera                                                 | Object detection (YOLOv8 small), ripeness classifier (MobileNet)         |
| Yield prediction              | Sensor history, DLI, degree-days                                      | Gradient boosting (XGBoost/LightGBM) regression                          |
| Alerts & UI                   | ESP32 (Wi-Fi/LoRa), Pi gateway, MQTT broker, Grafana/Streamlit        | Alert prioritization classifier, rule engine                             |

---

## Where models run (deployment split)

* **ESP32 (edge)**: sensor reads, threshold safety rules, actuator driving, heartbeat & retries. *No heavy ML.*
* **Raspberry Pi (local/gateway)**: lightweight ML inference (scikit-learn/XGBoost), sensor fusion, anomaly detection, small CV models if required (TinyYOLO / TensorFlow Lite). Acts as the primary runtime when cloud is unreachable.
* **Cloud**: training, large-model inference (full YOLO, RL/MPC, LSTM), data lake, model registry, dashboards, multi-bay coordination.

---

## AI components & models (what to build first)

**Priority (hackathon / 36-hour)**

1. **Irrigation advisor** — RandomForest/XGBoost regressor that predicts soil moisture or time-to-threshold (predict soil θ in 6 hours). Outputs recommended irrigation volume & schedule.
2. **Anomaly detector** — IsolationForest on multivariate sensor windows to flag stuck sensors or actuator failures.
3. **Inference service** — lightweight Python service (FastAPI/Flask) on Raspberry Pi that subscribes to MQTT telemetry, runs models, and publishes commands/alerts.

**Stretch / cloud**

* Yield predictor (XGBoost / LightGBM).
* Vision pipelines for fruit counting and ripeness (YOLOv8 small → Pi/Cloud).
* MPC / RL for multi-actuator coordinated control (cloud training, Pi inference).

---

## Data format (suggested telemetry JSON)

```json
{
  "ts": "2025-08-30T09:30:00Z",
  "bayId": "A1",
  "env": {"T": 26.4, "RH": 72.1, "VPD": 0.9, "CO2": 850, "PPFD": 320},
  "soil": {"theta": 0.29, "EC": 1.4, "T": 22.1},
  "ext": {"T": 31.2, "RH": 60, "wind": 2.4, "solar": 700},
  "actuators": {"fan": 0, "heater": 0, "irrigation": 0, "led": 0.7},
  "et0": 4.2,
  "alerts": []
}
```

---

## Quickstart — AI-side (run locally / on Pi)

**Environment**

```bash
python -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install pandas numpy scikit-learn xgboost joblib fastapi uvicorn paho-mqtt streamlit
```

**Run the demo pipeline (synthetic data)**

1. Place CSV in `data/` (synthetic dataset provided in `/data`).
2. Train irrigation model: `python src/train_irrigation.py` (produces `models/irrigation_model.pkl`).
3. Train anomaly detector: `python src/train_anomaly.py` (produces `models/anomaly_iforest.pkl`).
4. Start MQTT broker (Mosquitto) on Pi: `sudo apt install mosquitto` then `sudo systemctl start mosquitto`.
5. Start inference service: `python src/infer_service.py`.
6. Stream demo telemetry: `python src/mqtt_publisher_demo.py`.
7. Open dashboard: `streamlit run src/streamlit_dashboard.py`.

---

## 36-hour focused AI plan (what to deliver)

* **Irrigation model + metrics** (MAE, simulated water saved).
* **IsolationForest anomaly detector** (precision/recall on synthetic anomalies).
* **Inference service (Pi-ready)** publishing to MQTT topics.
* **Streamlit dashboard** showing telemetry, predictions, and alerts.
* **Demo script** that plays synthetic telemetry at accelerated speed.

---

## MQTT topics (standardized)

* `greenhouse/{bay}/telemetry` → raw JSON telemetry.
* `greenhouse/{bay}/ml/irrigation` → model outputs (predicted soil, recommended liters).
* `greenhouse/{bay}/alerts` → anomaly & critical alerts.
* `greenhouse/{bay}/cmd/{actuator}` → actuator commands (from Pi or cloud).

---

## Safety & guardrails

* Local fallback safety rules on ESP32 (hard cutoffs, min/max runtimes).
* Actuator interlocks (no CO₂ enrichment while vents open).
* Model & device heartbeats — Pi falls back to safe defaults if cloud unreachable.
* Signed OTA & per-device credentials for production.

---

## File structure (repo)

```
/ (root)
├─ data/                      # CSVs (synthetic + collected telemetry)
├─ docs/                      # hardware lists, diagrams, deeper docs
├─ models/                    # trained models (.pkl)
├─ src/
│  ├─ train_irrigation.py
│  ├─ train_anomaly.py
│  ├─ infer_service.py
│  ├─ mqtt_publisher_demo.py
│  └─ streamlit_dashboard.py
├─ README.md                  # this file (AI-focused)
└─ LICENSE
```

---

## Future enhancements

* Weather API integration for ET₀ forecasting and feedforward control.
* Full CV pipeline for fruit counting & disease detection.
* MPC / RL for multi-actuator coordination and energy optimization.
* LoRaWAN integration for large-farm coverage and mesh-controlled nodes.

---

## Contributing

If you add hardware, datasets, or new models, update `docs/full-hardware.md` and `docs/model-registry.md`. Create a clear `model-metadata.json` (name, version, sha256, trained-on-date).

---

## License

MIT

---

> Want me to also add a short `docs/quick-demo.md` with step-by-step commands and a minimal slide deck for the hackathon presentation?
