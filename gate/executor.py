"""Exactly-once payment executor. OWNER: Ayush.

The executor is the enforcement point: it refuses any payment without a receipt whose action hash,
expiry and single-use nonce match. Fails closed.
"""
from __future__ import annotations

from gate.contracts import Decision


def issue_receipt(decision: Decision, approver: str = "policy") -> dict:
    """For an ALLOW decision, or an ESCALATE a person approved. Returns
    {request_id, action_hash, nonce, expires_at, approver, signature}."""
    raise NotImplementedError("Ayush")


def execute(decision: Decision, receipt: dict) -> dict:
    """Outbox row (idempotency key = decision.action.idempotency_key) -> provider payout.
    Returns {status, payout_id, idempotency_key, replayed: bool}."""
    raise NotImplementedError("Ayush")


def resume() -> list[dict]:
    """After a crash: finish every outbox row left 'unknown' with the identical body and key."""
    raise NotImplementedError("Ayush")
