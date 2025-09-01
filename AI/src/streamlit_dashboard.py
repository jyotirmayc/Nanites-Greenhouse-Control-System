#!/usr/bin/env python3
"""
IOTricity Greenhouse Dashboard (Streamlit)

- Background MQTT thread ingests telemetry JSON into a bounded deque.
- Streamlit reads the deque, validates data, and renders metrics & charts.
- Includes a Difference view to compare any two sensor series.
- Uses structured logging and safe parsing; no prints or emojis.
"""

from collections import deque
from threading import Thread, Lock
from pathlib import Path
import time
import json
import logging
import os
import signal
from typing import Any, Dict

import pandas as pd
import paho.mqtt.client as mqtt
import streamlit as st
import yaml
import uuid

# ---------- Logging ----------
LOG = logging.getLogger("iotr_dashboard")
if not LOG.hasHandlers():
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    LOG.addHandler(h)
LOG.setLevel(logging.INFO)

# ---------- Configuration ----------
THIS_DIR = Path(__file__).resolve().parent
CONFIG_PATH = THIS_DIR.parent / "config.yaml"

cfg: Dict[str, Any] = {}
if CONFIG_PATH.exists():
    try:
        with open(CONFIG_PATH, "r") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception as e:
        LOG.warning("Could not load config.yaml (%s) — using defaults", e)

MQTT_BROKER = os.environ.get("MQTT_BROKER", cfg.get("inference", {}).get("mqtt_broker", "broker.hivemq.com"))
MQTT_PORT = int(os.environ.get("MQTT_PORT", cfg.get("inference", {}).get("mqtt_port", 1883)))
TELEMETRY_TOPIC = os.environ.get("MQTT_TOPIC", cfg.get("inference", {}).get("telemetry_topic", "greenhouse/A1/telemetry"))
COMMAND_TOPIC = os.environ.get("COMMAND_TOPIC", cfg.get("inference", {}).get("cmd_topic", "greenhouse/A1/cmd"))
DATA_CSV_PATH = os.environ.get("DATA_CSV_PATH", cfg.get("training", {}).get("data_path", str(THIS_DIR.parent / "data" / "synthetic_greenhouse_7days_10min.csv")))

MAX_MESSAGES = int(os.environ.get("MAX_MESSAGES", cfg.get("inference", {}).get("max_messages", 200)))
MAX_COMMANDS = int(os.environ.get("MAX_COMMANDS", 50))
AUTO_RECONNECT = True

# ---------- Shared state (persist across reruns) ----------
if "telemetry" not in st.session_state:
    st.session_state.telemetry = deque(maxlen=MAX_MESSAGES)
if "commands" not in st.session_state:
    st.session_state.commands = deque(maxlen=MAX_COMMANDS)
if "mqtt_client" not in st.session_state:
    st.session_state.mqtt_client = None
if "mqtt_connected" not in st.session_state:
    st.session_state.mqtt_connected = False
if "mqtt_started" not in st.session_state:
    st.session_state.mqtt_started = False

data_lock = Lock()
_stop_flag = False  # used to signal worker to stop on shutdown

# ---------- Utility functions ----------
def safe_float(v, default: float = None):
    """Convert to float safely. Return default if conversion fails or value is NaN/inf."""
    try:
        if v is None:
            return default
        f = float(v)
        if pd.isna(f) or f in (float("inf"), float("-inf")):
            return default
        return f
    except Exception:
        return default

def parse_ts(ts_val):
    """Return pandas.Timestamp UTC. Accepts epoch seconds/ms, ISO or Timestamp-like."""
    try:
        if ts_val is None:
            return pd.Timestamp.utcnow().tz_localize("UTC")
        if isinstance(ts_val, (int, float)):
            if ts_val > 1e12:
                return pd.to_datetime(ts_val, unit="ms", utc=True)
            return pd.to_datetime(ts_val, unit="s", utc=True)
        return pd.to_datetime(ts_val, utc=True)
    except Exception:
        return pd.Timestamp.utcnow().tz_localize("UTC")

def append_telemetry(record: dict):
    """Thread-safe append to telemetry deque in session_state."""
    with data_lock:
        st.session_state.telemetry.append(record)

