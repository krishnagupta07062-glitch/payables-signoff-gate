"""RazorpayX Payouts (test mode) and a mock provider. OWNER: Ayush.

PAYMENTS_MODE=mock (default) or test. See docs/research/04_engineering.md for headers and gotchas.

Both modes share the same semantics:
- same idempotency key + same body -> the same payout (no second payout);
- same idempotency key + a different body -> an error (PayoutRejected), never a new payout;
- reference_id lets us find a payout after a crash (find_by_reference).

The mock keeps its payouts in its own table in the gate database (mock_payouts), so a crash and a
restart see the same "provider" state, exactly like the real API would.

Test mode uses `requests` with basic auth (the razorpay SDK has no payouts resource). Because the
store keeps only last-4 + a keyed hash, the beneficiary account sent in test mode is a test account
number from env RAZORPAYX_TEST_BENEFICIARY (Razorpay test mode moves no money).
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from typing import Optional, Union

from gate.contracts import PaymentAction, canonical_json, now_iso

RZP = "https://api.razorpay.com/v1"
TERMINAL_FAIL = {"failed", "rejected", "reversed", "cancelled"}


class PayoutError(RuntimeError):
    """The provider could not be reached or answered 5xx: the outcome is UNKNOWN. Retry with the
    SAME key and body; never mint a new key."""


class PayoutRejected(RuntimeError):
    """The provider definitively refused the request (4xx, e.g. same key with a different body)."""

    def __init__(self, message: str, status_code: int = 400, response: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response or {}


def mode() -> str:
    return (os.environ.get("PAYMENTS_MODE") or "mock").strip().lower()


def _body_text(body: Union[dict, str]) -> str:
    return body if isinstance(body, str) else canonical_json(body)


# -------------------------------------------------------------------------------- body builder

def _clean(text: str, n: int) -> str:
    """RazorpayX accepts only letters, digits and spaces in narration and names."""
    import re
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9 ]", " ", text)).strip()[:n] or "Vendor"


def build_body(action: PaymentAction, reference_id: str, holder_name: str = "", narration: str = "") -> dict:
    """The exact payout body. The executor freezes canonical_json(body) in the outbox and replays
    those bytes; it never rebuilds the body for a retry."""
    body = {
        "account_number": os.environ.get("RAZORPAYX_ACCOUNT_NUMBER", "MOCK-SOURCE-ACCOUNT"),
        "amount": int(action.amount_paise),
        "currency": "INR",
        "mode": "IMPS",
        "purpose": action.purpose or "vendor bill",
        "queue_if_low_balance": True,
        "reference_id": reference_id[:40],
        "narration": _clean(narration or "Vendor bill", 30),
        "fund_account": {
            "account_type": "bank_account",
            "bank_account": {
                "name": _clean(holder_name or action.vendor_id, 120),
                "ifsc": action.ifsc,
                "account_number": os.environ.get("RAZORPAYX_TEST_BENEFICIARY", "765432123456789")
                if mode() == "test" else f"XXXX{action.account_last4}",
            },
            "contact": {"name": _clean(holder_name or action.vendor_id, 50), "type": "vendor",
                        "reference_id": action.vendor_id[:40]},
        },
        "notes": {"invoice_key": action.invoice_key[:250], "vendor_id": action.vendor_id[:250],
                  "account_hash_prefix": action.account_hash[:16]},
    }
    return body


# ----------------------------------------------------------------------------------- mock mode

_MOCK_SCHEMA = """CREATE TABLE IF NOT EXISTS mock_payouts(
    idempotency_key TEXT PRIMARY KEY, body_hash TEXT NOT NULL, payout_id TEXT UNIQUE NOT NULL,
    reference_id TEXT, amount INTEGER, status TEXT, created_at TEXT, polls INTEGER DEFAULT 0)"""


def _mock_con():
    from gate import store
    con = store.connect()
    con.execute(_MOCK_SCHEMA)
    return con


def _mock_view(r) -> dict:
    return {"id": r["payout_id"], "entity": "payout", "status": r["status"], "amount": r["amount"],
            "reference_id": r["reference_id"], "created_at": r["created_at"], "mode": "mock",
            "idempotency_key": r["idempotency_key"]}


def _mock_create(body_text: str, key: str) -> dict:
    body_hash = hashlib.sha256(json.dumps(json.loads(body_text), sort_keys=True).encode()).hexdigest()
    body = json.loads(body_text)
    con = _mock_con()
    try:
        con.execute("BEGIN IMMEDIATE")
        r = con.execute("SELECT * FROM mock_payouts WHERE idempotency_key=?", (key,)).fetchone()
        if r is not None:
            con.execute("COMMIT")
            if r["body_hash"] != body_hash:
                raise PayoutRejected("Different request body sent for the same Idempotency Header", 400)
            return _mock_view(r)
        pid = "pout_mock_" + uuid.uuid4().hex[:14]
        con.execute("INSERT INTO mock_payouts(idempotency_key, body_hash, payout_id, reference_id, amount, "
                    "status, created_at) VALUES(?,?,?,?,?,?,?)",
                    (key, body_hash, pid, body.get("reference_id"), body.get("amount"), "processing", now_iso()))
        con.execute("COMMIT")
        r = con.execute("SELECT * FROM mock_payouts WHERE idempotency_key=?", (key,)).fetchone()
        return _mock_view(r)
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def _mock_get(payout_id: str) -> dict:
    con = _mock_con()
    try:
        r = con.execute("SELECT * FROM mock_payouts WHERE payout_id=?", (payout_id,)).fetchone()
        if r is None:
            raise PayoutRejected(f"payout {payout_id} not found", 404)
        # The mock settles on the first poll: processing -> processed.
        if r["status"] == "processing":
            con.execute("UPDATE mock_payouts SET status='processed', polls=polls+1 WHERE payout_id=?", (payout_id,))
            r = con.execute("SELECT * FROM mock_payouts WHERE payout_id=?", (payout_id,)).fetchone()
        return _mock_view(r)
    finally:
        con.close()


def _mock_find(reference_id: str) -> Optional[dict]:
    con = _mock_con()
    try:
        r = con.execute("SELECT * FROM mock_payouts WHERE reference_id=? ORDER BY created_at LIMIT 1",
                        (reference_id[:40],)).fetchone()
        return _mock_view(r) if r else None
    finally:
        con.close()


def mock_payouts() -> list[dict]:
    """Every payout the mock provider has made (what the 'provider dashboard' would show)."""
    con = _mock_con()
    try:
        return [_mock_view(r) for r in con.execute("SELECT * FROM mock_payouts ORDER BY created_at")]
    finally:
        con.close()


# ----------------------------------------------------------------------------------- test mode

def _auth():
    kid, secret = os.environ.get("RAZORPAY_KEY_ID"), os.environ.get("RAZORPAY_KEY_SECRET")
    if not kid or not secret:
        raise PayoutError("PAYMENTS_MODE=test but RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are not set")
    if not kid.startswith("rzp_test_"):
        raise PayoutRejected("refusing to use a non-test Razorpay key", 400)
    return (kid, secret)


def _rzp(method: str, path: str, *, data: Optional[str] = None, params: Optional[dict] = None,
         headers: Optional[dict] = None, timeout: float = 15) -> dict:
    import requests
    try:
        r = requests.request(method, RZP + path, auth=_auth(), data=data, params=params, timeout=timeout,
                             headers={"Content-Type": "application/json", **(headers or {})})
    except requests.RequestException as e:
        raise PayoutError(f"RazorpayX unreachable: {e!r}"[:300]) from e
    try:
        j = r.json()
    except ValueError:
        j = {"raw": r.text[:300]}
    if r.status_code >= 500 or r.status_code == 429:
        raise PayoutError(f"RazorpayX {r.status_code}: {json.dumps(j)[:300]}")
    if r.status_code >= 400:
        msg = (j.get("error") or {}).get("description") if isinstance(j, dict) else None
        raise PayoutRejected(f"RazorpayX {r.status_code}: {msg or j}"[:300], r.status_code, j)
    return j


# ------------------------------------------------------------------------------------ interface

def create_payout(body: Union[dict, str], idempotency_key: str) -> dict:
    """POST /v1/payouts with X-Payout-Idempotency. Same key + same body -> same payout.
    `body` may be the exact JSON string frozen in the outbox (preferred: its bytes are replayed)."""
    if not (4 <= len(idempotency_key) <= 36):
        raise PayoutRejected("idempotency key must be 4-36 characters", 400)
    text = _body_text(body)
    if mode() == "test":
        return _rzp("POST", "/payouts", data=text, headers={"X-Payout-Idempotency": idempotency_key})
    return _mock_create(text, idempotency_key)


def get_payout(payout_id: str) -> dict:
    if mode() == "test":
        return _rzp("GET", f"/payouts/{payout_id}")
    return _mock_get(payout_id)


def find_by_reference(reference_id: str) -> dict | None:
    """Reconciliation after a crash: the payout we already made for this outbox row, if any."""
    if mode() == "test":
        j = _rzp("GET", "/payouts", params={"account_number": os.environ.get("RAZORPAYX_ACCOUNT_NUMBER", ""),
                                            "reference_id": reference_id[:40]})
        items = [p for p in j.get("items", []) if p.get("status") not in TERMINAL_FAIL]
        return items[0] if items else None
    return _mock_find(reference_id)
