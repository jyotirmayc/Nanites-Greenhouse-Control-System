"""
Pi fallback agent:
- Subscribes to telemetry and cloud cmd
- If cloud is silent for CLOUD_TIMEOUT_S, Pi runs local models
  and publishes commands (source="pi") to cmd topic
"""
import os, json, time, uuid
from datetime import datetime, timezone, timedelta
import joblib
import paho.mqtt.client as mqtt
import pandas as pd
from utils import load_config

cfg = load_config("../config.yaml")
MODEL_DIR = cfg['model_dir']
BAY = "A1"
MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
TOP_TELE = f"greenhouse/{BAY}/telemetry"
TOP_CMD = f"greenhouse/{BAY}/cmd"
TOP_CMD_CLOUD = f"greenhouse/{BAY}/cmd"
CLOUD_TIMEOUT_S = cfg.get('fallback', {}).get('cloud_timeout_s', 90)

# Load local models
irrig_model = joblib.load(os.path.join(MODEL_DIR, "irrigation_rf.pkl"))
anom_model = joblib.load(os.path.join(MODEL_DIR, "anomaly_iforest.pkl"))

last_cloud_cmd_ts = None
last_tele = None

client = mqtt.Client()
client.connect(MQTT_BROKER, 1883, 60)

def now_ts():
    return datetime.now(timezone.utc)

def publish_cmd(actions, source="pi", expires_s=120):
    cmd = {
        "ts": now_ts().isoformat(),
        "source": source,
        "cmd_id": str(uuid.uuid4()),
        "actions": actions,
        "expires_at": (now_ts() + timedelta(seconds=expires_s)).isoformat()
    }
    client.publish(TOP_CMD, json.dumps(cmd))
    print(f"[{now_ts().isoformat()}] PI published cmd {cmd['cmd_id']} actions={list(actions.keys())}")

def on_tele(client_c, userdata, msg):
    global last_tele
    last_tele = json.loads(msg.payload.decode())

def on_cmd(client_c, userdata, msg):
    global last_cloud_cmd_ts
    try:
        payload = json.loads(msg.payload.decode())
        src = payload.get('source', 'unknown')
        if src == 'cloud':
            last_cloud_cmd_ts = now_ts()
            print(f"Seen cloud cmd {payload.get('cmd_id')} at {last_cloud_cmd_ts.isoformat()}")
    except Exception as e:
        print("err on_cmd:", e)

client.on_message = lambda c, u, m: None
client.subscribe(TOP_TELE)
client.subscribe(TOP_CMD_CLOUD)
client.message_callback_add(TOP_TELE, on_tele)
client.message_callback_add(TOP_CMD_CLOUD, on_cmd)
client.loop_start()

# Control thresholds
SOIL_MIN = cfg.get('control', {}).get('soil_min', 0.28)
SOIL_TARGET = cfg.get('control', {}).get('soil_target', 0.32)
IRRIGATION_MAX_SEC = cfg.get('control', {}).get('irrigation_max_sec', 60)
IRRIGATION_MIN_SEC = cfg.get('control', {}).get('irrigation_min_sec', 8)
T_SET = cfg.get('control', {}).get('T_set', 24.0)
T_DEADBAND = cfg.get('control', {}).get('T_deadband', 1.0)

def duration_from_delta(delta):
    if delta <= 0:
        return 0
    secs = (delta / 0.01) * 15.0
    secs = max(IRRIGATION_MIN_SEC, min(IRRIGATION_MAX_SEC, secs))
    return int(secs)

while True:
    if last_cloud_cmd_ts and (now_ts() - last_cloud_cmd_ts) < timedelta(seconds=CLOUD_TIMEOUT_S):
        time.sleep(1.0)
        continue

    if last_tele is None:
        time.sleep(0.5)
        continue

    payload = last_tele
    soil = payload.get('soil_theta')
    soil_lag1 = payload.get('soil_theta_prev', soil)
    soil_roll_6 = payload.get('soil_roll_6', soil)
    ppfd_roll_6 = payload.get('ppfd_roll_6', payload.get('PPFD', 0.0))
    ext_T = payload.get('ext_T', payload.get('T', 0))
    hour = pd.to_datetime(payload.get('ts')).hour if payload.get('ts') else datetime.now().hour
    X = [[soil_lag1, soil_roll_6, ppfd_roll_6, payload.get('T'), payload.get('RH'), ext_T, hour]]
    pred_soil_6h = float(irrig_model.predict(X)[0])

    actions = {}
    if pred_soil_6h < SOIL_MIN:
        delta = SOIL_TARGET - pred_soil_6h
        secs = duration_from_delta(delta)
        if secs > 0:
            actions['irrigation'] = {"action": "on", "duration_s": secs}

    t = payload.get('T')
    if t is not None:
        if t > T_SET + T_DEADBAND:
            actions['fan'] = {"action": "set", "duty": 1.0}
        elif t < T_SET - T_DEADBAND:
            actions['fan'] = {"action": "set", "duty": 0.0}

    anom_vec = [
        payload.get('T', 0),
        payload.get('RH', 0),
        payload.get('soil_theta', 0),
        payload.get('PPFD', 0),
        payload.get('CO2', 0)
    ]
    is_anom = anom_model.predict([anom_vec])[0] == -1
    if is_anom:
        client.publish(
            f"greenhouse/{BAY}/alerts",
            json.dumps({"ts": now_ts().isoformat(), "type": "anomaly", "detail": "pi-detected"})
        )
        actions.setdefault('fan', {"action": "set", "duty": 1.0})
        actions['safety'] = {"action": "safe_mode"}

    if actions:
        publish_cmd(actions, source="pi")

    time.sleep(1.0)