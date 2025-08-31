import streamlit as st
import pandas as pd
import json
import time
import paho.mqtt.client as mqtt
from threading import Thread, Lock
import yaml
import os
from collections import deque

# ---------------- Streamlit setup ----------------
st.set_page_config(layout="wide")
st.title("Greenhouse Dashboard")

# ---------------- Shared data ----------------
data = deque(maxlen=1000)  # keep last 1000 messages to avoid memory issues
lock = Lock()

# ---------------- MQTT callbacks ----------------
def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        required = {"ts","T","RH","soil_theta","PPFD","CO2","ext_T"}
        if required.issubset(payload.keys()):
            with lock:
                data.append(payload)
    except Exception as e:
        print("Error parsing MQTT message:", e)

def mqtt_loop(broker, port, topic):
    client = mqtt.Client()
    client.on_message = on_message
    try:
        client.connect(broker, port, 60)
    except Exception as e:
        print(f"Failed to connect to MQTT broker {broker}:{port} - {e}")
        return
    client.subscribe(topic)
    client.loop_forever()

# ---------------- Load config ----------------
CONFIG_PATH = '../config.yaml'
with open(CONFIG_PATH, 'r') as f:
    config = yaml.safe_load(f)

MQTT_BROKER = config.get('inference', {}).get('mqtt_broker', 'localhost')
MQTT_PORT = config.get('inference', {}).get('mqtt_port', 1883)
MQTT_TOPIC = config.get('inference', {}).get('telemetry_topic', 'greenhouse/A1/telemetry')
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))  # Only one dirname
DATA_PATH = os.path.join(PROJECT_ROOT, "..", "data", "synthetic_greenhouse_7days_10min.csv")
DATA_PATH = os.path.abspath(DATA_PATH)

# Start MQTT thread
Thread(target=mqtt_loop, args=(MQTT_BROKER, MQTT_PORT, MQTT_TOPIC), daemon=True).start()

# ---------------- Placeholder for chart ----------------
placeholder = st.empty()

# ---------------- Initial CSV data ----------------
try:
    df_csv = pd.read_csv(DATA_PATH, parse_dates=['ts'])
except Exception as e:
    st.error(f"Failed to load CSV data: {e}")
    df_csv = pd.DataFrame(columns=['ts','soil_theta','T','RH','PPFD'])

# ---------------- Streamlit loop ----------------
st.write("Live data from MQTT:")

while True:
    time.sleep(1)
    with lock:
        snapshot = list(data)  # copy to avoid holding lock too long
    if snapshot:
        df_live = pd.DataFrame(snapshot)
        df_live['ts'] = pd.to_datetime(df_live['ts'])
        df_live = df_live.set_index('ts').sort_index()
        df_plot = df_live.tail(200)[['soil_theta','T','RH','PPFD']]
        placeholder.line_chart(df_plot)
    else:
        # show CSV data if MQTT not yet received
        df_plot = df_csv.set_index('ts').tail(200)[['soil_theta','T','RH','PPFD']]
        placeholder.line_chart(df_plot)
