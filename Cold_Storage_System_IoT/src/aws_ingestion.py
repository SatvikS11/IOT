from __future__ import annotations

import io
import json
from decimal import Decimal
from typing import Dict, List, Optional

import pandas as pd


def _to_float_or_none(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        if isinstance(value, Decimal):
            return float(value)
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_item(item: Dict[str, object]) -> Dict[str, object]:
    return {
        "timestamp": item.get("timestamp"),
        "temperature_c": _to_float_or_none(item.get("temperature_c")),
        "humidity_pct": _to_float_or_none(item.get("humidity_pct")),
    }


def _finalize_dataframe(df: pd.DataFrame, limit: int) -> pd.DataFrame:
    required = ["timestamp", "temperature_c", "humidity_pct"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    out = df[required].copy()
    out = out.dropna(subset=required)
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    out = out.dropna(subset=["timestamp"]).sort_values("timestamp")

    if len(out) > limit:
        out = out.tail(limit)

    out["timestamp"] = out["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return out.reset_index(drop=True)


def _scan_latest_items(table, limit: int) -> List[Dict[str, object]]:
    response = table.scan(Limit=max(limit * 3, 50))
    items: List[Dict[str, object]] = response.get("Items", [])

    while "LastEvaluatedKey" in response and len(items) < (limit * 3):
        response = table.scan(
            ExclusiveStartKey=response["LastEvaluatedKey"],
            Limit=max(limit * 3, 50),
        )
        items.extend(response.get("Items", []))

    return items


def _query_sensor_items(table, sensor_id: str, limit: int) -> List[Dict[str, object]]:
    from boto3.dynamodb.conditions import Key

    response = table.query(
        KeyConditionExpression=Key("sensor_id").eq(sensor_id),
        ScanIndexForward=False,
        Limit=limit,
    )
    return response.get("Items", [])


def load_sensor_data_from_dynamodb(
    table_name: str,
    region_name: str,
    sensor_id: Optional[str] = None,
    limit: int = 100,
) -> pd.DataFrame:
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 is not installed. Add boto3 to requirements.") from exc

    if not table_name:
        raise ValueError("DynamoDB table name is required.")

    dynamodb = boto3.resource("dynamodb", region_name=region_name)
    table = dynamodb.Table(table_name)

    if sensor_id:
        try:
            raw_items = _query_sensor_items(table, sensor_id=sensor_id, limit=limit)
        except Exception:
            raw_items = _scan_latest_items(table, limit=limit)
    else:
        raw_items = _scan_latest_items(table, limit=limit)

    if not raw_items:
        return pd.DataFrame(columns=["timestamp", "temperature_c", "humidity_pct"])

    normalized = [_normalize_item(item) for item in raw_items]
    return _finalize_dataframe(pd.DataFrame(normalized), limit=limit)


def _parse_json_readings(payload_text: str) -> List[Dict[str, object]]:
    parsed = json.loads(payload_text)
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        for key in ("readings", "records", "items", "data"):
            value = parsed.get(key)
            if isinstance(value, list):
                return value
        return [parsed]
    raise ValueError("Unsupported JSON structure for sensor readings.")


def load_sensor_data_from_s3(
    bucket_name: str,
    object_key: str,
    region_name: str,
    limit: int = 100,
    file_format: str = "auto",
) -> pd.DataFrame:
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 is not installed. Add boto3 to requirements.") from exc

    if not bucket_name:
        raise ValueError("S3 bucket name is required.")
    if not object_key:
        raise ValueError("S3 object key is required.")

    s3 = boto3.client("s3", region_name=region_name)
    response = s3.get_object(Bucket=bucket_name, Key=object_key)
    payload_bytes = response["Body"].read()
    payload_text = payload_bytes.decode("utf-8")

    selected_format = file_format.lower().strip()
    if selected_format == "auto":
        key = object_key.lower()
        if key.endswith(".csv"):
            selected_format = "csv"
        elif key.endswith(".json"):
            selected_format = "json"
        else:
            selected_format = "json"

    if selected_format == "csv":
        df = pd.read_csv(io.StringIO(payload_text))
        return _finalize_dataframe(df, limit=limit)

    if selected_format == "json":
        readings = _parse_json_readings(payload_text)
        normalized = [_normalize_item(item) for item in readings]
        return _finalize_dataframe(pd.DataFrame(normalized), limit=limit)

    raise ValueError("Unsupported file_format. Use one of: auto, json, csv.")
