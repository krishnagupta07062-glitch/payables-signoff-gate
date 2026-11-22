"""RazorpayX Payouts (test mode) and a mock provider. OWNER: Ayush.

PAYMENTS_MODE=mock (default) or test. See docs/research/04_engineering.md for headers and gotchas.
"""
from __future__ import annotations


def create_payout(body: dict, idempotency_key: str) -> dict:
    """POST /v1/payouts with X-Payout-Idempotency. Same key + same body -> same payout."""
    raise NotImplementedError("Ayush")


def get_payout(payout_id: str) -> dict:
    raise NotImplementedError("Ayush")


def find_by_reference(reference_id: str) -> dict | None:
    raise NotImplementedError("Ayush")
