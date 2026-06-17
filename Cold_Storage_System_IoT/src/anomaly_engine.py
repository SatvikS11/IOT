from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


@dataclass
class AlertRuleConfig:
    temp_min_c: float = 2.0
    temp_max_c: float = 8.0
    humidity_min_pct: float = 45.0
    humidity_max_pct: float = 70.0
    expected_interval_minutes: int = 5
    silence_gap_multiplier: int = 3
    drift_window_points: int = 8
    drift_slope_threshold_c_per_point: float = 0.25


def _ensure_timestamp(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    out = out.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return out


def detect_threshold_breaches(df: pd.DataFrame, cfg: AlertRuleConfig) -> pd.DataFrame:
    breaches = []
    for idx, row in df.iterrows():
        temp = row["temperature_c"]
        hum = row["humidity_pct"]
        reasons = []

        if temp < cfg.temp_min_c:
            reasons.append(f"Temperature too low ({temp:.2f}C < {cfg.temp_min_c:.2f}C)")
        elif temp > cfg.temp_max_c:
            reasons.append(f"Temperature too high ({temp:.2f}C > {cfg.temp_max_c:.2f}C)")

        if hum < cfg.humidity_min_pct:
            reasons.append(f"Humidity too low ({hum:.2f}% < {cfg.humidity_min_pct:.2f}%)")
        elif hum > cfg.humidity_max_pct:
            reasons.append(f"Humidity too high ({hum:.2f}% > {cfg.humidity_max_pct:.2f}%)")

        if reasons:
            breaches.append(
                {
                    "timestamp": row["timestamp"],
                    "event_type": "threshold_breach",
                    "severity": "high" if len(reasons) > 1 else "medium",
                    "details": "; ".join(reasons),
                }
            )

    return pd.DataFrame(breaches)


def detect_sensor_silence(df: pd.DataFrame, cfg: AlertRuleConfig) -> pd.DataFrame:
    events = []
    if len(df) < 2:
        return pd.DataFrame(events)

    gaps = df["timestamp"].diff().dt.total_seconds().div(60)
    silence_threshold = cfg.expected_interval_minutes * cfg.silence_gap_multiplier

    for idx in range(1, len(df)):
        gap = gaps.iloc[idx]
        if pd.notna(gap) and gap > silence_threshold:
            events.append(
                {
                    "timestamp": df.loc[idx, "timestamp"],
                    "event_type": "sensor_silence",
                    "severity": "high" if gap > (silence_threshold * 2) else "medium",
                    "details": (
                        f"No readings for {gap:.1f} minutes "
                        f"(expected every {cfg.expected_interval_minutes} minutes)"
                    ),
                }
            )

    return pd.DataFrame(events)


def _rolling_slope(values: np.ndarray) -> float:
    x = np.arange(len(values))
    slope, _ = np.polyfit(x, values, 1)
    return float(slope)


def detect_prolonged_drift(df: pd.DataFrame, cfg: AlertRuleConfig) -> pd.DataFrame:
    events = []
    if len(df) < cfg.drift_window_points:
        return pd.DataFrame(events)

    temps = df["temperature_c"].to_numpy()
    window = cfg.drift_window_points

    for i in range(window - 1, len(df)):
        chunk = temps[i - window + 1 : i + 1]
        slope = _rolling_slope(chunk)
        if abs(slope) >= cfg.drift_slope_threshold_c_per_point:
            direction = "upward" if slope > 0 else "downward"
            events.append(
                {
                    "timestamp": df.loc[i, "timestamp"],
                    "event_type": "prolonged_drift",
                    "severity": "medium",
                    "details": (
                        f"{direction.title()} temperature drift detected "
                        f"(slope={slope:.3f} C/reading over last {window} points)"
                    ),
                }
            )

    if not events:
        return pd.DataFrame(events)

    drift_df = pd.DataFrame(events)
    drift_df["prev_time"] = drift_df["timestamp"].shift(1)
    keep = drift_df["prev_time"].isna() | (
        (drift_df["timestamp"] - drift_df["prev_time"]).dt.total_seconds() > 900
    )
    return drift_df[keep].drop(columns=["prev_time"]).reset_index(drop=True)


def infer_overall_status(events: pd.DataFrame) -> Tuple[str, str]:
    if events.empty:
        return "stable", "No active anomalies detected."

    severities = events["severity"].tolist()
    if "high" in severities:
        return "critical", "Immediate intervention recommended."
    if "medium" in severities:
        return "watch", "Operational follow-up recommended within the hour."
    return "info", "Monitor and continue normal checks."


def recommend_action(events: pd.DataFrame) -> List[str]:
    if events.empty:
        return ["Continue routine monitoring and record readings as compliant."]

    actions: List[str] = []
    event_types = set(events["event_type"].tolist())

    if "threshold_breach" in event_types:
        actions.append("Inspect door seal and refrigeration unit immediately.")
        actions.append("Verify product exposure window and quarantine sensitive stock if needed.")

    if "prolonged_drift" in event_types:
        actions.append("Check condenser/evaporator performance and airflow obstructions.")
        actions.append("Schedule preventive maintenance if drift persists for 2+ cycles.")

    if "sensor_silence" in event_types:
        actions.append("Validate sensor power/network status and replace battery if applicable.")
        actions.append("Switch to backup logger until telemetry is restored.")

    return actions


def run_detection(df: pd.DataFrame, cfg: AlertRuleConfig) -> Dict[str, pd.DataFrame | str | List[str]]:
    cleaned = _ensure_timestamp(df)

    breach_df = detect_threshold_breaches(cleaned, cfg)
    silence_df = detect_sensor_silence(cleaned, cfg)
    drift_df = detect_prolonged_drift(cleaned, cfg)

    events = pd.concat([breach_df, silence_df, drift_df], ignore_index=True)
    if not events.empty:
        events = events.sort_values("timestamp").reset_index(drop=True)

    status, status_note = infer_overall_status(events)
    actions = recommend_action(events)

    return {
        "cleaned_data": cleaned,
        "events": events,
        "status": status,
        "status_note": status_note,
        "actions": actions,
    }
