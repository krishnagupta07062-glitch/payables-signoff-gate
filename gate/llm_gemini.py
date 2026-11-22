"""Google Gemini as an alternative model provider (free tier via Google AI Studio). OWNER: Krishna.

Select with GATE_PROVIDER=gemini and set GEMINI_API_KEY (and optionally GEMINI_MODEL).
Plain REST through `requests`, so no new dependency. Used by the extractor and the baseline guard;
the model's role is unchanged: it only returns JSON, and code validates every field.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from gate.runbudget import RunBudget

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-3.5-flash-lite"
# tried in order when the chosen model is overloaded (503) or out of free quota (429)
FALLBACK_MODELS = ("gemini-3.1-flash-lite", "gemini-2.5-flash-lite", "gemini-flash-lite-latest")
RETRY_STATUS = (429, 500, 503)


def provider() -> str:
    return (os.environ.get("GATE_PROVIDER") or "anthropic").strip().lower()


def model() -> str:
    return os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL


def models_to_try() -> list[str]:
    extra = [m.strip() for m in (os.environ.get("GEMINI_FALLBACK_MODELS") or ",".join(FALLBACK_MODELS)).split(",")]
    out = []
    for m in [model(), *extra]:
        if m and m not in out:
            out.append(m)
    return out


def _post(body: dict, key: str, timeout: float, model_name: Optional[str] = None):
    import requests
    return requests.post(API.format(model=model_name or model()), json=body, timeout=timeout,
                         headers={"x-goog-api-key": key, "Content-Type": "application/json"})


def parse_response(j: dict) -> tuple[Optional[dict], str]:
    """(object, "") on success, or (None, reason)."""
    if (j.get("promptFeedback") or {}).get("blockReason"):
        return None, f"model declined: {j['promptFeedback']['blockReason']}"
    cands = j.get("candidates") or []
    if not cands:
        return None, "no candidates"
    c = cands[0]
    if c.get("finishReason") not in (None, "STOP", "MAX_TOKENS"):
        return None, f"model stopped: {c.get('finishReason')}"
    text = "".join(p.get("text", "") for p in (c.get("content") or {}).get("parts", []) if not p.get("thought"))
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None, "invalid JSON"
    return (obj, "") if isinstance(obj, dict) else (None, "JSON was not an object")


def generate_json(system: str, user: str, schema: dict, budget: RunBudget, label: str,
                  timeout: float = 60.0) -> tuple[Optional[dict], str]:
    """Ask Gemini for one JSON object matching `schema`. Never raises; returns (obj, error_note)."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None, "GEMINI_API_KEY is not set"
    budget.ensure(0.0)
    cfg = {"responseMimeType": "application/json", "temperature": 0}
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": dict(cfg, responseJsonSchema=schema)}
    import time
    r, used = None, model()
    try:
        for used in models_to_try():
            for attempt in range(2):
                r = _post(body, key, timeout, used)
                if r.status_code == 400 and "responseJsonSchema" in r.text and "responseJsonSchema" in body["generationConfig"]:
                    # older models: plain JSON mode, schema given in the prompt; validation still applies
                    body["generationConfig"] = cfg
                    body["contents"][0]["parts"][0]["text"] = (
                        f"{user}\n\nReturn one JSON object matching this JSON Schema:\n{json.dumps(schema)}")
                    r = _post(body, key, timeout, used)
                if r.status_code not in RETRY_STATUS:
                    break
                time.sleep(2 + 3 * attempt)
            if r.status_code not in RETRY_STATUS:
                break
    except Exception as e:  # network, timeout
        budget.charge("gemini", label, 0.0, note=f"error: {type(e).__name__}")
        return None, f"{type(e).__name__}"
    try:
        j = r.json()
    except ValueError:
        j = {}
    if r.status_code != 200:
        msg = ((j.get("error") or {}).get("message") or r.text)[:200]
        budget.charge("gemini", label, 0.0, note=f"error: HTTP {r.status_code}")
        return None, f"HTTP {r.status_code}: {msg}"
    u = j.get("usageMetadata") or {}
    budget.charge("gemini", f"{label}:{used}", 0.0, request_id=j.get("responseId"),
                  tokens_in=u.get("promptTokenCount"), tokens_out=u.get("candidatesTokenCount"), note="usd=0 (free tier)")
    return parse_response(j)
