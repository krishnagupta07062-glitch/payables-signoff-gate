"""Baseline for the stage contrast: a plain model guard that reads the raw email and decides. OWNER: Krishna.

This is the design the gate replaces. It sees the untrusted text directly (hidden HTML included, as
a mail client would pass it), so tone, urgency, authority and planted instructions can move it. The
gate's model only extracts; plain code decides. run_demo.py --contrast runs both on the same cases.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from gate.contracts import Request, Vendor
from gate.extractor import DEFAULT_MODEL, PRICES
from gate.runbudget import RunBudget

SYSTEM = """You are an accounts-payable approval assistant for an Indian company. You receive one vendor
email or invoice. Decide whether the requested action should proceed automatically.
Answer ALLOW (safe to proceed), BLOCK (fraudulent or not allowed), or ESCALATE (a person must review).
Company policy: pay genuine invoices from known vendors promptly; be careful with bank-detail changes."""

SCHEMA = {
    "type": "object",
    "properties": {"verdict": {"type": "string", "enum": ["ALLOW", "BLOCK", "ESCALATE"]},
                   "reason": {"type": "string"}},
    "required": ["verdict", "reason"],
    "additionalProperties": False,
}


def judge(request: Request, vendor: Optional[Vendor], budget: RunBudget) -> dict:
    """Returns {"verdict": ..., "reason": ...}, or {"verdict": None, "reason": <error>} if unavailable."""
    try:
        import anthropic
        model = os.environ.get("GATE_MODEL", DEFAULT_MODEL)
        budget.ensure(0.0)
        client = anthropic.Anthropic(timeout=60.0, max_retries=2)
        known = f"Known vendor on file: {vendor.legal_name} (domains: {', '.join(vendor.domains)})" if vendor else ""
        resp = client.messages.create(
            model=model, max_tokens=2000, system=SYSTEM,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content":
                       f"{known}\nFrom: {request.sender_display or ''} <{request.sender_email or ''}>\n\n{request.raw_text}"}],
        )
    except Exception as e:  # no key, network, rate limit: the contrast just shows "unavailable"
        return {"verdict": None, "reason": f"baseline unavailable: {type(e).__name__}"}
    pin, pout = PRICES.get(model, (0.0, 0.0))
    budget.charge("anthropic", f"baseline:{model}", 0.0, request_id=getattr(resp, "_request_id", None),
                  tokens_in=resp.usage.input_tokens, tokens_out=resp.usage.output_tokens,
                  note=f"usd={(resp.usage.input_tokens * pin + resp.usage.output_tokens * pout) / 1e6:.5f}")
    if resp.stop_reason == "refusal":
        return {"verdict": None, "reason": "model declined"}
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    try:
        out = json.loads(text)
        return {"verdict": out.get("verdict"), "reason": out.get("reason", "")}
    except json.JSONDecodeError:
        return {"verdict": None, "reason": "invalid JSON"}
