"""Append-only, hash-chained audit ledger. OWNER: Ayush.

Every request, check, decision, approval and payout event is appended. verify() replays the chain.
"""
from __future__ import annotations


def append(event_type: str, payload: dict) -> str:
    """Append an event; returns its hash. Body hashed with contracts.canonical_json."""
    raise NotImplementedError("Ayush")


def verify() -> dict:
    """Replay the chain. Returns {"ok": bool, "rows": n, "first_bad_row": id_or_None}."""
    raise NotImplementedError("Ayush")
