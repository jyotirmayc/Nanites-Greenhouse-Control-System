"""
Cloud controller: subscribes to telemetry, runs ML models, decides actions, and publishes `cmd` messages.
It expects models in ../models produced by train scripts nd reads config.yaml for setpoints and horizons.
"""
import os, json, uuid
from datetime import datetime, timezone, timedelta
import pickle
import paho.mqtt.client as mqtt

from utils import load_config, duration_from_delta, safe_parse_timestamp, rolling_features

cfg = load_config("../config.yaml")
MODEL_DIR = cfg['model_dir']
BAY = "A1"
MQTT_BROKER = os.environ.get("MQTT_BROKER", "broker.hivemq.com")
TOPIC_TELE = f"greenhouse/{BAY}/telemetry"
TOPIC_CMD  = f"greenhouse/{BAY}/cmd"
TOPIC_ALERT = f"greenhouse/{BAY}/alerts"

# Load models
if not os.path.exists(MODEL_DIR):
    raise FileNotFoundError(f"Expected models not found in {MODEL_DIR}")
with open(os.path.join(MODEL_DIR, "irrigation_rf.pkl"), "rb") as f:
    irrig_model = pickle.load(f)
with open(os.path.join(MODEL_DIR, "anomaly_iforest.pkl"), "rb") as f:
    anom_model = pickle.load(f)

# Decision mapping parameters (tune in config.yaml or change here)
T_SET = cfg.get('control',{}).get('T_set', 24.0)
T_DEADBAND = cfg.get('control',{}).get('T_deadband', 1.0)
SOIL_MIN = cfg.get('control',{}).get('soil_min', 0.28)
SOIL_TARGET = cfg.get('control',{}).get('soil_target', 0.32)
IRRIGATION_MAX_SEC = cfg.get('control',{}).get('irrigation_max_sec', 60)
IRRIGATION_MIN_SEC = cfg.get('control',{}).get('irrigation_min_sec', 8)
CMD_EXPIRES_S = cfg.get('control',{}).get('cmd_expires_s', 180)

# MQTT setup
try:
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
except AttributeError:
    client = mqtt.Client()
import time
while True:
    try:
        client.connect(MQTT_BROKER, 1883, 60)
        break
    except Exception as e:
        print(f"MQTT connect failed: {e}. Retrying in 5s...")
        time.sleep(5)


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



def decide_actions_from_telemetry(payload):
    soil = payload.get('soil_theta')
    t    = payload.get('T',   0.0)  # ponytail: default 0.0 to avoid None -> sklearn ValueError
    rh   = payload.get('RH',  0.0)
    ppfd = payload.get('PPFD', 0.0)
    ext_T = payload.get('ext_T', t)
    hour = safe_parse_timestamp(payload.get('ts'))
    # Compute rolling features server-side — ESP32 only sends instantaneous readings.
    # rolling_features() maintains a 60-min time buffer matching train_irrigation.py FE.
    soil_lag1, soil_roll_6, ppfd_roll_6 = rolling_features(soil if soil is not None else 0.0, ppfd)

    X = [[soil_lag1, soil_roll_6, ppfd_roll_6, t, rh, ext_T, hour]]
    pred_soil_6h = float(irrig_model.predict(X)[0])

    actions = {}

    print(f"[{now_iso()}] DEBUG: soil={soil}, SOIL_MIN={SOIL_MIN}, current_critical={soil < SOIL_MIN if soil is not None else 'None'}")
    print(f"[{now_iso()}] DEBUG: pred_soil_6h={pred_soil_6h}, predicted_low={pred_soil_6h < SOIL_MIN}")

    # HYBRID IRRIGATION LOGIC: Use both current and predicted soil
    # If current soil is critically low OR predicted soil is low, irrigate
    if (soil is not None and soil < SOIL_MIN) or pred_soil_6h < SOIL_MIN:
        if soil is not None and soil < SOIL_MIN:
            delta = SOIL_TARGET - soil  # Base on current soil
            print(f"[{now_iso()}] CRITICAL: Current soil {soil:.3f} < {SOIL_MIN} - Immediate irrigation needed")
        else:
            delta = SOIL_TARGET - pred_soil_6h  # Base on predicted soil
            print(f"[{now_iso()}] PREDICTIVE: Predicted soil {pred_soil_6h:.3f} < {SOIL_MIN} - Preventive irrigation")
            
        secs = duration_from_delta(delta, min_sec=IRRIGATION_MIN_SEC, max_sec=IRRIGATION_MAX_SEC)
        print(f"[{now_iso()}] DEBUG: delta={delta}, secs={secs}")
        if secs > 0:
            actions['irrigation'] = {"action":"on", "duration_s": secs}
            print(f"[{now_iso()}] IRRIGATION: {secs}s command generated")
    # Temperature control: simple mapping using current temp (cloud can do advanced later)
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
        print(f"[{now_iso()}] DEBUG: Received payload: {payload}")
        
        # Process the telemetry and generate actions
        actions, pred_soil = decide_actions_from_telemetry(payload)
        print(f"[{now_iso()}] DEBUG: Generated actions: {actions}, pred_soil: {pred_soil}")
        
        if actions:
            cmd = make_cmd(actions, source="cloud")
            client.publish(TOPIC_CMD, json.dumps(cmd))
            print(f"[{now_iso()}] Published CMD: {cmd['cmd_id']} actions={list(actions.keys())}")
        else:
            print(f"[{now_iso()}] No actions generated from payload")
            
    except Exception as e:
        print(f"[{now_iso()}] Error in on_message: {e}")
        print(f"[{now_iso()}] Continuing to process next message...")

client.subscribe(TOPIC_TELE)
client.on_message = on_message
print("Cloud controller running. Subscribed to", TOPIC_TELE)
client.loop_forever()