def append_command(record: dict):
    """Append an AI command if unique by cmd_id; keep bounded history."""
    with data_lock:
        cmd_id = record.get("cmd_id") or record.get("command_id")
        # deduplicate by cmd_id
        if cmd_id:
            if any((c.get("cmd_id") == cmd_id or c.get("command_id") == cmd_id) for c in st.session_state.commands):
                return
        st.session_state.commands.append(record)

# ---------- MQTT callbacks & worker ----------
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        LOG.info("Connected to MQTT broker %s:%d", MQTT_BROKER, MQTT_PORT)
        client.subscribe(TELEMETRY_TOPIC)
        client.subscribe(COMMAND_TOPIC)
        st.session_state.mqtt_connected = True
    else:
        LOG.error("Failed to connect to MQTT (rc=%s)", rc)
        st.session_state.mqtt_connected = False

def on_disconnect(client, userdata, rc, properties=None):
    LOG.warning("MQTT disconnected (rc=%s)", rc)
    st.session_state.mqtt_connected = False

def on_message(client, userdata, msg):
    # Parse payload; tolerate different field names
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except Exception:
        LOG.debug("Received non-JSON payload on topic %s", msg.topic)
        return

    now_ts = pd.Timestamp.utcnow().tz_localize("UTC")

    if msg.topic == TELEMETRY_TOPIC:
        # Accept flexible payload shape; convert numeric fields to floats; parse timestamp if present
        ts_parsed = parse_ts(payload.get("ts")) if payload.get("ts") is not None else now_ts
        rec = {
            "ts": ts_parsed,
            "device_id": payload.get("device_id", payload.get("bayId", "A1")),
            "T": safe_float(payload.get("T")),
            "RH": safe_float(payload.get("RH")),
            "soil_theta": safe_float(payload.get("soil_theta", payload.get("soil"))),
            "PPFD": safe_float(payload.get("PPFD", payload.get("light"))),
            "CO2": safe_float(payload.get("CO2")),
            "ext_T": safe_float(payload.get("ext_T", payload.get("T"))),
        }
        append_telemetry(rec)

    elif msg.topic == COMMAND_TOPIC:
        cmd_rec = {
            "timestamp": now_ts,
            "cmd_id": payload.get("cmd_id") or payload.get("command_id") or str(uuid.uuid4()),
            "source": payload.get("source", "unknown"),
            "actions": payload.get("actions", {}),
            "raw": payload
        }
        append_command(cmd_rec)

def mqtt_worker(broker, port, telemetry_topic, command_topic):
    client_id = f"streamlit-dashboard-{uuid.uuid4().hex[:8]}"
    client = mqtt.Client(client_id=client_id, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=60)
    try:
        client.connect(broker, port, keepalive=60)
    except Exception as e:
        LOG.error("MQTT connect error: %s", e)
        st.session_state.mqtt_connected = False
        return

    st.session_state.mqtt_client = client
    st.session_state.mqtt_connected = True
    client.loop_start()
    LOG.info("MQTT loop started")
    try:
        while not _stop_flag:
            time.sleep(0.5)
    finally:
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass
        st.session_state.mqtt_connected = False
        LOG.info("MQTT worker stopped")

def start_mqtt():
    if st.session_state.mqtt_started:
        return
    thread = Thread(target=mqtt_worker, args=(MQTT_BROKER, MQTT_PORT, TELEMETRY_TOPIC, COMMAND_TOPIC), daemon=True)
    thread.start()
    st.session_state.mqtt_started = True
    LOG.info("Started MQTT background thread")

def stop_mqtt():
    global _stop_flag
    _stop_flag = True
    # loop_stop and disconnect happen inside worker finally
    st.session_state.mqtt_started = False

# ---------- Streamlit UI ----------
st.set_page_config(page_title="IOTricity Greenhouse Dashboard", layout="wide")
st.title("IOTricity Greenhouse Dashboard")
st.markdown("Professional real-time telemetry and AI control monitor")

