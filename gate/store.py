"""SQLite store.

Tables: vendors, vendor_accounts, requests, decisions, approvals, receipts, outbox, payouts, calls,
ledger (WAL mode). Account numbers are stored only as last-4 plus a keyed hash (HMAC-SHA256 with
ACCOUNT_HASH_KEY); a full number never reaches the database.

Every write of a decision, approval or payout also appends a ledger event in the same transaction.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

from gate import keys
from gate.contracts import (BankAccount, Check, CheckStatus, Claims, Contact, Decision, PaymentAction,
                            Reason, Request, RequestKind, Source, Vendor, Verdict, canonical_json,
                            now_iso, to_dict)

ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB = ROOT / "runs" / "gate.sqlite"
_db_path: Optional[str] = None
_init_lock = threading.Lock()
_initialised: set[str] = set()

SCHEMA = """
CREATE TABLE IF NOT EXISTS vendors(
    vendor_id TEXT PRIMARY KEY, legal_name TEXT NOT NULL, gstin TEXT, pan TEXT, state_code TEXT,
    country TEXT, domains TEXT, crustdata_company_id INTEGER, contacts TEXT,
    per_payment_limit_inr REAL, per_day_limit_inr REAL, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS vendor_accounts(
    vendor_id TEXT NOT NULL, ifsc TEXT, last4 TEXT, account_hash TEXT NOT NULL, holder TEXT,
    verified_at TEXT, added_at TEXT, status TEXT DEFAULT 'active',
    PRIMARY KEY(vendor_id, account_hash));
CREATE INDEX IF NOT EXISTS ix_accounts_hash ON vendor_accounts(account_hash);
CREATE TABLE IF NOT EXISTS requests(
    request_id TEXT PRIMARY KEY, kind TEXT, vendor_id TEXT, sender TEXT, sender_display TEXT,
    reply_to TEXT, received_at TEXT, raw_text_hash TEXT, po TEXT, attachments TEXT, claims TEXT);
CREATE TABLE IF NOT EXISTS decisions(
    request_id TEXT PRIMARY KEY, vendor_id TEXT, verdict TEXT, rules TEXT, reasons TEXT, checks TEXT,
    action TEXT, action_hash TEXT, idempotency_key TEXT, policy_version TEXT, decided_at TEXT,
    state TEXT NOT NULL, decision TEXT, updated_at TEXT);
CREATE INDEX IF NOT EXISTS ix_decisions_state ON decisions(state);
CREATE TABLE IF NOT EXISTS approvals(
    id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL, approver TEXT, approve INTEGER,
    note TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS receipts(
    nonce TEXT PRIMARY KEY, request_id TEXT, action_hash TEXT, approver TEXT, expires_at TEXT,
    issued_at TEXT, used_at TEXT);
CREATE TABLE IF NOT EXISTS outbox(
    idempotency_key TEXT PRIMARY KEY, request_id TEXT, action_hash TEXT, body TEXT NOT NULL,
    state TEXT NOT NULL, payout_id TEXT, attempts INTEGER DEFAULT 0, last_error TEXT,
    created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS payouts(
    payout_id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE, request_id TEXT, status TEXT,
    amount_paise INTEGER, mode TEXT, at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS calls(
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, run_id TEXT, provider TEXT, endpoint TEXT,
    credits REAL, cached INTEGER, request_id TEXT, tokens_in INTEGER, tokens_out INTEGER, note TEXT,
    UNIQUE(run_id, ts, endpoint, request_id, note));
CREATE TABLE IF NOT EXISTS ledger(
    id INTEGER PRIMARY KEY AUTOINCREMENT, prev_hash TEXT NOT NULL, hash TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL, body TEXT NOT NULL, at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS ledger_no_update BEFORE UPDATE ON ledger
    BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS ledger_no_delete BEFORE DELETE ON ledger
    BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
"""

# Decision states
DECIDED, ESCALATED, APPROVED, REJECTED, PAID = "DECIDED", "ESCALATED", "APPROVED", "REJECTED", "PAID"
_TERMINAL = (APPROVED, REJECTED, PAID)


# ----------------------------------------------------------------------------------- connections

def db_path() -> str:
    return _db_path or os.environ.get("GATE_DB") or str(_DEFAULT_DB)


def connect(path: Optional[str] = None) -> sqlite3.Connection:
    """A new autocommit connection (one per call: safe across Streamlit threads)."""
    p = path or db_path()
    if p not in _initialised:
        _create(p)
    con = sqlite3.connect(p, timeout=30, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    return con


@contextmanager
def tx(con: Optional[sqlite3.Connection] = None) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE ... COMMIT (or ROLLBACK on error). Writers serialise, so the ledger chain
    and the conditional UPDATEs never race."""
    own = con is None
    con = con or connect()
    con.execute("BEGIN IMMEDIATE")
    try:
        yield con
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    finally:
        if own:
            con.close()


def _create(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=30, isolation_level=None)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(SCHEMA)
    finally:
        con.close()
    _initialised.add(path)


def init_db(path: Optional[str] = None) -> None:
    """Create tables if missing. Default path: runs/gate.sqlite (env GATE_DB).
    Passing a path makes it the store's database for the rest of the process."""
    global _db_path
    with _init_lock:
        if path is not None:
            _db_path = str(path)
        _create(db_path())


# ----------------------------------------------------------------------------- account hashing

def hash_account(account_number: str) -> str:
    """HMAC-SHA256(ACCOUNT_HASH_KEY, digits). Delegates to the shared gate.keys.account_hash so the
    store, the verifiers and the payouts agree byte for byte."""
    return keys.account_hash(str(account_number))


def last4(account_number: str) -> str:
    digits = "".join(ch for ch in str(account_number) if ch.isdigit())
    return digits[-4:]


def _redact_claims(claims: Any) -> Optional[dict]:
    """Claims as a dict with the full pay-to account replaced by last-4 + keyed hash."""
    if claims is None:
        return None
    d = to_dict(claims) if not isinstance(claims, dict) else dict(claims)
    acct = d.get("pay_to_account")
    if acct and not str(acct).startswith("hash:"):
        d["pay_to_account_last4"] = last4(acct)
        d["pay_to_account_hash"] = hash_account(acct)
        d["pay_to_account"] = None
    return d


# ------------------------------------------------------------------------------------- vendors

def _account_from_fixture(a: dict) -> BankAccount:
    if a.get("account_number"):
        num = str(a["account_number"])
        return BankAccount(ifsc=a.get("ifsc", ""), account_last4=last4(num), account_hash=hash_account(num),
                           holder_name=a.get("holder_name") or a.get("holder", ""),
                           verified_at=a.get("verified_at"), added_at=a.get("added_at"))
    return BankAccount(ifsc=a.get("ifsc", ""), account_last4=a.get("account_last4", ""),
                       account_hash=a["account_hash"], holder_name=a.get("holder_name") or a.get("holder", ""),
                       verified_at=a.get("verified_at"), added_at=a.get("added_at"))


def vendor_from_dict(d: dict) -> Vendor:
    return Vendor(
        vendor_id=d["vendor_id"], legal_name=d["legal_name"], gstin=d.get("gstin"), pan=d.get("pan"),
        state_code=d.get("state_code"), country=d.get("country", "IN"), domains=list(d.get("domains", [])),
        crustdata_company_id=d.get("crustdata_company_id"),
        bank_accounts=[_account_from_fixture(a) for a in d.get("bank_accounts", [])],
        contacts=[Contact(**{k: c.get(k) for k in ("name", "role", "email", "phone_on_file", "recorded_at")})
                  for c in d.get("contacts", [])],
        per_payment_limit_inr=float(d.get("per_payment_limit_inr", 500000.0)),
        per_day_limit_inr=float(d.get("per_day_limit_inr", 1000000.0)),
        created_at=d.get("created_at"))


def upsert_vendor(vendor: Vendor, con: Optional[sqlite3.Connection] = None) -> None:
    with tx(con) as c:
        c.execute(
            """INSERT INTO vendors(vendor_id, legal_name, gstin, pan, state_code, country, domains,
                   crustdata_company_id, contacts, per_payment_limit_inr, per_day_limit_inr, created_at, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(vendor_id) DO UPDATE SET legal_name=excluded.legal_name, gstin=excluded.gstin,
                   pan=excluded.pan, state_code=excluded.state_code, country=excluded.country,
                   domains=excluded.domains, crustdata_company_id=excluded.crustdata_company_id,
                   contacts=excluded.contacts, per_payment_limit_inr=excluded.per_payment_limit_inr,
                   per_day_limit_inr=excluded.per_day_limit_inr, updated_at=excluded.updated_at""",
            (vendor.vendor_id, vendor.legal_name, vendor.gstin, vendor.pan, vendor.state_code, vendor.country,
             json.dumps(vendor.domains), vendor.crustdata_company_id,
             json.dumps(to_dict(vendor.contacts), ensure_ascii=False), vendor.per_payment_limit_inr,
             vendor.per_day_limit_inr, vendor.created_at or now_iso(), now_iso()))
        c.execute("DELETE FROM vendor_accounts WHERE vendor_id=?", (vendor.vendor_id,))
        for a in vendor.bank_accounts:
            c.execute(
                """INSERT OR REPLACE INTO vendor_accounts(vendor_id, ifsc, last4, account_hash, holder,
                       verified_at, added_at, status) VALUES(?,?,?,?,?,?,?, 'active')""",
                (vendor.vendor_id, a.ifsc, a.account_last4, a.account_hash, a.holder_name, a.verified_at,
                 a.added_at))


def get_vendor(vendor_id: str) -> Optional[Vendor]:
    if not vendor_id:
        return None
    con = connect()
    try:
        r = con.execute("SELECT * FROM vendors WHERE vendor_id=?", (vendor_id,)).fetchone()
        if r is None:
            return None
        accts = con.execute("SELECT * FROM vendor_accounts WHERE vendor_id=? AND status='active' "
                            "ORDER BY added_at", (vendor_id,)).fetchall()
    finally:
        con.close()
    return Vendor(
        vendor_id=r["vendor_id"], legal_name=r["legal_name"], gstin=r["gstin"], pan=r["pan"],
        state_code=r["state_code"], country=r["country"] or "IN", domains=json.loads(r["domains"] or "[]"),
        crustdata_company_id=r["crustdata_company_id"],
        bank_accounts=[BankAccount(ifsc=a["ifsc"], account_last4=a["last4"], account_hash=a["account_hash"],
                                   holder_name=a["holder"], verified_at=a["verified_at"], added_at=a["added_at"])
                       for a in accts],
        contacts=[Contact(**c) for c in json.loads(r["contacts"] or "[]")],
        per_payment_limit_inr=r["per_payment_limit_inr"], per_day_limit_inr=r["per_day_limit_inr"],
        created_at=r["created_at"])


def list_vendors() -> list[Vendor]:
    con = connect()
    try:
        ids = [r[0] for r in con.execute("SELECT vendor_id FROM vendors ORDER BY vendor_id")]
    finally:
        con.close()
    return [v for v in (get_vendor(i) for i in ids) if v]


def find_vendor_by_domain(domain: str) -> Optional[Vendor]:
    domain = (domain or "").lower().strip()
    for v in list_vendors():
        if domain in [d.lower() for d in v.domains]:
            return v
    return None


def load_fixtures(path: Optional[str] = None) -> int:
    """Load fixtures/vendors.json (a list of vendors, or {"vendors": [...]}) into the vendor tables.
    Full account numbers in a fixture are hashed on the way in. Returns the number loaded."""
    p = Path(path) if path else ROOT / "fixtures" / "vendors.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    items = data.get("vendors", []) if isinstance(data, dict) else data
    for d in items:
        upsert_vendor(vendor_from_dict(d))
    return len(items)


# ------------------------------------------------------------------------------------ requests

def save_request(request: Request, claims: Optional[Claims] = None) -> None:
    """Raw text is stored as a SHA-256 only; the untrusted text itself is not kept."""
    with tx() as c:
        c.execute(
            """INSERT INTO requests(request_id, kind, vendor_id, sender, sender_display, reply_to, received_at,
                   raw_text_hash, po, attachments, claims) VALUES(?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(request_id) DO UPDATE SET kind=excluded.kind, vendor_id=excluded.vendor_id,
                   sender=excluded.sender, sender_display=excluded.sender_display, reply_to=excluded.reply_to,
                   raw_text_hash=excluded.raw_text_hash, po=excluded.po, attachments=excluded.attachments,
                   claims=COALESCE(excluded.claims, requests.claims)""",
            (request.request_id, to_dict(request.kind), request.vendor_id, request.sender_email,
             request.sender_display, request.reply_to, request.received_at,
             hashlib.sha256((request.raw_text or "").encode("utf-8")).hexdigest(),
             json.dumps(request.po) if request.po is not None else None, json.dumps(request.attachments),
             canonical_json(_redact_claims(claims)) if claims is not None else None))
        _ledger_append(c, "request", {"request_id": request.request_id, "kind": to_dict(request.kind),
                                      "vendor_id": request.vendor_id, "sender": request.sender_email,
                                      "received_at": request.received_at})


def get_request_row(request_id: str) -> Optional[dict]:
    con = connect()
    try:
        r = con.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()
    finally:
        con.close()
    return dict(r) if r else None


# ----------------------------------------------------------------------------------- decisions

def decision_to_dict(decision: Decision) -> dict:
    d = to_dict(decision)
    d["claims"] = _redact_claims(decision.claims)
    return d


def decision_from_dict(d: dict) -> Decision:
    """Inverse of decision_to_dict (claims come back redacted: pay_to_account is None)."""
    def src(s: dict) -> Source:
        return Source(**{k: s.get(k) for k in ("kind", "ref", "retrieved_at", "request_id", "record_id",
                                               "record_date", "excerpt")})

    checks = [Check(name=c["name"], status=CheckStatus(c["status"]), value=c.get("value") or {},
                    sources=[src(s) for s in c.get("sources", [])], credits=c.get("credits", 0.0),
                    note=c.get("note", "")) for c in d.get("checks", [])]
    reasons = [Reason(rule_id=r["rule_id"], text=r["text"], check_names=r.get("check_names", []))
               for r in d.get("reasons", [])]
    action = PaymentAction(**d["action"]) if d.get("action") else None
    claims = None
    if d.get("claims"):
        fields = Claims.__dataclass_fields__
        claims = Claims(**{k: v for k, v in d["claims"].items() if k in fields})
    return Decision(request_id=d["request_id"], verdict=Verdict(d["verdict"]), rule_ids=list(d.get("rule_ids", [])),
                    reasons=reasons, checks=checks, policy_version=d.get("policy_version", ""), action=action,
                    action_hash=d.get("action_hash"), decided_at=d.get("decided_at") or now_iso(), claims=claims)


def save_decision(decision: Decision) -> None:
    """Persist the decision; ESCALATE decisions enter the approval queue (state='ESCALATED').
    A decision already approved, rejected or paid keeps its state (a re-run never reopens it)."""
    d = decision_to_dict(decision)
    state = ESCALATED if decision.verdict == Verdict.ESCALATE else DECIDED
    vendor_id = decision.action.vendor_id if decision.action else None
    with tx() as c:
        if vendor_id is None:
            r = c.execute("SELECT vendor_id FROM requests WHERE request_id=?", (decision.request_id,)).fetchone()
            vendor_id = r["vendor_id"] if r else None
        c.execute(
            """INSERT INTO decisions(request_id, vendor_id, verdict, rules, reasons, checks, action, action_hash,
                   idempotency_key, policy_version, decided_at, state, decision, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(request_id) DO UPDATE SET
                   vendor_id=excluded.vendor_id, verdict=excluded.verdict, rules=excluded.rules,
                   reasons=excluded.reasons, checks=excluded.checks, action=excluded.action,
                   action_hash=excluded.action_hash, idempotency_key=excluded.idempotency_key,
                   policy_version=excluded.policy_version, decided_at=excluded.decided_at,
                   decision=excluded.decision, updated_at=excluded.updated_at,
                   state=CASE WHEN decisions.state IN ('APPROVED','REJECTED','PAID') THEN decisions.state
                              ELSE excluded.state END
               WHERE decisions.state NOT IN ('APPROVED','REJECTED','PAID')""",
            (decision.request_id, vendor_id, d["verdict"], json.dumps(d["rule_ids"]),
             json.dumps(d["reasons"], ensure_ascii=False), json.dumps(d["checks"], ensure_ascii=False),
             json.dumps(d["action"]) if d["action"] else None, decision.action_hash,
             decision.action.idempotency_key if decision.action else None, decision.policy_version,
             decision.decided_at, state, canonical_json(d), now_iso()))
        if decision.claims is not None:
            c.execute("UPDATE requests SET claims=? WHERE request_id=?",
                      (canonical_json(d["claims"]), decision.request_id))
        _ledger_append(c, "decision", {"request_id": decision.request_id, "verdict": d["verdict"],
                                       "rule_ids": d["rule_ids"], "policy_version": decision.policy_version,
                                       "action_hash": decision.action_hash,
                                       "checks": [{"name": ch["name"], "status": ch["status"]} for ch in d["checks"]],
                                       "state": state})


def get_decision(request_id: str) -> Optional[Decision]:
    row = get_decision_row(request_id)
    return decision_from_dict(json.loads(row["decision"])) if row else None


def get_decision_row(request_id: str) -> Optional[dict]:
    con = connect()
    try:
        r = con.execute("SELECT * FROM decisions WHERE request_id=?", (request_id,)).fetchone()
    finally:
        con.close()
    return dict(r) if r else None


def list_decisions(limit: int = 500) -> list[dict]:
    con = connect()
    try:
        rows = con.execute(
            """SELECT d.request_id, d.vendor_id, d.verdict, d.rules, d.state, d.decided_at, d.action_hash,
                      d.idempotency_key, r.kind, r.sender, r.received_at
               FROM decisions d LEFT JOIN requests r ON r.request_id = d.request_id
               ORDER BY d.decided_at DESC, d.request_id LIMIT ?""", (limit,)).fetchall()
    finally:
        con.close()
    out = []
    for r in rows:
        d = dict(r)
        d["rule_ids"] = json.loads(d.pop("rules") or "[]")
        out.append(d)
    return out


def set_decision_state(con: sqlite3.Connection, request_id: str, state: str) -> None:
    con.execute("UPDATE decisions SET state=?, updated_at=? WHERE request_id=?", (state, now_iso(), request_id))


def history_for(vendor_id: Optional[str] = None) -> list[dict]:
    """Prior requests with: request_id, vendor_id, invoice_key, invoice_number, amount_inr,
    invoice_date, account_hash, verdict, paid (bool). vendor_id=None returns all vendors."""
    con = connect()
    try:
        q = """SELECT d.request_id, COALESCE(d.vendor_id, r.vendor_id) AS vendor_id, d.verdict, d.state,
                      d.action, d.idempotency_key, r.claims, r.received_at,
                      (SELECT COUNT(*) FROM payouts p WHERE p.idempotency_key = d.idempotency_key
                           AND p.status NOT IN ('failed','rejected','reversed','cancelled')) AS n_paid
               FROM decisions d LEFT JOIN requests r ON r.request_id = d.request_id"""
        args: tuple = ()
        if vendor_id is not None:
            q += " WHERE COALESCE(d.vendor_id, r.vendor_id) = ?"
            args = (vendor_id,)
        rows = con.execute(q + " ORDER BY d.decided_at", args).fetchall()
    finally:
        con.close()
    out = []
    for r in rows:
        action = json.loads(r["action"]) if r["action"] else {}
        claims = json.loads(r["claims"]) if r["claims"] else {}
        out.append({
            "request_id": r["request_id"],
            "vendor_id": r["vendor_id"],
            "invoice_key": action.get("invoice_key"),
            "invoice_number": claims.get("invoice_number"),
            "amount_inr": claims.get("amount_inr") if claims.get("amount_inr") is not None
            else (action["amount_paise"] / 100 if action.get("amount_paise") is not None else None),
            "invoice_date": claims.get("invoice_date"),
            "account_hash": action.get("account_hash") or claims.get("pay_to_account_hash"),
            "verdict": r["verdict"],
            "state": r["state"],
            "received_at": r["received_at"],
            "paid": bool(r["n_paid"]) or r["state"] == PAID,
        })
    return out


def pending_escalations() -> list[dict]:
    con = connect()
    try:
        rows = con.execute(
            """SELECT d.request_id, d.vendor_id, d.verdict, d.rules, d.reasons, d.decided_at, d.action_hash,
                      r.kind, r.sender FROM decisions d LEFT JOIN requests r ON r.request_id = d.request_id
               WHERE d.state = 'ESCALATED' ORDER BY d.decided_at""").fetchall()
    finally:
        con.close()
    return [{"request_id": r["request_id"], "vendor_id": r["vendor_id"], "verdict": r["verdict"],
             "rule_ids": json.loads(r["rules"] or "[]"), "reasons": json.loads(r["reasons"] or "[]"),
             "decided_at": r["decided_at"], "action_hash": r["action_hash"], "kind": r["kind"],
             "sender": r["sender"]} for r in rows]


class ApprovalRefused(ValueError):
    """The approval breaks an approver rule; nothing was recorded."""


class SecondApproverNeeded(Exception):
    """The first of two required approvals was recorded; a different approver must approve too."""


DEFAULT_APPROVERS = "finance.controller,ap.lead,cfo"
DEFAULT_TWO_PERSON_MIN_INR = 500000  # ₹5 lakh


def approvers() -> set[str]:
    """Who may approve or reject: APPROVERS (comma-separated), else the demo default."""
    raw = os.environ.get("APPROVERS") or DEFAULT_APPROVERS
    return {a.strip().lower() for a in raw.split(",") if a.strip()}


def two_person_min_paise() -> int:
    try:
        return int(float(os.environ.get("TWO_PERSON_MIN_INR") or DEFAULT_TWO_PERSON_MIN_INR) * 100)
    except ValueError:
        return DEFAULT_TWO_PERSON_MIN_INR * 100


def _approval_problem(approver: str, approve: bool, note: str, req: dict) -> Optional[str]:
    who = (approver or "").strip().lower()
    if who not in approvers():
        return f"{approver or '(blank)'} is not an approver (allowed: {', '.join(sorted(approvers()))})"
    sender = (req.get("sender") or "").strip().lower()
    if sender and who in (sender, sender.split("@")[0]):
        return "the requester cannot approve their own request (maker-checker)"
    if approve and req.get("kind") == "bank_change" and not (note or "").strip():
        return "a bank change needs a note recording the call-back on the number on file"
    return None


def record_approval(request_id: str, approver: str, approve: bool, note: str = "") -> bool:
    """Atomic: UPDATE ... WHERE state='ESCALATED'. Returns False if already decided (double click).

    Approver rules (enforced here, not only in the UI): the approver must be on the APPROVERS list, cannot be
    the requester, and must leave a call-back note to approve a bank change (ApprovalRefused). A payment of
    TWO_PERSON_MIN_INR or more needs two different approvers: the first approval is recorded and
    SecondApproverNeeded is raised; the second one moves the decision to APPROVED.
    """
    new_state = APPROVED if approve else REJECTED
    needs_second = False
    with tx() as c:
        row = c.execute("SELECT state, decision FROM decisions WHERE request_id=?", (request_id,)).fetchone()
        if not row or row["state"] != ESCALATED:
            return False
        req = c.execute("SELECT kind, sender FROM requests WHERE request_id=?", (request_id,)).fetchone()
        problem = _approval_problem(approver, approve, note, dict(req) if req else {})
        if problem:
            raise ApprovalRefused(problem)
        action = (json.loads(row["decision"] or "{}") or {}).get("action") or {}
        if approve and (action.get("amount_paise") or 0) >= two_person_min_paise():
            prior = {r["approver"].strip().lower() for r in c.execute(
                "SELECT approver FROM approvals WHERE request_id=? AND approve=1", (request_id,))}
            if approver.strip().lower() in prior:
                raise ApprovalRefused("a payment this large needs a second, different approver")
            if not prior:
                needs_second = True
        if not needs_second:
            cur = c.execute("UPDATE decisions SET state=?, updated_at=? WHERE request_id=? AND state='ESCALATED'",
                            (new_state, now_iso(), request_id))
            if cur.rowcount != 1:
                return False
        at = now_iso()
        c.execute("INSERT INTO approvals(request_id, approver, approve, note, at) VALUES(?,?,?,?,?)",
                  (request_id, approver, int(bool(approve)), note, at))
        _ledger_append(c, "approval", {"request_id": request_id, "approver": approver, "approve": bool(approve),
                                       "note": note, "at": at, "first_of_two": needs_second})
    if needs_second:
        raise SecondApproverNeeded(f"first approval recorded by {approver}; a second, different approver must approve")
    return True


def approvals_for(request_id: str) -> list[dict]:
    con = connect()
    try:
        return [dict(r) for r in con.execute("SELECT * FROM approvals WHERE request_id=? ORDER BY id",
                                             (request_id,))]
    finally:
        con.close()


# ------------------------------------------------------------------------- payouts (read side)

def list_payouts() -> list[dict]:
    con = connect()
    try:
        return [dict(r) for r in con.execute(
            """SELECT p.*, o.state AS outbox_state, o.attempts FROM payouts p
               LEFT JOIN outbox o ON o.idempotency_key = p.idempotency_key ORDER BY p.at""")]
    finally:
        con.close()


def list_outbox() -> list[dict]:
    con = connect()
    try:
        return [dict(r) for r in con.execute("SELECT * FROM outbox ORDER BY created_at")]
    finally:
        con.close()


# ------------------------------------------------------------------------------- calls mirror

def record_calls(budget) -> int:
    """Mirror a RunBudget's call lines into the calls table (idempotent). Returns rows added."""
    n = 0
    with tx() as c:
        for line in budget.calls:
            cur = c.execute(
                """INSERT OR IGNORE INTO calls(ts, run_id, provider, endpoint, credits, cached, request_id,
                       tokens_in, tokens_out, note) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (line["ts"], line["run_id"], line["provider"], line["endpoint"], line["credits"],
                 int(line["cached"]), line.get("request_id"), line.get("tokens_in", 0),
                 line.get("tokens_out", 0), line.get("note", "")))
            n += cur.rowcount
    return n


def credits_summary() -> list[dict]:
    con = connect()
    try:
        return [dict(r) for r in con.execute(
            """SELECT run_id, provider, COUNT(*) AS calls, SUM(cached) AS cached_calls,
                      ROUND(SUM(credits), 3) AS credits FROM calls GROUP BY run_id, provider
               ORDER BY MIN(ts) DESC""")]
    finally:
        con.close()


# ------------------------------------------------------------------------------------- internals

def _ledger_append(con: sqlite3.Connection, event_type: str, payload: dict) -> str:
    from gate import ledger  # late import: ledger uses this module's connections
    return ledger.append(event_type, payload, con=con)
