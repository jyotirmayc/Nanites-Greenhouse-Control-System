# infer_service.py
# Improved inference + alert + optional cmd publisher for greenhouse demo
# Usage:
#   set env MQTT_BROKER, MQTT_PORT, PUBLISH_CMDS (1/0), SOIL_THRESHOLD (0-1), CMD_EXPIRES_S, LOG_DIR, MODEL_DIR
#   python infer_service.py

import os
import json
import uuid
import time
import joblib
import logging
import traceback
from datetime import datetime, timezone, timedelta
import signal
import yaml

import pandas as pd
import paho.mqtt.client as mqtt

# ----------------------
# Configuration
# ----------------------
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG_PATH = os.path.join(THIS_DIR, "..", "config.yaml")

def load_config(path: str = DEFAULT_CONFIG_PATH) -> dict:
    if not os.path.exists(path):
        raise FileNotFoundError(f"config.yaml not found at: {path}")
    with open(path, "r") as f:
        cfg = yaml.safe_load(f) or {}
    # Basic sanity
    for k in ["inference", "model"]:
        if k not in cfg:
            raise KeyError(f"Missing top-level key '{k}' in config.yaml")
    return cfg

config = load_config()

MQTT_BROKER = os.environ.get("MQTT_BROKER")
if not MQTT_BROKER or MQTT_BROKER.startswith("${") or MQTT_BROKER == "${MQTT_BROKER:-localhost}":
    MQTT_BROKER = config["inference"].get("mqtt_broker", "localhost")
port_str = os.environ.get("MQTT_PORT", str(config["inference"].get("mqtt_port", 1883)))
try:
    MQTT_PORT = int(port_str)
except ValueError:
    MQTT_PORT = 1883  # fallback to default
PUBLISH_CMDS = os.environ.get("PUBLISH_CMDS", "1").lower() in ("1", "true", "yes")
SOIL_THRESHOLD = float(os.environ.get("SOIL_THRESHOLD", "0.30"))  # if pred_soil < this -> cmd
CMD_EXPIRES_S = int(os.environ.get("CMD_EXPIRES_S", "120"))
LOG_DIR = os.environ.get("LOG_DIR", os.path.join(THIS_DIR, "..", "logs"))
MODEL_DIR = os.environ.get("MODEL_DIR", os.path.join(THIS_DIR, "..", "models"))

TOPIC_TELE = config["inference"].get("telemetry_topic", "greenhouse/A1/tele")
TOPIC_IRR  = config["inference"].get("irrigation_topic", "greenhouse/A1/pred")
TOPIC_ALERT= config["inference"].get("alert_topic", "greenhouse/A1/alert")
TOPIC_CMD  = config["inference"].get("cmd_topic", "greenhouse/A1/cmd")

rf_path  = config["model"]["irrigation"]["path"]
iso_path = config["model"]["anomaly"]["path"]

# Resolve model paths relative to MODEL_DIR if given as basenames
if not os.path.isabs(rf_path):
    rf_path = os.path.join(MODEL_DIR, rf_path)
if not os.path.isabs(iso_path):
    iso_path = os.path.join(MODEL_DIR, iso_path)

# ----------------------
# Logging setup
# ----------------------
os.makedirs(LOG_DIR, exist_ok=True)
log_path = os.path.join(LOG_DIR, "infer_service.log")

logger = logging.getLogger("infer_service")
logger.setLevel(logging.DEBUG)
if not logger.handlers:  # prevent duplicate handlers if re-imported
    fmt = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")

    fh = logging.FileHandler(log_path)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

logger.info("Starting infer_service")
logger.info(f"MQTT broker = {MQTT_BROKER}:{MQTT_PORT}, publish_cmds = {PUBLISH_CMDS}")

# ----------------------
# Load models
# ----------------------
if not os.path.exists(rf_path) or not os.path.exists(iso_path):
    logger.error(f"Model files not found. Expected: {rf_path}, {iso_path}")
    raise SystemExit("Missing model files. Train models or place them in ../models")

