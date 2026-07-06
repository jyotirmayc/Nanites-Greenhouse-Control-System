# IOTricity Nanites — Smart Greenhouse Control

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![Arduino](https://img.shields.io/badge/ESP32-Wokwi-green.svg)](https://wokwi.com)
[![MQTT](https://img.shields.io/badge/MQTT-HiveMQ-orange.svg)](https://hivemq.com)
[![Docker](https://img.shields.io/badge/Docker-Cloud%20Run-blue.svg)](https://docker.com)

End-to-end IoT + ML system for automated greenhouse management. An ESP32 reads sensors every 5 seconds and publishes telemetry over MQTT. A Python AI backend on the cloud runs ML models and sends timed control commands back. A Raspberry Pi provides local fallback if the cloud goes silent.

---

## How it works

```
ESP32 (Wokwi sim)
  │  publishes telemetry → greenhouse/A1/telemetry
  │  subscribes to commands ← greenhouse/A1/cmd
  ▼
HiveMQ public MQTT broker (broker.hivemq.com:1883)
  ├──▶ Cloud Controller (cloud_controller.py)
  │      runs RandomForest + IsolationForest
  │      publishes commands with source="cloud"
  │
  ├──▶ Pi Fallback (pi_fallback.py)
  │      watches for cloud silence > 90s
  │      takes over with local models, source="pi"
  │
  └──▶ Flask Dashboard (flask_dashboard.py)
         Socket.IO → live browser charts
```

**ESP32 control hierarchy (priority order):**
1. AI commands via MQTT (pump timer + fan duty)
2. Pi fallback commands (same format, `source: "pi"`)
3. Local threshold logic (soil < 0.30 → pump on, T > 28°C → fan on)
4. AI mode times out after 5 minutes → returns to local logic

---

## AI / ML Pipeline

### Models

| Model | Algorithm | Task | Features |
|-------|-----------|------|----------|
| `irrigation_rf.pkl` | RandomForestRegressor | Predict `soil_theta` 6 hours ahead | soil lag, soil rolling mean, PPFD rolling mean, T, RH, ext_T, hour |
| `anomaly_iforest.pkl` | IsolationForest | Detect multivariate anomalies | T, RH, soil_theta, PPFD, CO2 |

### Decision logic (cloud + pi)

**Irrigation** — triggered when current soil < 0.28 VWC **or** predicted soil in 6h < 0.28 VWC.
Duration proportional to deficit: `0.01 VWC ≈ 15s`, clamped to `[8s, 60s]`.

**Fan** — on when `T > 25°C`, off when `T < 23°C` (1°C deadband).

**Safety mode** — on anomaly: fan full, pump stopped, `safety: safe_mode` flag sent to ESP32.

### Training pipeline

```bash
cd AI/src

# 1. Generate 7 days of synthetic 10-min telemetry
python generate_synthetic.py

# 2. Train soil moisture predictor (RandomForest, 6h horizon)
python train_irrigation.py

# 3. Train anomaly detector (IsolationForest, contamination=0.01)
python train_anomaly.py
```

Models saved to `AI/models/`. Metadata JSON written alongside each `.pkl`.

---

## Hardware (simulated in Wokwi)

| Pin | Sensor / Actuator | Field |
|-----|-------------------|-------|
| GPIO 4 | DHT22 — temperature & humidity | `T`, `RH` |
| GPIO 34 | Potentiometer — soil moisture proxy | `soil_theta` (0.1–0.6 VWC) |
| GPIO 35 | LDR — light intensity | `PPFD` (0–1000 scaled) |
| GPIO 32 | MQ2 — gas/CO₂ proxy | `CO2` (0–1000 ppm scaled) |
| GPIO 25 | Fan relay | — |
| GPIO 26 | Pump relay | — |
| GPIO 27 | Status LED | — |
| I²C | SSD1306 OLED (128×64) | — |

Telemetry published every 5s. Heartbeat status every 15s.
`ts` field = `millis()/1000` (boot-seconds, not wall clock).

---

## Sensors → MQTT payload

```json
{
  "ts": "1204",
  "device_id": "A1",
  "T": 24.3,
  "RH": 61.2,
  "soil_theta": 0.31,
  "PPFD": 743.1,
  "CO2": 428.0,
  "ext_T": 26.1
}
```

Commands published by the AI to `greenhouse/A1/cmd`:

```json
{
  "ts": "2025-08-24T08:14:02+00:00",
  "source": "cloud",
  "cmd_id": "uuid",
  "actions": {
    "irrigation": {"action": "on", "duration_s": 23},
    "fan": {"action": "set", "duty": 1.0}
  },
  "expires_at": "2025-08-24T08:17:02+00:00"
}
```

---

## Quick Start

**Prerequisites:** Python 3.9+, pip

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Train models (run from AI/src/)
cd AI/src
python generate_synthetic.py
python train_irrigation.py
python train_anomaly.py

# 3. Start AI cloud controller (connects to HiveMQ, blocks)
python cloud_controller.py

# 4. Start dashboard  →  http://localhost:5000
python flask_dashboard.py

# 5. Open Wokwi simulation — ESP32 auto-connects to HiveMQ
#    https://wokwi.com  (load Hardware/Arduino/esp32_code.ino)
```

**Pi fallback** (run on Raspberry Pi, same network or anywhere):
```bash
cd AI/src
python pi_fallback.py   # monitors cloud silence, takes over at 90s
```

---

## Docker (Cloud Run)

The Dockerfile runs the full pipeline in sequence on startup:
1. `generate_synthetic.py` — generate training data
2. `train_irrigation.py` + `train_anomaly.py` — train models
3. `cloud_controller.py` — start AI brain (background)
4. `flask_dashboard.py` — serve dashboard on port 8080

```bash
docker build -t iotricity .
docker run -p 8080:8080 -e MQTT_BROKER=broker.hivemq.com iotricity
```

---

## Configuration

All tunable parameters live in `AI/config.yaml`:

```yaml
control:
  soil_min: 0.28        # trigger irrigation below this VWC
  soil_target: 0.32     # irrigate until this VWC
  T_set: 24.0           # fan setpoint (°C)
  T_deadband: 1.0       # ±deadband around setpoint
  irrigation_max_sec: 60
  irrigation_min_sec: 8
  cmd_expires_s: 180    # command TTL

fallback:
  cloud_timeout_s: 90   # seconds of silence before Pi takes over
```

---

## Project Structure

```
IOTricity_Nanites/
├── AI/
│   ├── config.yaml                 # all tuneable parameters
│   ├── src/
│   │   ├── cloud_controller.py     # AI brain — MQTT subscriber + ML inference
│   │   ├── pi_fallback.py          # local fallback agent
│   │   ├── flask_dashboard.py      # Socket.IO web dashboard
│   │   ├── generate_synthetic.py   # synthetic training data generator
│   │   ├── train_irrigation.py     # RandomForest training script
│   │   ├── train_anomaly.py        # IsolationForest training script
│   │   └── utils.py                # shared: config loader, model saver, timestamp parser, duration helper
│   ├── models/                     # trained .pkl files + metadata JSON
│   └── data/                       # generated CSV training data
├── Hardware/Arduino/
│   └── esp32_code.ino              # ESP32 firmware (Wokwi compatible)
├── docs/
│   ├── model.md                    # ML pipeline details
│   └── sensor_specs.md             # hardware sensor specs
├── Dockerfile
└── requirements.txt
```

---

## Known Limitations

- **No real-time clock on ESP32** — `ts` field is boot-seconds, not wall time. Cloud controller handles this via `safe_parse_timestamp()`.
- **Public MQTT broker** — `broker.hivemq.com` has no auth. Topic isolation only. Not suitable for production with sensitive data.
- **Simulated sensors** — LDR and MQ2 are analog proxies; PPFD is scaled 0–1000 to match training distribution.
- **Rolling features** — `soil_roll_6` and `ppfd_roll_6` are not computed on the ESP32. Cloud controller falls back to point values when absent from payload.

---

## Dependencies

```
pandas, numpy, scikit-learn, joblib   # ML pipeline
paho-mqtt                             # MQTT client
pyyaml                                # config
flask, flask-socketio                 # dashboard
```