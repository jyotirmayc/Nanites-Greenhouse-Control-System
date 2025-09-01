"""
Streamlit dashboard for greenhouse telemetry.

- Background MQTT thread collects messages into a bounded deque.
- Streamlit UI reads the deque, validates data, and renders charts/metrics.
- Uses logging (no prints), robust timestamp parsin            if col != 'timestamp':
                df_live[col] = pd.to_numeric(df_live[col], errors="coerce")
                # Replace inf/-inf with NaN, then fill
                df_live[col] = df_live[col].replace([float("inf"), float("-inf")], pd.NA)
                df_live[col] = df_live[col].ffill().fillna(0.0)
                
                # Final check: ensure no remaining inf values
                if df_live[col].isin([float("inf"), float("-inf")]).any():
                    df_live[col] = df_live[col].replace([float("inf"), float("-inf")], 0.0)fe numeric handling.
"""
from collections import deque
from threading import Thread, Lock
from pathlib import Path
from datetime import datetime, timezone, timedelta
import time
import json
import logging
import os
import signal
import pandas as pd
import paho.mqtt.client as mqtt
import streamlit as st
import yaml
import joblib
import uuid

# ---------- Configuration ----------
THIS_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = THIS_DIR.parent / "config.yaml"

LOG = logging.getLogger("io_tricity_dashboard")
if not LOG.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    LOG.addHandler(ch)
LOG.setLevel(logging.INFO)  # Reduce logging now that it's working

# Load config (fallback to sensible defaults)
try:
    with open(DEFAULT_CONFIG_PATH, "r") as f:
        cfg = yaml.safe_load(f) or {}
except Exception:
    LOG.warning("Failed to load config.yaml; using defaults")
    cfg = {}

MQTT_BROKER = os.environ.get("MQTT_BROKER", "broker.hivemq.com")  # Override to public broker
MQTT_PORT = int(os.environ.get("MQTT_PORT",
                               cfg.get("inference", {}).get("mqtt_port", 1883)))
MQTT_TOPIC = cfg.get("inference", {}).get("telemetry_topic", "greenhouse/A1/telemetry")
MQTT_CMD_TOPIC = cfg.get("inference", {}).get("cmd_topic", "greenhouse/A1/cmd")
DATA_CSV_PATH = cfg.get("training", {}).get("data_path",
                                           str(THIS_DIR.parent / "data" / "synthetic_greenhouse_7days_10min.csv"))

# AI Control Configuration
MODEL_DIR = THIS_DIR.parent / "models"
IRRIGATION_MODEL_PATH = MODEL_DIR / "irrigation_rf.pkl"
ANOMALY_MODEL_PATH = MODEL_DIR / "anomaly_iforest.pkl"

# Control thresholds
SOIL_MIN = 0.28
SOIL_TARGET = 0.32
T_SET = 24.0
T_DEADBAND = 1.0
IRRIGATION_MIN_SEC = 8
IRRIGATION_MAX_SEC = 60
CMD_EXPIRES_S = 180

# Load AI models for command generation
irrigation_model = None
anomaly_model = None

try:
    if IRRIGATION_MODEL_PATH.exists():
        irrigation_model = joblib.load(IRRIGATION_MODEL_PATH)
        LOG.info("Loaded irrigation model from %s", IRRIGATION_MODEL_PATH)
    else:
        LOG.warning("Irrigation model not found at %s", IRRIGATION_MODEL_PATH)
except Exception as e:
    LOG.error("Failed to load irrigation model: %s", e)

try:
    if ANOMALY_MODEL_PATH.exists():
        anomaly_model = joblib.load(ANOMALY_MODEL_PATH)
        LOG.info("Loaded anomaly model from %s", ANOMALY_MODEL_PATH)
    else:
        LOG.warning("Anomaly model not found at %s", ANOMALY_MODEL_PATH)
except Exception as e:
    LOG.error("Failed to load anomaly model: %s", e)

# Buffer settings
MAX_MESSAGES = int(os.environ.get("MAX_MESSAGES", "1000"))

# ---------- Shared state ----------
data_queue = deque(maxlen=MAX_MESSAGES)
data_lock = Lock()
_stop_flag = False  # used for graceful shutdown of background thread

# ---------- Helpers ----------
def safe_float(v, default=0.0):
    try:
        if v is None:
            return default
        f = float(v)
        if pd.isna(f) or f in (float("inf"), float("-inf")):
            return default
        return f
    except Exception:
        return default

