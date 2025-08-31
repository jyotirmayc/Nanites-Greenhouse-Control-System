#!/usr/bin/env python3
import os
import sys
import json
import joblib
import paho.mqtt.client as mqtt
import pandas as pd
import yaml
from pathlib import Path

# ---------------- Load config ----------------
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
if not CONFIG_PATH.exists():
    sys.exit(f"Config file not found: {CONFIG_PATH}")

with CONFIG_PATH.open("r") as f:
    config = yaml.safe_load(f) or {}

MODEL_PATH = Path(config.get('model', {}).get('anomaly', {}).get('path', ''))
META_PATH = Path("../models/anomaly_iforest_meta.json")  # optional: move to config

BROKER = os.environ.get("MQTT_BROKER", config.get('inference', {}).get('mqtt_broker', 'localhost'))
PORT = int(os.environ.get("MQTT_PORT", 1883))
SUB_TOPIC = config.get('inference', {}).get('telemetry_topic', 'greenhouse/sensors')
PUB_TOPIC = config.get('inference', {}).get('alert_topic', 'greenhouse/anomalies')

# ---------------- Load model & metadata ----------------
if not MODEL_PATH.exists():
    sys.exit(f"Anomaly model file not found: {MODEL_PATH}")

try:
    iso = joblib.load(MODEL_PATH)
except Exception as e:
    sys.exit(f"Failed to load model: {e}")

if not META_PATH.exists():
    print(f"Warning: metadata file not found: {META_PATH}", file=sys.stderr)
    meta = {}
else:
    with META_PATH.open() as f:
        meta = json.load(f)

anom_features = config.get('training', {}).get('anomaly_features', ['T','RH','soil_theta','PPFD','CO2'])

# ---------------- Payload processing ----------------
def process_payload(payload: dict):
    if not all(k in payload for k in anom_features):
        return None
    try:
        X = pd.DataFrame([[payload[k] for k in anom_features]], columns=anom_features)
        y_pred = iso.predict(X)[0]  # 1=normal, -1=anomaly
        return {"anomaly": int(y_pred == -1), "data": payload}
    except Exception as e:
        print(f"Prediction error: {e}", file=sys.stderr)
        return None

# ---------------- MQTT callbacks ----------------
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"Connected to MQTT broker {BROKER}:{PORT}")
        client.subscribe(SUB_TOPIC)
        print(f"Subscribed to topic: {SUB_TOPIC}")
    else:
        print(f"Failed to connect, return code {rc}", file=sys.stderr)

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        result = process_payload(payload)
        if result:
            client.publish(PUB_TOPIC, json.dumps(result))
            print(f"Published result: {result}")
    except Exception as e:
        print(f"Error handling message: {e}", file=sys.stderr)

# ---------------- Main ----------------
if __name__ == "__main__":
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(BROKER, PORT, 60)
    except Exception as e:
        sys.exit(f"Failed to connect to MQTT broker {BROKER}:{PORT} - {e}")

    client.loop_forever()
