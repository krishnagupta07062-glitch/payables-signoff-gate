"""SQLite store. OWNER: Ayush.

Tables: vendors, requests, decisions, approvals, outbox, payouts, calls, ledger (WAL mode).
Account numbers are stored only as last-4 plus a keyed hash.
"""
from __future__ import annotations

from typing import Optional

from gate.contracts import Decision, Request, Vendor


def init_db(path: Optional[str] = None) -> None:
    """Create tables if missing. Default path: runs/gate.sqlite (env GATE_DB)."""
    raise NotImplementedError("Ayush")


def upsert_vendor(vendor: Vendor) -> None:
    raise NotImplementedError("Ayush")


def get_vendor(vendor_id: str) -> Optional[Vendor]:
    raise NotImplementedError("Ayush")


def save_request(request: Request) -> None:
    raise NotImplementedError("Ayush")


def save_decision(decision: Decision) -> None:
    """Persist the decision; ESCALATE decisions enter the approval queue (state='ESCALATED')."""
    raise NotImplementedError("Ayush")


def history_for(vendor_id: Optional[str] = None) -> list[dict]:
    """Prior requests with: request_id, vendor_id, invoice_key, invoice_number, amount_inr,
    invoice_date, account_hash, verdict, paid (bool). vendor_id=None returns all vendors."""
    raise NotImplementedError("Ayush")


def pending_escalations() -> list[dict]:
    raise NotImplementedError("Ayush")


def record_approval(request_id: str, approver: str, approve: bool, note: str = "") -> bool:
    """Atomic: UPDATE ... WHERE state='ESCALATED'. Returns False if already decided (double click)."""
    raise NotImplementedError("Ayush")