# Sidebar controls
with st.sidebar:
    st.header("Connection")
    st.write(f"Broker: {MQTT_BROKER}:{MQTT_PORT}")
    st.write(f"Telemetry topic: {TELEMETRY_TOPIC}")
    st.write(f"Command topic: {COMMAND_TOPIC}")
    if st.button("Connect to MQTT"):
        start_mqtt()
        time.sleep(0.5)
        st.experimental_rerun()
    if st.button("Disconnect MQTT"):
        stop_mqtt()
        time.sleep(0.5)
        st.experimental_rerun()
    st.markdown("---")
    st.header("Display options")
    auto_refresh = st.checkbox("Auto refresh", value=False)
    refresh_interval = st.slider("Refresh interval (s)", min_value=1, max_value=10, value=2)
    st.markdown("---")
    st.header("Difference plot")
    diff_sensor_a = st.selectbox("Sensor A (left)", options=["T", "ext_T", "RH", "soil_theta", "PPFD", "CO2"], index=0)
    diff_sensor_b = st.selectbox("Sensor B (right)", options=["T", "ext_T", "RH", "soil_theta", "PPFD", "CO2"], index=2)
    rolling_window = st.slider("Rolling window for diff (points)", min_value=1, max_value=50, value=5)
    st.markdown("---")
    if st.button("Clear telemetry buffer"):
        with data_lock:
            st.session_state.telemetry.clear()
            st.session_state.commands.clear()
        st.experimental_rerun()

# Start MQTT automatically if not started
if not st.session_state.mqtt_started:
    start_mqtt()

# Snapshot of telemetry & commands for this render
with data_lock:
    telemetry_list = list(st.session_state.telemetry)
    commands_list = list(st.session_state.commands)

# Convert telemetry to DataFrame if available
if telemetry_list:
    df = pd.DataFrame(telemetry_list)
    # Ensure ts is datetime and sort
    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        df = df.sort_values("ts")
    else:
        df["ts"] = pd.Timestamp.utcnow()
else:
    df = pd.DataFrame(columns=["ts", "device_id", "T", "RH", "soil_theta", "PPFD", "CO2", "ext_T"])

# Top metrics (most recent sample)
st.subheader("Current readings")
col_temp, col_rh, col_soil, col_ppfd, col_co2 = st.columns(5)
if not df.empty:
    latest = df.iloc[-1]
    col_temp.metric("Temperature (°C)", f"{latest.get('T', 'N/A'):.1f}" if pd.notna(latest.get('T')) else "N/A")
    col_rh.metric("Humidity (%)", f"{latest.get('RH', 'N/A'):.0f}" if pd.notna(latest.get('RH')) else "N/A")
    soil_val = latest.get("soil_theta")
    if pd.notna(soil_val):
        col_soil.metric("Soil moisture", f"{soil_val:.3f}")
    else:
        col_soil.metric("Soil moisture", "N/A")
    col_ppfd.metric("PPFD", f"{latest.get('PPFD', 'N/A'):.1f}" if pd.notna(latest.get('PPFD')) else "N/A")
    col_co2.metric("CO2 (ppm)", f"{latest.get('CO2', 'N/A'):.0f}" if pd.notna(latest.get('CO2')) else "N/A")
else:
    col_temp.metric("Temperature (°C)", "N/A")
    col_rh.metric("Humidity (%)", "N/A")
    col_soil.metric("Soil moisture", "N/A")
    col_ppfd.metric("PPFD", "N/A")
    col_co2.metric("CO2 (ppm)", "N/A")

# Charts area
st.subheader("Sensor trends")
tabs = st.tabs(["Temperature", "Moisture & Humidity", "Light (PPFD)", "CO2", "Difference", "AI Monitor"])

# Helpers to plot series safely
def safe_series_plot(series: pd.Series, label: str):
    if series.dropna().empty or len(series.dropna()) < 2:
        st.info(f"Insufficient data for {label}")
        return
    st.line_chart(series)

with tabs[0]:
    st.markdown("Temperature (internal and external)")
    if not df.empty and "T" in df.columns:
        temp_df = df.set_index("ts")[["T", "ext_T"]].dropna(how="all")
        if not temp_df.empty:
            st.line_chart(temp_df)
            st.write(f"Average: {temp_df.mean().to_dict()}")
        else:
            st.info("Not enough temperature data")
    else:
        st.info("No temperature data available")

