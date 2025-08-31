import json, joblib, os
import paho.mqtt.client as mqtt
import pandas as pd

MQTT_BROKER = os.environ.get("MQTT_BROKER","localhost")
TOPIC_TELE = "greenhouse/A1/telemetry"
TOPIC_IRR = "greenhouse/A1/ml/irrigation"
TOPIC_ALERT = "greenhouse/A1/alerts"

# load models
rf = joblib.load("../models/irrigation_rf.pkl")
iso = joblib.load("../models/anomaly_iforest.pkl")

client = mqtt.Client()
client.connect(MQTT_BROKER, 1883, 60)

def compute_features(payload):
    # expects payload keys: T,RH,soil_theta,PPFD,ext_T,ts
    return {
        'soil_lag1': payload.get('soil_theta_prev', payload['soil_theta']),
        'soil_roll_6': payload.get('soil_roll_6', payload['soil_theta']),
        'ppfd_roll_6': payload.get('ppfd_roll_6', payload['PPFD']),
        'T': payload['T'], 'RH': payload['RH'], 'ext_T': payload['ext_T'],
        'hour': pd.to_datetime(payload['ts']).hour + pd.to_datetime(payload['ts']).minute/60.0
    }

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        feats = compute_features(payload)
        X = [[feats['soil_lag1'], feats['soil_roll_6'], feats['ppfd_roll_6'],
              feats['T'], feats['RH'], feats['ext_T'], feats['hour']]]
        pred_soil = float(rf.predict(X)[0])
        client.publish(TOPIC_IRR, json.dumps({"ts": payload['ts'], "pred_soil_6h": pred_soil}))
        # anomaly check
        anom_features = [payload['T'], payload['RH'], payload['soil_theta'], payload['PPFD'], payload['CO2']]
        is_anom = iso.predict([anom_features])[0] == -1
        if is_anom:
            client.publish(TOPIC_ALERT, json.dumps({"ts":payload['ts'], "type":"anomaly", "msg":"anomaly detected"}))
    except Exception as e:
        print("Error in on_message:", e)

client.subscribe(TOPIC_TELE)
client.on_message = on_message
print("Inference service running. Subscribed to", TOPIC_TELE, "broker:", MQTT_BROKER)
client.loop_forever()