def parse_timestamp(ts_val):
    """Return a pandas.Timestamp in UTC. Accept numeric epoch, ISO string, or pandas Timestamp."""
    try:
        if ts_val is None:
            return pd.Timestamp.utcnow()
        
        # Handle ESP32 format: numeric seconds since boot (string like "134")
        if isinstance(ts_val, str) and ts_val.isdigit():
            # ESP32 sends seconds since boot, convert to actual timestamp
            # Use current time as reference and create meaningful timestamp
            boot_seconds = float(ts_val)
            current_time = pd.Timestamp.utcnow()
            # Create timestamp based on boot time (approximate)
            return current_time - pd.Timedelta(seconds=max(0, 300 - boot_seconds))
            
        # numeric seconds or milliseconds
        if isinstance(ts_val, (int, float)):
            # assume seconds if value < 1e12, milliseconds otherwise
            if ts_val > 1e12:
                return pd.to_datetime(ts_val, unit="ms", utc=True)
            elif ts_val > 0:
                return pd.to_datetime(ts_val, unit="s", utc=True)
            else:
                # Handle small values like ESP32 boot seconds
                current_time = pd.Timestamp.utcnow()
                return current_time - pd.Timedelta(seconds=max(0, 300 - ts_val))
                
        # string or pandas timestamp - try to parse as datetime
        return pd.to_datetime(ts_val, utc=True)
        
    except Exception as e:
        LOG.debug(f"Timestamp parsing failed for {ts_val}: {e}")
        return pd.Timestamp.utcnow()

def normalize_for_plot(df, columns):
    """Scale columns 0-100 for comparison; ignore constant columns."""
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            continue
        mn, mx = out[col].min(), out[col].max()
        if pd.isna(mn) or pd.isna(mx) or mx <= mn:
            out[col] = 50.0
        else:
            out[col] = (out[col] - mn) / (mx - mn) * 100.0
    return out

# ---------- AI Control Functions ----------
def now_iso():
    return datetime.now(timezone.utc).isoformat()

def duration_from_delta(delta):
    """Map predicted deficit to irrigation seconds"""
    if delta <= 0:
        return 0
    secs = (delta / 0.01) * 15.0
    secs = max(IRRIGATION_MIN_SEC, min(IRRIGATION_MAX_SEC, secs))
    return int(secs)

def make_cmd(actions, source="cloud"):
    """Create MQTT command JSON"""
    cmd = {
        "ts": now_iso(),
        "source": source,
        "cmd_id": str(uuid.uuid4()),
        "actions": actions,
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=CMD_EXPIRES_S)).isoformat()
    }
    return cmd

def decide_actions_from_telemetry(payload):
    """AI decision logic - returns (actions dict, pred_soil)"""
    if not irrigation_model or not anomaly_model:
        return {}, 0.0
        
    try:
        # Extract sensor data
        soil = safe_float(payload.get('soil_theta', 0))
        t = safe_float(payload.get('T', 20))
        rh = safe_float(payload.get('RH', 50))
        ppfd = safe_float(payload.get('PPFD', 0))
        co2 = safe_float(payload.get('CO2', 400))
        ext_T = safe_float(payload.get('ext_T', t))
        
        # Build features for irrigation model
        soil_lag1 = payload.get('soil_theta_prev', soil)
        soil_roll_6 = payload.get('soil_roll_6', soil)  
        ppfd_roll_6 = payload.get('ppfd_roll_6', ppfd)
        hour = pd.to_datetime(payload.get('ts')).hour if payload.get('ts') else datetime.now().hour

        X = [[soil_lag1, soil_roll_6, ppfd_roll_6, t, rh, ext_T, hour]]
        pred_soil_6h = float(irrigation_model.predict(X)[0])

        actions = {}

        # Irrigation decision
        if pred_soil_6h < SOIL_MIN:
            delta = SOIL_TARGET - pred_soil_6h
            secs = duration_from_delta(delta)
            if secs > 0:
                actions['irrigation'] = {"action": "on", "duration_s": secs}

        # Temperature control
        if t > T_SET + T_DEADBAND:
            actions['fan'] = {"action": "set", "duty": 1.0}
        elif t < T_SET - T_DEADBAND:
            actions['fan'] = {"action": "set", "duty": 0.0}

        # Anomaly detection
        anom_input = [[t, rh, soil, ppfd, co2]]
        is_anom = anomaly_model.predict(anom_input)[0] == -1
        if is_anom:
            actions.setdefault('fan', {"action": "set", "duty": 1.0})
            actions['safety'] = {"action": "safe_mode"}
            LOG.warning("Anomaly detected! Activating safety mode.")

        return actions, pred_soil_6h
        
    except Exception as e:
        LOG.error("Error in AI decision logic: %s", e)
        return {}, 0.0

