# src/utils.py
from datetime import datetime
from pathlib import Path
import yaml


def load_config(path: str | Path) -> dict:
    """Load a YAML config file and return as dict."""
    p = Path(path)
    if not p.is_absolute():
        p = (Path(__file__).parent / p).resolve()
        
    with open(p, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg or {}


def safe_parse_timestamp(ts_val) -> float:
    """Return fractional hour (0.0–24.0) from an ESP32 timestamp.

    Handles boot-seconds (e.g. "32"), Unix epoch s/ms, and ISO strings.
    Returns fractional hours to match training feature (hour = H + min/60).
    # ponytail: stdlib datetime only; no pandas needed
    """
    def fh(dt: datetime) -> float:
        return dt.hour + dt.minute / 60.0

    try:
        if ts_val is None:
            return fh(datetime.now())
        ts_str = str(ts_val)
        if ts_str.replace('.', '', 1).isdigit():
            n = float(ts_str)
            if n < 86400:           # boot-seconds, not a wall-clock timestamp
                return fh(datetime.now())
            if n > 1e12:            # milliseconds → seconds
                n /= 1000
            return fh(datetime.fromtimestamp(n))
        return fh(datetime.fromisoformat(ts_str))
    except Exception:
        return fh(datetime.now())

# Per-process telemetry buffer — shared by cloud_controller and pi_fallback.
# Holds (wall_clock_s, soil, ppfd) tuples for the last 60 minutes.
from collections import deque as _deque
import time as _time
_tele_buf: _deque = _deque()


def rolling_features(soil: float, ppfd: float) -> tuple[float, float, float]:
    """Compute soil_lag1, soil_roll_6, ppfd_roll_6 from a 60-min time buffer.

    Mirrors train_irrigation.py feature engineering:
      soil_lag1   = df['soil_theta'].shift(1)          -> reading ~10 min ago
      soil_roll_6 = df['soil_theta'].rolling(6).mean() -> 60-min mean
      ppfd_roll_6 = df['PPFD'].rolling(6).mean()       -> 60-min mean

    On startup (buffer < 10 min old) returns soil/ppfd as the best available
    approximation rather than crashing or introducing None.
    """
    now = _time.time()
    _tele_buf.append((now, soil, ppfd))
    # Drop readings older than 60 minutes
    while _tele_buf and now - _tele_buf[0][0] > 3600:
        _tele_buf.popleft()

    soils = [s for _, s, _ in _tele_buf]
    ppfds = [p for _, _, p in _tele_buf]

    # lag1: most recent reading that is at least 10 min old
    lag_candidates = [s for ts, s, _ in _tele_buf if now - ts >= 600]
    soil_lag1 = lag_candidates[-1] if lag_candidates else soils[0]

    soil_roll_6 = sum(soils) / len(soils)
    ppfd_roll_6 = sum(ppfds) / len(ppfds)
    return soil_lag1, soil_roll_6, ppfd_roll_6


def duration_from_delta(delta: float, min_sec: int = 8, max_sec: int = 60) -> int:
    """Map soil-moisture deficit (VWC fraction) to pump duration in seconds.

    Rule of thumb: 0.01 VWC deficit ≈ 15 s of irrigation, clamped to [min_sec, max_sec].
    Returns 0 if delta is non-positive (no irrigation needed).
    """
    if delta <= 0:
        return 0
    secs = (delta / 0.01) * 15.0
    return int(max(min_sec, min(max_sec, secs)))
