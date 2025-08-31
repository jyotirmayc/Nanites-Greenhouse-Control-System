import streamlit as st
import pandas as pd
import json, time
import paho.mqtt.client as mqtt
from threading import Thread, Lock

st.set_page_config(layout="wide")
st.title("Greenhouse Dashboard")

data = []
lock = Lock()

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        required = {"ts","T","RH","soil_theta","PPFD","CO2","ext_T"}
        if required.issubset(payload.keys()):
            with lock:
                data.append(payload)
    except:
        pass

def mqtt_loop():
    client = mqtt.Client()
    client.on_message = on_message
    client.connect("localhost",1883,60)
    client.subscribe("greenhouse/A1/telemetry")
    client.loop_forever()

Thread(target=mqtt_loop,daemon=True).start()

placeholder = st.empty()
while True:
    time.sleep(1)
    with lock:
        if len(data) > 0:
            df = pd.DataFrame(data)
            df['ts'] = pd.to_datetime(df['ts'])
            df = df.set_index('ts').tail(200)
            placeholder.line_chart(df[['soil_theta','T','RH','PPFD']])