def publish_command(client, actions):
    """Publish AI command to ESP32"""
    if not actions:
        return
        
    try:
        cmd = make_cmd(actions, source="dashboard_ai")
        cmd_json = json.dumps(cmd)
        result = client.publish(MQTT_CMD_TOPIC, cmd_json, qos=1)
        LOG.info("🤖 AI Command sent: %s -> %s", cmd['cmd_id'], list(actions.keys()))
        return True
    except Exception as e:
        LOG.error("Failed to publish command: %s", e)
        return False

# ---------- MQTT background worker ----------
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        LOG.info("Connected to MQTT broker %s:%d", MQTT_BROKER, MQTT_PORT)
        client.subscribe(MQTT_TOPIC)
        LOG.info("Subscribed to topic %s", MQTT_TOPIC)
    else:
        LOG.error("Failed to connect to MQTT broker (rc=%s)", rc)

def on_disconnect(client, userdata, flags, rc, properties=None):
    LOG.warning("MQTT disconnected (rc=%s)", rc)

def on_mqtt_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        LOG.debug("Received MQTT payload: %s", payload)
    except Exception as e:
        LOG.debug("Received non-JSON payload; ignoring: %s", e)
        return

    # required telemetry keys (relaxed)
    required = {"ts", "T", "RH", "soil_theta", "PPFD", "CO2"}
    # Accept if at least these keys in payload
    if not required.issubset(payload.keys()):
        LOG.debug("Telemetry missing required fields: %s", required - set(payload.keys()))
        return

    # parse/convert fields
    try:
        ts = parse_timestamp(payload.get("ts"))
        record = {
            "ts": ts,
            "T": safe_float(payload.get("T")),
            "RH": safe_float(payload.get("RH")),
            "soil_theta": safe_float(payload.get("soil_theta")),
            "PPFD": safe_float(payload.get("PPFD")),
            "CO2": safe_float(payload.get("CO2")),
            "ext_T": safe_float(payload.get("ext_T", payload.get("T"))),
            "device_id": payload.get("device_id", payload.get("bayId", "A1")),
        }
        
        LOG.debug("Processed record: %s", record)

        with data_lock:
            data_queue.append(record)
            
        # 🤖 AI CONTROL: Make decisions and send commands to ESP32
        actions, pred_soil = decide_actions_from_telemetry(payload)
        if actions:
            publish_command(client, actions)
            LOG.info("🎯 AI Decision: pred_soil=%.3f, actions=%s", pred_soil, list(actions.keys()))
            
    except Exception as e:
        LOG.error("Error processing MQTT message: %s", e)
        LOG.debug("Problematic payload: %s", payload)

def mqtt_worker(broker, port, topic, keepalive=60):
    try:
        # Use newer MQTT client API to avoid deprecation warning
        client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    except:
        # Fallback for older paho-mqtt versions
        client = mqtt.Client()
        
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_mqtt_message
    try:
        client.connect(broker, port, keepalive=keepalive)
    except Exception as e:
        LOG.error("Unable to connect to MQTT broker %s:%d -> %s", broker, port, e)
        return
    client.loop_start()
    try:
        while not _stop_flag:
            time.sleep(0.5)
    finally:
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass
        LOG.info("MQTT worker stopped")

# ---------- Start MQTT thread ----------
mqtt_thread = Thread(target=mqtt_worker, args=(MQTT_BROKER, MQTT_PORT, MQTT_TOPIC), daemon=True)
mqtt_thread.start()

# ---------- Streamlit UI ----------
st.set_page_config(page_title="IOTricity Greenhouse Dashboard", layout="wide")

st.title("IOTricity Greenhouse Dashboard")
st.subheader("Real-time environmental monitoring and control")

# connection / info card
st.sidebar.header("Connection")
st.sidebar.text(f"Broker: {MQTT_BROKER}:{MQTT_PORT}")
st.sidebar.text(f"Topic: {MQTT_TOPIC}")
st.sidebar.text(f"Cmd Topic: {MQTT_CMD_TOPIC}")
st.sidebar.text(f"Data buffer: last {MAX_MESSAGES} messages")

