"""Exactly-once payment executor.

The executor is the enforcement point: it refuses any payment without a receipt whose action hash,
expiry and single-use nonce match. Fails closed.

Exactly once comes from three things (no engine gives exactly-once external side effects alone):
  (a) a durable intent committed BEFORE the provider call: the outbox row, state 'unknown',
      holding the exact JSON body;
  (b) a provider idempotency key derived from the invoice fingerprint (decision.action.idempotency_key),
      never from the attempt; a retry replays the identical key and body bytes;
  (c) reconciliation by reference_id after a crash (find_by_reference) before any resend.

Outbox states: unknown (intent committed, may or may not have reached the provider) -> sent
(provider returned a payout id) | failed (provider definitively refused; only a person may issue a
new key). A key is never re-minted while a payout is processing.

GATE_CRASH_AT=after_unknown|after_payout makes the process os._exit() at that point (crash demo/test).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone

from gate import ledger, store
from gate.contracts import Decision, Verdict, action_hash, canonical_json, now_iso
from gate.payments import razorpayx

RECEIPT_TTL = timedelta(minutes=10)
_RECEIPT_FIELDS = ("request_id", "action_hash", "nonce", "expires_at", "approver")


class ExecutionRefused(RuntimeError):
    """The executor will not pay: bad/expired/used receipt, wrong action hash, or wrong state."""


# ------------------------------------------------------------------------------------- receipts

def _receipt_key() -> bytes:
    k = os.environ.get("RECEIPT_SIGNING_KEY") or os.environ.get("ACCOUNT_HASH_KEY") or "dev-only-receipt-key"
    return ("receipt:" + k).encode("utf-8")


def _sign(fields: dict) -> str:
    msg = canonical_json({k: fields[k] for k in _RECEIPT_FIELDS})
    return hmac.new(_receipt_key(), msg.encode("utf-8"), hashlib.sha256).hexdigest()


def _parse(ts: str) -> datetime:
    d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def issue_receipt(decision: Decision, approver: str = "policy") -> dict:
    """For an ALLOW decision, or an ESCALATE a person approved. Returns
    {request_id, action_hash, nonce, expires_at, approver, signature}."""
    if decision.action is None:
        raise ExecutionRefused(f"{decision.request_id}: decision has no payment action")
    row = store.get_decision_row(decision.request_id)
    state = row["state"] if row else None
    if decision.verdict == Verdict.ALLOW:
        if state in (store.REJECTED,):
            raise ExecutionRefused(f"{decision.request_id}: decision was rejected")
    elif decision.verdict == Verdict.ESCALATE:
        if state not in (store.APPROVED, store.PAID):
            raise ExecutionRefused(f"{decision.request_id}: ESCALATE needs a person's approval first (state={state})")
        if approver == "policy":
            raise ExecutionRefused("an escalated payment needs a named human approver, not the policy")
    else:
        raise ExecutionRefused(f"{decision.request_id}: verdict {decision.verdict.value} is never paid")
    ah = action_hash(decision.action)
    if decision.action_hash and decision.action_hash != ah:
        raise ExecutionRefused(f"{decision.request_id}: decision.action_hash does not match its action")
    fields = {"request_id": decision.request_id, "action_hash": ah, "nonce": secrets.token_hex(16),
              "expires_at": (datetime.now(timezone.utc) + RECEIPT_TTL).isoformat(timespec="seconds"),
              "approver": approver}
    fields["signature"] = _sign(fields)
    with store.tx() as c:
        c.execute("INSERT INTO receipts(nonce, request_id, action_hash, approver, expires_at, issued_at) "
                  "VALUES(?,?,?,?,?,?)", (fields["nonce"], fields["request_id"], ah, approver,
                                          fields["expires_at"], now_iso()))
        ledger.append("receipt_issued", {k: fields[k] for k in _RECEIPT_FIELDS}, con=c)
    return fields


def _check_receipt(decision: Decision, receipt: dict) -> str:
    """Returns the action hash, or raises ExecutionRefused. Pure checks; the nonce is spent later
    inside the outbox transaction."""
    if decision.action is None:
        raise ExecutionRefused("decision has no payment action")
    if decision.verdict == Verdict.BLOCK:
        raise ExecutionRefused("BLOCK decisions are never paid")
    try:
        sig = receipt["signature"]
        fields = {k: receipt[k] for k in _RECEIPT_FIELDS}
    except (KeyError, TypeError):
        raise ExecutionRefused("receipt is missing fields")
    if not hmac.compare_digest(sig, _sign(fields)):
        raise ExecutionRefused("receipt signature is invalid")
    if fields["request_id"] != decision.request_id:
        raise ExecutionRefused("receipt is for a different request")
    ah = action_hash(decision.action)
    if fields["action_hash"] != ah or (decision.action_hash and decision.action_hash != ah):
        raise ExecutionRefused("action hash mismatch: the payment differs from what was approved")
    try:
        if _parse(fields["expires_at"]) <= datetime.now(timezone.utc):
            raise ExecutionRefused("receipt has expired")
    except ValueError:
        raise ExecutionRefused("receipt expiry is unreadable")
    row = store.get_decision_row(decision.request_id)
    if row and row["state"] == store.REJECTED:
        raise ExecutionRefused("decision was rejected by a person")
    if decision.verdict == Verdict.ESCALATE and (not row or row["state"] not in (store.APPROVED, store.PAID)):
        raise ExecutionRefused("escalated decision is not approved")
    return ah


# ------------------------------------------------------------------------------------- execute

def _crash_point(name: str) -> None:
    if os.environ.get("GATE_CRASH_AT") == name:
        os._exit(17)


def _holder_for(decision: Decision) -> str:
    v = store.get_vendor(decision.action.vendor_id)
    if not v:
        return decision.action.vendor_id
    for a in v.bank_accounts:
        if a.account_hash == decision.action.account_hash and a.holder_name:
            return a.holder_name
    return v.legal_name


def _result(status: str, payout_id, key: str, replayed: bool, **extra) -> dict:
    return {"status": status, "payout_id": payout_id, "idempotency_key": key, "replayed": replayed, **extra}


def execute(decision: Decision, receipt: dict) -> dict:
    """Outbox row (idempotency key = decision.action.idempotency_key) -> provider payout.
    Returns {status, payout_id, idempotency_key, replayed: bool}."""
    ah = _check_receipt(decision, receipt)
    action = decision.action
    key = action.idempotency_key
    with store.tx() as c:
        # Spend the single-use nonce (atomic: a second use finds used_at set and fails).
        cur = c.execute("UPDATE receipts SET used_at=? WHERE nonce=? AND used_at IS NULL AND request_id=? "
                        "AND action_hash=?", (now_iso(), receipt["nonce"], decision.request_id, ah))
        if cur.rowcount != 1:
            raise ExecutionRefused("receipt nonce is unknown or already used")
        existing = c.execute("SELECT * FROM outbox WHERE idempotency_key=?", (key,)).fetchone()
        if existing is not None:
            if existing["action_hash"] != ah:
                ledger.append("payout_refused", {"request_id": decision.request_id, "idempotency_key": key,
                                                 "reason": "key already used for a different action"}, con=c)
                raise ExecutionRefused("idempotency key already used for a different payment action")
            ledger.append("payout_replayed", {"request_id": decision.request_id, "idempotency_key": key,
                                              "outbox_state": existing["state"],
                                              "payout_id": existing["payout_id"]}, con=c)
        else:
            body = razorpayx.build_body(action, reference_id=key, holder_name=_holder_for(decision),
                                        narration=f"Inv {action.invoice_key.split('|')[1] if '|' in action.invoice_key else ''}")
            body_text = canonical_json(body)
            c.execute("INSERT INTO outbox(idempotency_key, request_id, action_hash, body, state, attempts, "
                      "created_at, updated_at) VALUES(?,?,?,?, 'unknown', 0, ?, ?)",
                      (key, decision.request_id, ah, body_text, now_iso(), now_iso()))
            ledger.append("payout_intent", {"request_id": decision.request_id, "idempotency_key": key,
                                            "action_hash": ah, "amount_paise": action.amount_paise,
                                            "account_last4": action.account_last4, "ifsc": action.ifsc,
                                            "approver": receipt["approver"],
                                            "body_sha256": hashlib.sha256(body_text.encode()).hexdigest(),
                                            "mode": razorpayx.mode()}, con=c)
    if existing is not None:
        if existing["state"] == "sent":
            return _result("sent", existing["payout_id"], key, True)
        if existing["state"] == "failed":
            return _result("failed", None, key, True, error=existing["last_error"])
        # 'unknown': finish it with the identical body and key.
        r = _send(key)
        r["replayed"] = True
        return r
    _crash_point("after_unknown")
    return _send(key)


def _send(key: str) -> dict:
    """Send (or re-send) the frozen outbox body with its key and record the outcome."""
    con = store.connect()
    try:
        row = con.execute("SELECT * FROM outbox WHERE idempotency_key=?", (key,)).fetchone()
        con.execute("UPDATE outbox SET attempts=attempts+1, updated_at=? WHERE idempotency_key=?", (now_iso(), key))
    finally:
        con.close()
    if row is None:
        raise ExecutionRefused(f"no outbox row for {key}")
    if row["state"] == "sent":
        return _result("sent", row["payout_id"], key, True)
    try:
        payout = razorpayx.create_payout(row["body"], key)  # exact stored bytes, same key
    except razorpayx.PayoutRejected as e:
        _record_failure(row, str(e))
        return _result("failed", None, key, False, error=str(e))
    except razorpayx.PayoutError as e:
        with store.tx() as c:
            c.execute("UPDATE outbox SET last_error=?, updated_at=? WHERE idempotency_key=?",
                      (str(e)[:500], now_iso(), key))
            ledger.append("payout_unknown", {"idempotency_key": key, "request_id": row["request_id"],
                                             "error": str(e)[:300]}, con=c)
        return _result("unknown", None, key, False, error=str(e))
    _crash_point("after_payout")
    return _record_sent(row, payout, attempt=row["attempts"] + 1)


def _record_sent(row, payout: dict, attempt: int, adopted: bool = False) -> dict:
    key = row["idempotency_key"]
    body = json.loads(row["body"])
    with store.tx() as c:
        c.execute("INSERT OR IGNORE INTO payouts(payout_id, idempotency_key, request_id, status, amount_paise, "
                  "mode, at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
                  (payout["id"], key, row["request_id"], payout.get("status"), body.get("amount"),
                   razorpayx.mode(), now_iso(), now_iso()))
        c.execute("UPDATE outbox SET state='sent', payout_id=?, last_error=NULL, updated_at=? WHERE idempotency_key=?",
                  (payout["id"], now_iso(), key))
        store.set_decision_state(c, row["request_id"], store.PAID)
        ledger.append("payout_sent", {"idempotency_key": key, "request_id": row["request_id"],
                                      "payout_id": payout["id"], "status": payout.get("status"),
                                      "attempt": attempt, "adopted_by_reference": adopted,
                                      "mode": razorpayx.mode()}, con=c)
    return _result("sent", payout["id"], key, attempt > 1 or adopted, payout_status=payout.get("status"))


def _record_failure(row, error: str) -> None:
    with store.tx() as c:
        c.execute("UPDATE outbox SET state='failed', last_error=?, updated_at=? WHERE idempotency_key=?",
                  (error[:500], now_iso(), row["idempotency_key"]))
        ledger.append("payout_failed", {"idempotency_key": row["idempotency_key"], "request_id": row["request_id"],
                                        "error": error[:300]}, con=c)


# -------------------------------------------------------------------------------------- resume

def resume() -> list[dict]:
    """After a crash: finish every outbox row left 'unknown' with the identical body and key."""
    con = store.connect()
    try:
        rows = con.execute("SELECT * FROM outbox WHERE state='unknown' ORDER BY created_at").fetchall()
    finally:
        con.close()
    out = []
    for row in rows:
        key = row["idempotency_key"]
        found = None
        try:
            found = razorpayx.find_by_reference(key)
        except (razorpayx.PayoutError, razorpayx.PayoutRejected):
            found = None  # resending with the same key is still safe: the provider dedupes it
        if found:
            out.append(_record_sent(row, found, attempt=row["attempts"], adopted=True))
        else:
            out.append(_send(key))
    if rows:
        ledger.append("resume", {"rows": len(rows), "results": [{k: r.get(k) for k in ("idempotency_key", "status",
                                                                                         "payout_id")} for r in out]})
    return out


def refresh_payouts() -> list[dict]:
    """Poll the provider for every non-terminal payout and record status changes (no webhooks)."""
    changed = []
    for p in store.list_payouts():
        if p["status"] in ("processed",) or p["status"] in razorpayx.TERMINAL_FAIL:
            continue
        try:
            cur = razorpayx.get_payout(p["payout_id"])
        except (razorpayx.PayoutError, razorpayx.PayoutRejected):
            continue
        if cur.get("status") != p["status"]:
            with store.tx() as c:
                c.execute("UPDATE payouts SET status=?, updated_at=? WHERE payout_id=?",
                          (cur.get("status"), now_iso(), p["payout_id"]))
                ledger.append("payout_status", {"payout_id": p["payout_id"], "from": p["status"],
                                                "to": cur.get("status")}, con=c)
            changed.append({"payout_id": p["payout_id"], "from": p["status"], "to": cur.get("status")})
    return changed


def pay(decision: Decision, approver: str = "policy") -> dict:
    """Convenience for the pipeline and the UI worker: issue_receipt + execute."""
    return execute(decision, issue_receipt(decision, approver))
