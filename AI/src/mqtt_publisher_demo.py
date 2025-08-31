import pandas as pd, json, time, os
import paho.mqtt.client as mqtt
BROKER = os.environ.get("MQTT_BROKER","localhost")
df = pd.read_csv("../data/synthetic_greenhouse_7days_10min.csv", parse_dates=['ts'])
client = mqtt.Client(); client.connect(BROKER,1883,60)
print("Publishing to broker:", BROKER)
for i,row in df.iterrows():
    payload = {
      "ts": row['ts'].isoformat(),
      "T": float(row['T']), "RH": float(row['RH']),
      "soil_theta": float(row['soil_theta']), "PPFD": float(row['PPFD']),
      "CO2": float(row['CO2']), "ext_T": float(row['ext_T'])
    }
    client.publish("greenhouse/A1/telemetry", json.dumps(payload))
    time.sleep(0.1)
print("Done publishing demo stream")
