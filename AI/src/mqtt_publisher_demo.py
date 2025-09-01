"""
Publish rows from the CSV (from config['training']['data_path']) to the telemetry topic.
Improvements over the original:
 - robust config & path resolution
 - safe parsing of timestamps and numeric columns
 - optional MQTT credentials support from config
 - starts paho network loop (loop_start) so publishes actually go out
 - uses logging and graceful shutdown
 - supports MQTT_PORT and PUBLISH_RATE via env
"""
from pathlib import Path
import os
import json
import time
import logging
import traceback

import pandas as pd
import paho.mqtt.client as mqtt
import yaml

# ---------- Configuration ----------
THIS_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = os.environ.get("CONFIG_PATH") or (THIS_DIR.parent / "config.yaml")

# Logging
LOG = logging.getLogger("demo_publisher")
LOG.setLevel(logging.INFO)
if not LOG.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    LOG.addHandler(ch)

def load_config(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"config.yaml not found at: {path}")
    with path.open("r") as f:
        cfg = yaml.safe_load(f) or {}
    return cfg

try:
    config = load_config(Path(DEFAULT_CONFIG_PATH))
except Exception as e:
    LOG.error("Failed to load config: %s", e)
    raise

# Data path (resolve relative paths to repo root (one level up from script) for convenience)
data_path = Path(config.get("training", {}).get("data_path", ""))
if not data_path:
    raise SystemExit("config['training']['data_path'] is missing")
if not data_path.is_absolute():
    # assume path relative to project root (THIS_DIR.parent)
    data_path = (THIS_DIR.parent / data_path).resolve()

if not data_path.exists():
    raise SystemExit(f"Data file not found: {data_path}")

TOPIC_TELE = config.get("inference", {}).get("telemetry_topic", "greenhouse/A1/telemetry")
BROKER = os.environ.get("MQTT_BROKER", config.get("inference", {}).get("mqtt_broker", "broker.hivemq.com"))
MQTT_PORT = int(os.environ.get("MQTT_PORT", config.get("inference", {}).get("mqtt_port", 1883)))
PUBLISH_RATE = float(os.environ.get("PUBLISH_RATE", "0.1"))  # seconds between messages
QOS = int(os.environ.get("MQTT_QOS", "1"))

# Optional auth in config:
MQTT_USER = config.get("inference", {}).get("mqtt_user")
MQTT_PASS = config.get("inference", {}).get("mqtt_pass")

# ---------- Helpers ----------
def safe_float(v):
    """Return float(v) or None if NaN/None/unconvertible."""
    try:
        if pd.isna(v):
            return None
        return float(v)
    except Exception:
        return None

def safe_iso_ts(ts_val):
    """Return ISO timestamp string. If ts_val is NaT/NaN/None, return current UTC ISO."""
    try:
        if pd.isna(ts_val):
            return pd.Timestamp.utcnow().isoformat() + "Z"
        return pd.to_datetime(ts_val, utc=True).isoformat()
    except Exception:
        return pd.Timestamp.utcnow().isoformat() + "Z"

# ---------- Read data ----------
LOG.info("Reading data from %s", data_path)
df = pd.read_csv(data_path, parse_dates=['ts'])

required_cols = {"ts", "T", "RH", "soil_theta", "PPFD", "CO2", "ext_T"}
missing = required_cols - set(df.columns)
if missing:
    LOG.error("Missing required columns in CSV: %s", missing)
    raise SystemExit("CSV missing required columns")

# Optionally drop rows with missing essential telemetry (or choose to fill)
# Here we drop rows missing the essential trio (ts, T, RH, soil_theta)
df = df.dropna(subset=["T", "RH", "soil_theta"])

# ---------- MQTT setup ----------
client = mqtt.Client()
if MQTT_USER:
    client.username_pw_set(MQTT_USER, MQTT_PASS)

# last will: announce offline status in the telemetry topic (or separate status topic if you prefer)
client.will_set(
    TOPIC_TELE,
    payload=json.dumps({"status": "offline", "ts": pd.Timestamp.utcnow().isoformat() + "Z"}),
    qos=QOS,
    retain=False,
)

try:
    client.connect(BROKER, MQTT_PORT, keepalive=60)
except Exception as e:
    LOG.error("Unable to connect to MQTT broker %s:%d - %s", BROKER, MQTT_PORT, e)
    raise

client.loop_start()  # start network thread (important)

LOG.info("Publishing to broker %s:%d topic=%s (rate=%.3fs, qos=%d)", BROKER, MQTT_PORT, TOPIC_TELE, PUBLISH_RATE, QOS)

# ---------- Publish loop ----------
published = 0
try:
    for i, row in df.iterrows():
        try:
            payload = {
                "ts": safe_iso_ts(row["ts"]),
                "T": safe_float(row["T"]),
                "RH": safe_float(row["RH"]),
                "soil_theta": safe_float(row["soil_theta"]),
                "PPFD": safe_float(row["PPFD"]),
                "CO2": safe_float(row["CO2"]),
                "ext_T": safe_float(row["ext_T"]),
            }
            # remove keys with None if you prefer not to send nulls
            # payload = {k: v for k, v in payload.items() if v is not None}

            info = client.publish(TOPIC_TELE, json.dumps(payload), qos=QOS)
            # info is MQTTMessageInfo. If you want to wait until it's published:
            # info.wait_for_publish(timeout=1.0)
            published += 1

            if published % 100 == 0:
                LOG.info("Published %d messages so far...", published)

            time.sleep(PUBLISH_RATE)
        except Exception as row_err:
            LOG.exception("Failed to publish row %d: %s", i, row_err)
            # continue publishing remaining rows
except KeyboardInterrupt:
    LOG.info("Interrupted by user")
except Exception as e:
    LOG.error("Fatal error during publishing: %s", e)
    LOG.error(traceback.format_exc())
finally:
    # clean up
    LOG.info("Published %d messages, shutting down MQTT client...", published)
    client.loop_stop()
    try:
        client.disconnect()
    except Exception:
        pass
    LOG.info("Done.")