# AI Control Status
st.sidebar.header("🤖 AI Control")
ai_status = "🟢 ACTIVE" if (irrigation_model and anomaly_model) else "🔴 OFFLINE"
st.sidebar.text(f"Status: {ai_status}")
if irrigation_model:
    st.sidebar.text("✅ Irrigation Model Loaded")
else:
    st.sidebar.text("❌ Irrigation Model Missing")
if anomaly_model:
    st.sidebar.text("✅ Anomaly Model Loaded") 
else:
    st.sidebar.text("❌ Anomaly Model Missing")
    
st.sidebar.text(f"Soil Target: {SOIL_TARGET}")
st.sidebar.text(f"Temp Setpoint: {T_SET}°C")

# Load fallback CSV for historical view
try:
    df_csv = pd.read_csv(DATA_CSV_PATH, parse_dates=["ts"])
    LOG.info("Loaded CSV fallback data from %s", DATA_CSV_PATH)
except Exception:
    df_csv = pd.DataFrame()

# Top metrics layout
col1, col2, col3, col4 = st.columns(4)
msg_count_el = col1.empty()
last_msg_el = col2.empty()
status_el = col3.empty()
uptime_el = col4.empty()

chart_placeholder = st.empty()
latest_values_container = st.empty()

start_time = time.time()

# Auto-refresh using Streamlit's built-in rerun with delay
refresh_interval = 3  # seconds

