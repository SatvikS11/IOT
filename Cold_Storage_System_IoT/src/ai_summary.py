from __future__ import annotations

import os
from typing import Dict, List


def _fallback_summary(payload: Dict) -> str:
    status = payload.get("status", "unknown")
    events = payload.get("events", [])
    actions: List[str] = payload.get("actions", [])

    if not events:
        return (
            "Cold room status is stable. No threshold breaches, drift patterns, "
            "or sensor silence events were detected in the selected window. "
            "Recommendation: continue routine monitoring."
        )

    first = events[0]
    last = events[-1]
    action_text = " ".join([f"- {a}" for a in actions[:3]])
    return (
        f"Cold room status is {status}. Detected {len(events)} anomaly events "
        f"from {first['timestamp']} to {last['timestamp']}. "
        f"Primary signal: {first['event_type']} ({first['severity']}). "
        f"Recommended actions: {action_text}"
    )


def _build_prompt(payload: Dict) -> str:
    return (
        "You are an operations assistant for cold-storage compliance. "
        "Given anomaly events and recommended actions, generate a concise "
        "3-4 sentence operational briefing for shift supervisors. "
        "Mention urgency, likely operational risk, and the immediate next step. "
        f"Input payload: {payload}"
    )


def _generate_with_groq(payload: Dict, api_key: str) -> str:
    from openai import OpenAI

    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You write concise cold-room operations briefings for shift supervisors."
                ),
            },
            {"role": "user", "content": _build_prompt(payload)},
        ],
        temperature=0.2,
    )
    return (response.choices[0].message.content or "").strip()


def _generate_with_openai(payload: Dict, api_key: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You write concise cold-room operations briefings for shift supervisors."
                ),
            },
            {"role": "user", "content": _build_prompt(payload)},
        ],
        temperature=0.2,
    )
    return (response.choices[0].message.content or "").strip()


def generate_ai_summary(payload: Dict) -> str:
    groq_api_key = os.getenv("GROQ_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    if not groq_api_key and not openai_api_key:
        return _fallback_summary(payload)

    if groq_api_key:
        try:
            text = _generate_with_groq(payload, groq_api_key)
            if text:
                return text
        except Exception:
            pass

    if openai_api_key:
        try:
            text = _generate_with_openai(payload, openai_api_key)
            if text:
                return text
        except Exception:
            pass

    return _fallback_summary(payload)