try:
    rf = joblib.load(rf_path)
    iso = joblib.load(iso_path)
    logger.info("Loaded models successfully.")
except Exception as e:
    logger.error("Failed to load models: %s", e)
    logger.error(traceback.format_exc())
    raise

# ----------------------
# Utility functions
# ----------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def parse_ts_utc_iso(ts_val) -> str:
    """
    Returns an ISO 8601 UTC string. Robust to epoch seconds, ISO strings, pandas Timestamps.
    """
    try:
        if ts_val is None:
            return now_iso()
        if isinstance(ts_val, (int, float)):
            return datetime.fromtimestamp(ts_val, tz=timezone.utc).isoformat()
        # Parse any string/ts; force UTC (assume naive is UTC)
        ts = pd.to_datetime(ts_val, utc=True)
        return ts.isoformat()
    except Exception:
        return now_iso()

def duration_from_delta(delta: float, min_sec: int = 8, max_sec: int = 60) -> int:
    """
    Heuristic mapping: 0.01 VWC deficit -> ~15s; scale and clamp.
    """
    if delta <= 0:
        return 0
    secs = (delta / 0.01) * 15.0
    secs = max(min_sec, min(max_sec, secs))
    return int(secs)

def build_cmd(irrig_secs: int | None = None, fan_duty: float | None = None, source: str = "cloud") -> dict:
    cmd = {
        "ts": now_iso(),
        "source": source,
        "cmd_id": str(uuid.uuid4()),
        "actions": {},
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=CMD_EXPIRES_S)).isoformat(),
    }
    if irrig_secs and irrig_secs > 0:
        cmd["actions"]["irrigation"] = {"action": "on", "duration_s": int(irrig_secs)}
    if fan_duty is not None:
        cmd["actions"]["fan"] = {"action": "set", "duty": float(fan_duty)}
    return cmd

# ----------------------
# MQTT callbacks
# ----------------------
# Ensure compatibility with paho-mqtt 2.x using v3-style callbacks
client = mqtt.Client(
    protocol=mqtt.MQTTv311
)

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("Connected to MQTT broker.")
        client.subscribe(TOPIC_TELE)
        logger.info("Subscribed to topic: %s", TOPIC_TELE)
    else:
        logger.error("Failed to connect to MQTT, return code %d", rc)

def on_disconnect(client, userdata, rc):
    logger.warning("Disconnected from MQTT (rc=%s).", rc)

def compute_features(payload: dict) -> dict | None:
    """
    Safe feature building. Expects payload to be dict with optional keys.
    Returns None if essential inputs missing.
    """
    try:
        # Essential: soil_theta, T, RH
        soil = payload.get("soil_theta", payload.get("soil"))
        T = payload.get("T")
        RH = payload.get("RH")
        PPFD = payload.get("PPFD", payload.get("light", 0.0))
        ext_T = payload.get("ext_T", T if T is not None else 0.0)
        ts_in = payload.get("ts")

        if soil is None or T is None or RH is None:
            missing = [k for k in ("soil_theta", "T", "RH") if payload.get(k) is None and (k != "soil_theta" or payload.get("soil") is None)]
            logger.warning("Telemetry missing essential keys: %s", missing)
            return None

        # Single parse; hour in UTC fractional
        ts_iso = parse_ts_utc_iso(ts_in)
        ts_parsed = pd.to_datetime(ts_iso, utc=True)
        hour = ts_parsed.hour + ts_parsed.minute / 60.0

        soil_lag1 = payload.get("soil_theta_prev", soil)
        soil_roll_6 = payload.get("soil_roll_6", soil)
        ppfd_roll_6 = payload.get("ppfd_roll_6", PPFD)

        feats = {
            "soil_lag1": float(soil_lag1),
            "soil_roll_6": float(soil_roll_6),
            "ppfd_roll_6": float(ppfd_roll_6),
            "T": float(T),
            "RH": float(RH),
            "ext_T": float(ext_T),
            "hour": float(hour),
            "ts_iso": ts_iso,  # pass-through for downstream publishing
        }
        return feats
    except Exception as e:
        logger.error("Error computing features: %s", e)
        logger.error(traceback.format_exc())
        return None

