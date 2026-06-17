from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from src.ai_summary import generate_ai_summary
from src.anomaly_engine import AlertRuleConfig, run_detection
from src.aws_ingestion import load_sensor_data_from_dynamodb, load_sensor_data_from_s3

st.set_page_config(page_title="Cold Storage Anomaly Monitoring Assistant", layout="wide")

st.title("Cold Storage Anomaly Monitoring Assistant")
st.caption("One-sensor scenario for cold-room temperature and humidity monitoring")

sample_path = Path("data/sample_sensor_feed.csv")

with st.sidebar:
    st.header("Alert Settings")
    temp_min = st.number_input("Temp Min (C)", value=2.0, step=0.5)
    temp_max = st.number_input("Temp Max (C)", value=8.0, step=0.5)
    hum_min = st.number_input("Humidity Min (%)", value=45.0, step=1.0)
    hum_max = st.number_input("Humidity Max (%)", value=70.0, step=1.0)
    expected_interval = st.number_input("Expected Interval (min)", value=5, step=1)

    st.markdown("---")
    st.subheader("Data Source")
    source_mode = st.radio(
        "Select source",
        options=["CSV (Demo/Upload)", "AWS S3 (Mock JSON/CSV)", "AWS DynamoDB"],
        index=0,
    )

    uploaded = None
    s3_bucket = ""
    s3_object_key = ""
    s3_format = "auto"
    s3_limit = 100

    aws_region = ""
    aws_table = ""
    aws_sensor_id = ""
    aws_limit = 100

    if source_mode == "CSV (Demo/Upload)":
        uploaded = st.file_uploader("Upload sensor CSV", type=["csv"])
    elif source_mode == "AWS S3 (Mock JSON/CSV)":
        aws_region = st.text_input("AWS Region", value="ap-south-1")
        s3_bucket = st.text_input("S3 Bucket Name", value="")
        s3_object_key = st.text_input("S3 Object Key", value="coldroom/mock_sensor_feed.json")
        s3_format = st.selectbox("File Format", options=["auto", "json", "csv"], index=0)
        s3_limit = int(st.number_input("Read latest N rows", value=100, min_value=10, step=10))
        st.caption("Object must contain timestamp, temperature_c, humidity_pct.")
    else:
        aws_region = st.text_input("AWS Region", value="ap-south-1")
        aws_table = st.text_input("DynamoDB Table Name", value="cold_room_readings")
        aws_sensor_id = st.text_input("Sensor ID (optional)", value="")
        aws_limit = int(st.number_input("Fetch latest N rows", value=100, min_value=10, step=10))
        st.caption("If Sensor ID is set, query uses partition key `sensor_id`.")

if source_mode == "CSV (Demo/Upload)":
    if uploaded is not None:
        df = pd.read_csv(uploaded)
        st.success("Loaded data from uploaded CSV.")
    else:
        df = pd.read_csv(sample_path)
        st.info("Loaded demo dataset from local sample CSV.")
elif source_mode == "AWS S3 (Mock JSON/CSV)":
    try:
        df = load_sensor_data_from_s3(
            bucket_name=s3_bucket.strip(),
            object_key=s3_object_key.strip(),
            region_name=aws_region,
            limit=s3_limit,
            file_format=s3_format,
        )
        if df.empty:
            st.warning("No valid records found in selected S3 object.")
        else:
            st.success(f"Loaded {len(df)} rows from S3.")
    except Exception as exc:
        st.error(f"S3 data load failed: {exc}")
        st.stop()
else:
    try:
        df = load_sensor_data_from_dynamodb(
            table_name=aws_table,
            region_name=aws_region,
            sensor_id=aws_sensor_id.strip() or None,
            limit=aws_limit,
        )
        if df.empty:
            st.warning("No records found in DynamoDB with current settings.")
        else:
            st.success(f"Loaded {len(df)} rows from DynamoDB.")
    except Exception as exc:
        st.error(f"AWS data load failed: {exc}")
        st.stop()

cfg = AlertRuleConfig(
    temp_min_c=float(temp_min),
    temp_max_c=float(temp_max),
    humidity_min_pct=float(hum_min),
    humidity_max_pct=float(hum_max),
    expected_interval_minutes=int(expected_interval),
)

result = run_detection(df, cfg)
cleaned = result["cleaned_data"]
events = result["events"]
status = result["status"]
status_note = result["status_note"]
actions = result["actions"]

col1, col2, col3 = st.columns(3)
col1.metric("Total Readings", value=len(cleaned))
col2.metric("Anomaly Events", value=len(events))
col3.metric("System Status", value=status.upper())

st.info(status_note)

fig_temp = px.line(
    cleaned,
    x="timestamp",
    y="temperature_c",
    title="Temperature Trend",
)
fig_temp.add_hrect(y0=temp_min, y1=temp_max, line_width=0, fillcolor="green", opacity=0.1)
st.plotly_chart(fig_temp, use_container_width=True)

fig_hum = px.line(
    cleaned,
    x="timestamp",
    y="humidity_pct",
    title="Humidity Trend",
)
fig_hum.add_hrect(y0=hum_min, y1=hum_max, line_width=0, fillcolor="blue", opacity=0.08)
st.plotly_chart(fig_hum, use_container_width=True)

st.subheader("Detected Events")
if events.empty:
    st.success("No anomalies detected in the selected dataset.")
else:
    display_events = events.copy()
    display_events["timestamp"] = display_events["timestamp"].astype(str)
    st.dataframe(display_events, use_container_width=True)

st.subheader("Recommended Actions")
for i, action in enumerate(actions, start=1):
    st.write(f"{i}. {action}")

summary_payload = {
    "status": status,
    "events": events.to_dict(orient="records") if not events.empty else [],
    "actions": actions,
}
summary_text = generate_ai_summary(summary_payload)

st.subheader("AI Operational Summary")
st.write(summary_text)

with st.expander("CSV format expected"):
    st.code(
        "timestamp,temperature_c,humidity_pct\\n"
        "2026-03-21T09:00:00Z,4.2,55.1",
        language="text",
    )

with st.expander("AWS payload example"):
    st.code(
        '{"sensor_id":"CR-01","timestamp":"2026-03-21T09:00:00Z","temperature_c":4.2,"humidity_pct":55.1}',
        language="json",
    )

with st.expander("S3 JSON array example"):
    st.code(
        '[{"timestamp":"2026-03-21T09:00:00Z","temperature_c":4.2,"humidity_pct":55.1}]',
        language="json",
    )
