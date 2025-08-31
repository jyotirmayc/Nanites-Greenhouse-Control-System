import os
import sys
import json
import joblib
import paho.mqtt.client as mqtt
import pandas as pd

MODEL_PATH = "../models/anomaly_iforest.pkl"
META_PATH = "../models/anomaly_iforest_meta.json"
BROKER = os.getenv("MQTT_BROKER", "localhost")
PORT = int(os.getenv("MQTT_PORT", 1883))
SUB_TOPIC = "greenhouse/sensors"
PUB_TOPIC = "greenhouse/anomalies"

# Load model + metadata
iso = joblib.load(MODEL_PATH)
with open(META_PATH) as f:
    meta = json.load(f)
anom_features = ["T", "RH", "soil_theta", "PPFD", "CO2"]

def process_payload(payload: dict):
    if not all(k in payload for k in anom_features):
        return None  # skip invalid data
    X = pd.DataFrame([[payload[k] for k in anom_features]], columns=anom_features)
    y_pred = iso.predict(X)[0]  # 1=normal, -1=anomaly
    return {"anomaly": int(y_pred == -1), "data": payload}

def on_connect(client, userdata, flags, rc):
    client.subscribe(SUB_TOPIC)

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        result = process_payload(payload)
        if result:
            print("Result:", result)
            client.publish(PUB_TOPIC, json.dumps(result))
    except Exception as e:
        print("Error:", e, file=sys.stderr)

if __name__ == "__main__":
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, 60)
    client.loop_forever()
