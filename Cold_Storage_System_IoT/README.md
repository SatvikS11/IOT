# Cold Storage Anomaly Monitoring Assistant

AI-enabled monitoring assistant for cold-room temperature and humidity feeds.

## What this project does
- Ingests sensor data from:
  - CSV (demo/upload)
  - AWS S3 (mock JSON/CSV)
  - AWS DynamoDB (optional IoT Core-backed path)
- Detects three anomaly classes:
  - threshold breach
  - prolonged drift
  - sensor silence
- Produces:
  - event timeline
  - severity status
  - recommended actions
  - AI operational summary

## Quick start
1. Create and activate virtual environment.
2. Install dependencies.
3. Run Streamlit app.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Input data format
```csv
timestamp,temperature_c,humidity_pct
2026-03-21T09:00:00Z,4.2,55.1
```

## Project structure
- `app.py`: Streamlit dashboard and alert workflow view.
- `src/anomaly_engine.py`: Detection rules and action recommendations.
- `src/ai_summary.py`: LLM-backed or fallback operational summary.
- `src/aws_ingestion.py`: AWS S3 + DynamoDB data loaders for sensor telemetry.
- `data/sample_sensor_feed.csv`: Demo dataset with injected anomalies.
- `data/mock_sensor_feed.json`: S3-ready mock JSON dataset.
- `docs/architecture.md`: Architecture diagram.
- `docs/aws_setup.md`: S3-first AWS integration steps (with DynamoDB optional path).
- `docs/demo_script.md`: Voiceover script for demo recording.
- `docs/submission_one_pager.md`: Final one-page submission content.
- `docs/scoring_alignment.md`: Talking points aligned to judging criteria.

## Google Drive submission checklist
1. Architecture diagram: use `docs/architecture.md`.
2. Demo recording: follow `docs/demo_script.md`.
3. One-page template response: use `docs/submission_one_pager.md`.

## Notes
- If `OPENAI_API_KEY` is present, app calls an LLM to generate summary text.
- Without API key, app uses deterministic fallback summary.
- For AWS mode, provide AWS credentials and pick `AWS S3 (Mock JSON/CSV)` in the sidebar.
