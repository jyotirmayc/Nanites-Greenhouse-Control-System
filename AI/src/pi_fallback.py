"""
Pi fallback agent:
- Subscribes to telemetry and cloud cmd
- If cloud is silent for CLOUD_TIMEOUT_S, Pi runs local models
  and publishes commands (source="pi") to cmd topic
"""
import os, json, time, uuid
from datetime import datetime, timezone, timedelta
import pickle
import paho.mqtt.client as mqtt

from utils import load_config, duration_from_delta, safe_parse_timestamp, rolling_features

cfg = load_config("../config.yaml")
MODEL_DIR = cfg['model_dir']
BAY = "A1"
MQTT_BROKER = os.environ.get("MQTT_BROKER", "broker.hivemq.com")
TOP_TELE = f"greenhouse/{BAY}/telemetry"
TOP_CMD  = f"greenhouse/{BAY}/cmd"
CLOUD_TIMEOUT_S = cfg.get('fallback', {}).get('cloud_timeout_s', 90)

# Load local models
with open(os.path.join(MODEL_DIR, "irrigation_rf.pkl"), "rb") as f:
    irrig_model = pickle.load(f)
with open(os.path.join(MODEL_DIR, "anomaly_iforest.pkl"), "rb") as f:
    anom_model = pickle.load(f)

last_cloud_cmd_ts = None
last_tele = None
last_cmd_published_ts = None  # ponytail: cooldown guard — prevents command spam every 1s

try:
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
except AttributeError:
    client = mqtt.Client()
while True:
    try:
        client.connect(MQTT_BROKER, 1883, 60)
        break
    except Exception as e:
        print(f"MQTT connect failed: {e}. Retrying in 5s...")
        time.sleep(5)

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
client.subscribe(TOP_CMD)
client.message_callback_add(TOP_TELE, on_tele)
client.message_callback_add(TOP_CMD, on_cmd)
client.loop_start()

# Control thresholds
SOIL_MIN = cfg.get('control', {}).get('soil_min', 0.28)
SOIL_TARGET = cfg.get('control', {}).get('soil_target', 0.32)
IRRIGATION_MAX_SEC = cfg.get('control', {}).get('irrigation_max_sec', 60)
IRRIGATION_MIN_SEC = cfg.get('control', {}).get('irrigation_min_sec', 8)
T_SET = cfg.get('control', {}).get('T_set', 24.0)
T_DEADBAND = cfg.get('control', {}).get('T_deadband', 1.0)


while True:
    if last_cloud_cmd_ts and (now_ts() - last_cloud_cmd_ts) < timedelta(seconds=CLOUD_TIMEOUT_S):
        time.sleep(1.0)
        continue

    if last_tele is None:
        time.sleep(0.5)
        continue

    payload = last_tele
    soil = payload.get('soil_theta')
    t    = payload.get('T',   0.0)
    rh   = payload.get('RH',  0.0)
    ppfd = payload.get('PPFD', 0.0)
    ext_T = payload.get('ext_T', t)
    hour = safe_parse_timestamp(payload.get('ts'))
    # Compute rolling features server-side — matches train_irrigation.py FE.
    soil_lag1, soil_roll_6, ppfd_roll_6 = rolling_features(soil if soil is not None else 0.0, ppfd)
    X = [[soil_lag1, soil_roll_6, ppfd_roll_6, t, rh, ext_T, hour]]
    pred_soil_6h = float(irrig_model.predict(X)[0])

    actions = {}
    if pred_soil_6h < SOIL_MIN:
        delta = SOIL_TARGET - pred_soil_6h
        secs = duration_from_delta(delta, min_sec=IRRIGATION_MIN_SEC, max_sec=IRRIGATION_MAX_SEC)
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
        # Only publish if we haven't sent a command recently (cooldown = expires_s window)
        # Without this, a fresh uuid4 is generated every 1s, bypassing ESP32 dedup,
        # causing pump_end_time to be reset continuously -> indefinite irrigation.
        expires_s = 120
        if last_cmd_published_ts is None or \
           (now_ts() - last_cmd_published_ts).total_seconds() >= expires_s:
            publish_cmd(actions, source="pi", expires_s=expires_s)
            last_cmd_published_ts = now_ts()

    time.sleep(1.0)