with tabs[1]:
    st.markdown("Soil moisture and Relative Humidity")
    if not df.empty:
        moist_df = df.set_index("ts")[["soil_theta", "RH"]].dropna(how="all")
        if not moist_df.empty:
            st.line_chart(moist_df)
        else:
            st.info("No moisture/humidity data")
    else:
        st.info("No data available")

with tabs[2]:
    st.markdown("Light (PPFD)")
    if not df.empty and "PPFD" in df.columns:
        ppfd_df = df.set_index("ts")[["PPFD"]].dropna()
        if not ppfd_df.empty:
            st.line_chart(ppfd_df)
        else:
            st.info("No PPFD data")
    else:
        st.info("No PPFD data available")

with tabs[3]:
    st.markdown("CO2 concentration")
    if not df.empty and "CO2" in df.columns:
        co2_df = df.set_index("ts")[["CO2"]].dropna()
        if not co2_df.empty:
            st.line_chart(co2_df)
        else:
            st.info("No CO2 data")
    else:
        st.info("No CO2 data available")

with tabs[4]:
    st.markdown("Difference between two sensors")
    # Ensure both columns exist
    if diff_sensor_a not in df.columns or diff_sensor_b not in df.columns:
        st.info("Selected sensors are not present in telemetry yet")
    else:
        diff_df = df.set_index("ts")[[diff_sensor_a, diff_sensor_b]].dropna(how="all").dropna()
        if diff_df.empty or len(diff_df) < 2:
            st.info("Insufficient data points for difference plot")
        else:
            diff_series = diff_df[diff_sensor_a] - diff_df[diff_sensor_b]
            st.line_chart(diff_series.rename(f"{diff_sensor_a} - {diff_sensor_b}"))
            # rolling mean
            if rolling_window > 1:
                rolling_mean = diff_series.rolling(window=rolling_window, min_periods=1).mean()
                st.line_chart(rolling_mean.rename(f"Rolling mean ({rolling_window})"))
            st.write({
                "latest_difference": float(diff_series.iloc[-1]),
                "mean_difference": float(diff_series.mean()),
                "std_difference": float(diff_series.std())
            })

with tabs[5]:
    st.markdown("AI control history")
    if commands_list:
        recent = list(reversed(commands_list[-20:]))
        for cmd in recent:
            ts = cmd.get("timestamp")
            src = cmd.get("source")
            cid = cmd.get("cmd_id")
            with st.expander(f"{ts.strftime('%Y-%m-%d %H:%M:%S')} — {src} — {cid}"):
                actions = cmd.get("actions", {})
                st.json(actions)
        # summary metrics
        irrig_count = sum(1 for c in commands_list if "irrigation" in c.get("actions", {}))
        fan_count = sum(1 for c in commands_list if "fan" in c.get("actions", {}))
        safety_count = sum(1 for c in commands_list if "safety" in c.get("actions", {}))
        st.metric("Irrigation events", irrig_count)
        st.metric("Fan activations", fan_count)
        st.metric("Safety events", safety_count)
    else:
        st.info("No AI commands received yet")

# Footer: connection and refresh controls
st.markdown("---")
conn_col1, conn_col2, conn_col3 = st.columns([2, 2, 6])
with conn_col1:
    conn_status = "Connected" if st.session_state.mqtt_connected else "Disconnected"
    st.write(f"MQTT: {conn_status}")
with conn_col2:
    st.write(f"Telemetry buffer: {len(telemetry_list)}")
with conn_col3:
    if st.button("Manual refresh"):
        st.experimental_rerun()

# Auto-refresh handling
if auto_refresh:
    time.sleep(float(refresh_interval))
    st.experimental_rerun()

# Graceful shutdown handler
def _shutdown(sig, frame):
    global _stop_flag
    LOG.info("Shutdown signal received: %s", sig)
    _stop_flag = True

for sig in (signal.SIGINT, signal.SIGTERM):
    try:
        signal.signal(sig, _shutdown)
    except Exception:
        pass