# Main render (non-blocking): read queue snapshot and render
with data_lock:
    snapshot = list(data_queue)

    # Uptime
    uptime_seconds = int(time.time() - start_time)
    uptime_el.metric("Dashboard Uptime", f"{uptime_seconds // 3600:02d}:{(uptime_seconds % 3600) // 60:02d}:{uptime_seconds % 60:02d}")

    # Messages received
    msg_count_el.metric("Messages Received", len(snapshot))

    if snapshot:
        status_el.success("Connected and receiving live data")
        last_msg_el.metric("Last update", "Live", delta="Just now")
        df_live = pd.DataFrame(snapshot).sort_values("ts")
        
        # ensure dtype and fill - more robust cleaning
        numeric_cols = ["T", "RH", "soil_theta", "PPFD", "CO2", "ext_T"]
        for col in numeric_cols:
            if col in df_live.columns:
                df_live[col] = pd.to_numeric(df_live[col], errors="coerce")
                # Replace inf/-inf with NaN, then fill
                df_live[col] = df_live[col].replace([float("inf"), float("-inf")], pd.NA)
                df_live[col] = df_live[col].fillna(method="ffill").fillna(0.0)
                
                # Final check: ensure no remaining inf values
                if df_live[col].isin([float("inf"), float("-inf")]).any():
                    df_live[col] = df_live[col].replace([float("inf"), float("-inf")], 0.0)

        # pick last N points for plotting - DON'T set ts as index to avoid timezone issues
        df_plot = df_live.tail(200).copy()
        
        # Create time-series data for charts (use numeric index instead of datetime index)
        df_plot_indexed = df_plot.set_index(pd.RangeIndex(len(df_plot)))

        # Tabs for different metrics
        tabs = chart_placeholder.tabs(["Temperature", "Moisture & Humidity", "PPFD", "CO2", "Overview"])
        with tabs[0]:
            st.markdown("### Temperature")
            if "T" in df_plot.columns and not df_plot["T"].isna().all():
                # Use numeric data without timestamp index to avoid infinite extent errors
                temp_series = df_plot["T"].reset_index(drop=True)
                if not temp_series.empty and temp_series.notna().sum() > 0:
                    st.line_chart(temp_series, use_container_width=True)
                    st.info(f"Average temperature: {temp_series.mean():.1f} °C")
                else:
                    st.warning("No valid temperature data")
            else:
                st.warning("No valid temperature data")

        with tabs[1]:
            st.markdown("### Moisture & Humidity")
            cols = [c for c in ["soil_theta", "RH"] if c in df_plot.columns]
            if cols:
                # Create clean data without timestamp issues
                moisture_data = df_plot[cols].reset_index(drop=True)
                valid_data = moisture_data.dropna(how='all')
                
                if not valid_data.empty:
                    st.line_chart(valid_data, use_container_width=True)
                    if "soil_theta" in valid_data.columns:
                        st.metric("Avg Soil Moisture", f"{valid_data['soil_theta'].mean():.2f}")
                    if "RH" in valid_data.columns:
                        st.metric("Avg Humidity", f"{valid_data['RH'].mean():.0f}%")
                else:
                    st.warning("No valid moisture/humidity data")
            else:
                st.warning("No valid moisture/humidity data")

        with tabs[2]:
            st.markdown("### PPFD")
            if "PPFD" in df_plot.columns and not df_plot["PPFD"].isna().all():
                ppfd_series = df_plot["PPFD"].reset_index(drop=True)
                if not ppfd_series.empty and ppfd_series.notna().sum() > 0:
                    st.line_chart(ppfd_series, use_container_width=True)
                    st.info(f"Average PPFD: {ppfd_series.mean():.1f}")
                else:
                    st.warning("No valid PPFD data")
            else:
                st.warning("No valid PPFD data")

        with tabs[3]:
            st.markdown("### CO2")
            if "CO2" in df_plot.columns and not df_plot["CO2"].isna().all():
                co2_series = df_plot["CO2"].reset_index(drop=True)
                if not co2_series.empty and co2_series.notna().sum() > 0:
                    st.line_chart(co2_series, use_container_width=True)
                    st.info(f"Average CO2: {co2_series.mean():.0f} ppm")
                else:
                    st.warning("No valid CO2 data")
            else:
                st.warning("No valid CO2 data")

        with tabs[4]:
            st.markdown("### Sensor Overview (normalized)")
            overview_cols = [c for c in ["T", "RH", "soil_theta", "PPFD", "CO2"] if c in df_plot.columns]
            if overview_cols:
                overview_data = df_plot[overview_cols].copy()
                # Reset index to avoid timestamp issues
                overview_data = overview_data.reset_index(drop=True)
                
                # Clean normalization
                normalized_data = pd.DataFrame(index=overview_data.index)
                for col in overview_cols:
                    col_data = overview_data[col].dropna()
                    if len(col_data) > 1:
                        min_val, max_val = col_data.min(), col_data.max()
                        if max_val > min_val and not pd.isna(min_val) and not pd.isna(max_val):
                            normalized_data[col] = ((overview_data[col] - min_val) / (max_val - min_val) * 100).fillna(50)
                        else:
                            normalized_data[col] = 50
                    else:
                        normalized_data[col] = 50
                        
                if not normalized_data.empty:
                    st.line_chart(normalized_data, use_container_width=True)
                    st.caption(f"{len(overview_cols)} sensors normalized for comparison")
                else:
                    st.warning("No valid sensor data to show")
            else:
                st.warning("No valid sensor data to show")

        # Latest readings
        if len(df_live) > 0:
            latest_values = df_live.iloc[-1]
            with latest_values_container.container():
                cols = st.columns(5)
                metrics = [
                    ("Temperature (°C)", "T", "{:.1f}"),
                    ("Humidity (%)", "RH", "{:.0f}"),
                    ("Soil Moisture", "soil_theta", "{:.2f}"),
                    ("PPFD", "PPFD", "{:.1f}"),
                    ("CO2 (ppm)", "CO2", "{:.0f}"),
                ]
                for c, (label, key, fmt) in zip(cols, metrics):
                    val = latest_values.get(key, None)
                    if val is None or pd.isna(val):
                        c.metric(label, "--")
                    else:
                        c.metric(label, fmt.format(val))
        else:
            latest_values_container.info("No data available")

    else:
        status_el.warning("Waiting for live data")
        last_msg_el.metric("Last update", "No data")
        latest_values_container.info("No live telemetry yet. Historical CSV shown below (if available).")
        if not df_csv.empty:
            try:
                # Use numeric index for historical data too
                df_hist = df_csv.tail(100)[["T", "RH", "soil_theta", "PPFD"]].reset_index(drop=True)
                chart_placeholder.line_chart(df_hist, use_container_width=True)
            except Exception as e:
                st.warning(f"Failed to render historical CSV: {e}")
                
    # Auto-refresh after delay
    time.sleep(refresh_interval)
    st.rerun()

# Footer controls
st.markdown("---")
if st.button("Clear buffer"):
    with data_lock:
        data_queue.clear()
    st.experimental_rerun()

# graceful shutdown when script terminates (attempt)
def _shutdown(signum, frame):
    global _stop_flag
    LOG.info("Shutdown signal received")
    _stop_flag = True

for sig in (signal.SIGINT, signal.SIGTERM):
    try:
        signal.signal(sig, _shutdown)
    except Exception:
        pass
