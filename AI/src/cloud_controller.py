# cloud_controller.py
"""
Cloud controller: subscribes to telemetry, runs ML models, decides actions, and publishes `cmd` messages.
Run this on your cloud VM (or laptop for demo). It expects models in ../models produced by train scripts
and reads config.yaml for setpoints and horizons.
"""
import os, json, time, uuid
from datetime import datetime, timezone, timedelta
import joblib
import paho.mqtt.client as mqtt
import pandas as pd
from utils import load_config, read_csv  # reuse your utils

cfg = load_config("../config.yaml")
MODEL_DIR = cfg['model_dir']
BAY = "A1"
MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
TOPIC_TELE = f"greenhouse/{BAY}/telemetry"
TOPIC_CMD  = f"greenhouse/{BAY}/cmd"
TOPIC_ALERT = f"greenhouse/{BAY}/alerts"

# Load models with retry mechanism for cloud deployment
irrig_model_path = os.path.join(MODEL_DIR, "irrigation_rf.pkl")
anom_model_path  = os.path.join(MODEL_DIR, "anomaly_iforest.pkl")

# Wait for models to be available (training might still be in progress)
max_retries = 30  # Wait up to 5 minutes
retry_count = 0
while retry_count < max_retries:
    if os.path.exists(irrig_model_path) and os.path.exists(anom_model_path):
        try:
            irrig_model = joblib.load(irrig_model_path)
            anom_model = joblib.load(anom_model_path)
            print(f"✅ Models loaded successfully after {retry_count} retries")
            break
        except Exception as e:
            print(f"⚠️ Model loading failed (attempt {retry_count + 1}): {e}")
            time.sleep(10)
            retry_count += 1
    else:
        print(f"⏳ Waiting for models to be trained... (attempt {retry_count + 1})")
        time.sleep(10)
        retry_count += 1

if retry_count >= max_retries:
    raise FileNotFoundError("Models not available after waiting - training may have failed")

# Decision mapping parameters (tune in config.yaml or change here)
T_SET = cfg.get('control',{}).get('T_set', 24.0)
T_DEADBAND = cfg.get('control',{}).get('T_deadband', 1.0)
SOIL_MIN = cfg.get('control',{}).get('soil_min', 0.28)
SOIL_TARGET = cfg.get('control',{}).get('soil_target', 0.32)
IRRIGATION_MAX_SEC = cfg.get('control',{}).get('irrigation_max_sec', 60)
IRRIGATION_MIN_SEC = cfg.get('control',{}).get('irrigation_min_sec', 8)
CMD_EXPIRES_S = cfg.get('control',{}).get('cmd_expires_s', 180)

# MQTT setup
client = mqtt.Client()
client.connect(MQTT_BROKER, 1883, 60)

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def make_cmd(actions, source="cloud", expires_s=CMD_EXPIRES_S):
    cmd = {
        "ts": now_iso(),
        "source": source,
        "cmd_id": str(uuid.uuid4()),
        "actions": actions,
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=expires_s)).isoformat()
    }
    return cmd

def duration_from_delta(delta):  # heuristic: map predicted deficit to seconds
    # delta: positive amount of soil fraction needed (soil_target - pred_soil)
    # map 0.01 VWC -> 15s, scaled, clamp
    if delta <= 0:
        return 0
    secs = (delta / 0.01) * 15.0
    secs = max(IRRIGATION_MIN_SEC, min(IRRIGATION_MAX_SEC, secs))
    return int(secs)

def decide_actions_from_telemetry(payload):
    # payload is dictionary with keys: T, RH, soil_theta (0-1), PPFD, CO2 (optional)
    # Build features for irrigation model (same FE used in training)
    # NOTE: We assume incoming payload includes rolling features where possible; otherwise use simple lags
    soil = payload.get('soil_theta')
    t = payload.get('T')
    rh = payload.get('RH')
    ppfd = payload.get('PPFD', 0.0)
    # Build minimal feature vector used during training:
    # ['soil_lag1','soil_roll_6','ppfd_roll_6','T','RH','ext_T','hour']
    soil_lag1 = payload.get('soil_theta_prev', soil)
    soil_roll_6 = payload.get('soil_roll_6', soil)
    ppfd_roll_6 = payload.get('ppfd_roll_6', ppfd)
    ext_T = payload.get('ext_T', t)
    hour = pd.to_datetime(payload.get('ts')).hour if payload.get('ts') else datetime.now().hour

    X = [[soil_lag1, soil_roll_6, ppfd_roll_6, t, rh, ext_T, hour]]
    pred_soil_6h = float(irrig_model.predict(X)[0])

    actions = {}

    # Irrigation decision: if predicted soil after horizon < soil_min -> run pump
    if pred_soil_6h < SOIL_MIN:
        delta = SOIL_TARGET - pred_soil_6h
        secs = duration_from_delta(delta)
        if secs > 0:
            actions['irrigation'] = {"action":"on", "duration_s": secs}
    # Temperature control: simple mapping using current temp (cloud can do advanced later)
    if t is not None:
        if t > T_SET + T_DEADBAND:
            actions['fan'] = {"action":"set", "duty": 1.0}
        elif t < T_SET - T_DEADBAND:
            actions['fan'] = {"action":"set", "duty": 0.0}
    # CO2: if absent or proxy, we skip; if high CO2 -> do nothing; if low, cloud may enrich (skip here)
    # Anomaly detection -> publish alert and potentially safe-mode action
    anom_input = [payload.get('T',0), payload.get('RH',0), payload.get('soil_theta',0), payload.get('PPFD',0), payload.get('CO2',0)]
    is_anom = anom_model.predict([anom_input])[0] == -1
    if is_anom:
        # publish alert and add safe actions: open vents (fan on), stop irrigation
        client.publish(TOPIC_ALERT, json.dumps({"ts": now_iso(), "type":"anomaly", "detail":"multivariate anomaly detected"}))
        actions.setdefault('fan', {"action":"set","duty":1.0})
        # add safe mode flag -- ESP should interpret safe or we just avoid commanding pump
        actions['safety'] = {"action":"safe_mode"}

    return actions, pred_soil_6h

# MQTT callback to receive telemetry (subscribe)
def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        actions, pred_soil = decide_actions_from_telemetry(payload)
        if actions:
            cmd = make_cmd(actions, source="cloud")
            client.publish(TOPIC_CMD, json.dumps(cmd))
            print(f"[{now_iso()}] Published CMD: {cmd['cmd_id']} actions={list(actions.keys())}")
        else:
            # optionally publish no-op or status
            pass
    except Exception as e:
        print("Error in on_message:", e)

client.subscribe(TOPIC_TELE)
client.on_message = on_message
print("Cloud controller running. Subscribed to", TOPIC_TELE)
client.loop_forever()