def on_message(client, userdata, msg):
    try:
        payload_raw = msg.payload.decode()
        payload = json.loads(payload_raw)
    except Exception as e:
        logger.error("Failed to parse JSON payload: %s; raw: %s", e, msg.payload)
        return

    feats = compute_features(payload)
    if feats is None:
        logger.info("Skipping inference due to missing features.")
        return

    ts_iso = feats.pop("ts_iso", now_iso())
    logger.debug("Received telemetry ts=%s payload_keys=%s", ts_iso, list(payload.keys()))

    try:
        X = [[
            feats['soil_lag1'],
            feats['soil_roll_6'],
            feats['ppfd_roll_6'],
            feats['T'],
            feats['RH'],
            feats['ext_T'],
            feats['hour'],
        ]]
        pred_soil = float(rf.predict(X)[0])
        irr_msg = {"ts": ts_iso, "pred_soil_6h": pred_soil}
        client.publish(TOPIC_IRR, json.dumps(irr_msg))  # add qos=1 if you want delivery guarantee
        logger.info("Published prediction pred_soil_6h=%.4f to %s", pred_soil, TOPIC_IRR)

        # anomaly detection (safe vector with defaults)
        anom_vec = [
            float(payload.get("T", 0.0)),
            float(payload.get("RH", 0.0)),
            float(payload.get("soil_theta", payload.get("soil", 0.0))),
            float(payload.get("PPFD", payload.get("light", 0.0))),
            float(payload.get("CO2", 0.0)),
        ]
        try:
            is_anom = (iso.predict([anom_vec])[0] == -1)
        except Exception as e:
            logger.error("Anomaly model error: %s", e)
            is_anom = False

        if is_anom:
            alert = {"ts": ts_iso, "type": "anomaly", "msg": "anomaly detected by isoFOREST"}
            client.publish(TOPIC_ALERT, json.dumps(alert))
            logger.warning("Published anomaly alert: %s", alert)

        # Optionally publish actionable command when pred_soil below threshold
        if PUBLISH_CMDS and pred_soil < SOIL_THRESHOLD:
            deficit = SOIL_THRESHOLD - pred_soil
            secs = duration_from_delta(deficit)
            if secs > 0:
                cmd = build_cmd(irrig_secs=secs, source="cloud")
                client.publish(TOPIC_CMD, json.dumps(cmd))
                logger.info("Published CMD (irrigation %ds) cmd_id=%s", secs, cmd["cmd_id"])

    except Exception as e:
        logger.error("Error running inference or publishing results: %s", e)
        logger.error(traceback.format_exc())

# ----------------------
# MQTT client setup
# ----------------------
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message
client.reconnect_delay_set(min_delay=1, max_delay=32)
client.will_set(TOPIC_ALERT, json.dumps({"ts": now_iso(), "type": "status", "msg": "infer_service offline"}), retain=False)

_stop = False
def _handle_stop(signum, frame):
    global _stop
    _stop = True
signal.signal(signal.SIGINT, _handle_stop)
signal.signal(signal.SIGTERM, _handle_stop)

def run():
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    except Exception as e:
        logger.error("Unable to connect to MQTT broker %s:%d - %s", MQTT_BROKER, MQTT_PORT, e)
        raise

    client.loop_start()
    logger.info("MQTT loop started. Waiting for telemetry...")

    try:
        while not _stop:
            time.sleep(1.0)
    except Exception as e:
        logger.error("Fatal error in main loop: %s", e)
        logger.error(traceback.format_exc())
    finally:
        client.loop_stop()
        try:
            client.disconnect()
        except Exception:
            pass
        logger.info("Clean shutdown complete.")

if __name__ == "__main__":
    run()
