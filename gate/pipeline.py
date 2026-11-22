"""The only module that calls all three parts. OWNER: Krishna.

    trusted vendor record (loaded FIRST) -> extract -> verifiers.run_all -> policy.decide
    -> store.save_decision -> ledger -> executor (ALLOW only)

Until a teammate's module is ready (it raises NotImplementedError), the pipeline falls back to the
fixture's stored mocks and an in-memory store, and says so in the trace. With MOCK=1 it always uses
the stored claims and checks and never touches the network.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from datetime import date
from pathlib import Path
from typing import Any, Optional

from gate import extractor, policy
from gate.contracts import (BankAccount, Check, CheckStatus, Claims, Contact, Decision, Request, RequestKind,
                            Source, Vendor, Verdict, to_dict)
from gate.runbudget import BudgetExceeded, RunBudget

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"


# ------------------------------------------------------------------------------- loading helpers

def _only(cls, d: dict) -> dict:
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in d.items() if k in names}


def vendor_from_dict(d: dict) -> Vendor:
    v = Vendor(**_only(Vendor, d))
    v.bank_accounts = [BankAccount(**_only(BankAccount, a)) for a in d.get("bank_accounts", [])]
    v.contacts = [Contact(**_only(Contact, c)) for c in d.get("contacts", [])]
    return v


def request_from_dict(d: dict) -> Request:
    r = Request(**_only(Request, d))
    r.kind = RequestKind(r.kind)
    return r


def check_from_dict(d: dict) -> Check:
    c = Check(**_only(Check, d))
    c.status = CheckStatus(c.status)
    c.sources = [s if isinstance(s, Source) else Source(**_only(Source, s)) for s in (d.get("sources") or [])]
    if not c.sources:
        c.sources = [Source(kind="fixture", ref="fixtures/requests (synthetic mock)")]
    return c


def load_vendors(path: Optional[Path] = None) -> dict[str, Vendor]:
    vendors = {}
    for p in [path or FIXTURES / "vendors.json", FIXTURES / "private" / "vendors.json"]:
        if p.exists():
            for d in json.loads(p.read_text(encoding="utf-8")):
                vendors[d["vendor_id"]] = vendor_from_dict(d)
    return vendors


def load_case(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def all_case_files() -> list[Path]:
    files = sorted((FIXTURES / "requests").glob("*.json"))
    priv = FIXTURES / "private" / "requests"
    if priv.exists():
        files += sorted(priv.glob("*.json"))
    return files


# ----------------------------------------------------------------------- teammate module adapters

class _MemoryStore:
    """Stand-in for gate.store until Ayush's store is ready. Same function names."""

    def __init__(self):
        self.decisions: list[dict] = []

    def save_decision(self, d: Decision) -> None:
        self.decisions.append(to_dict(d))

    def history_for(self, vendor_id: Optional[str] = None) -> list[dict]:
        out = []
        for d in self.decisions:
            a, c = d.get("action") or {}, d.get("claims") or {}
            if vendor_id and a.get("vendor_id") not in (None, vendor_id):
                continue
            out.append({"request_id": d["request_id"], "vendor_id": a.get("vendor_id"),
                        "invoice_key": a.get("invoice_key"), "invoice_number": c.get("invoice_number"),
                        "amount_inr": c.get("amount_inr"), "invoice_date": c.get("invoice_date"),
                        "account_hash": a.get("account_hash"), "verdict": d["verdict"],
                        "paid": d["verdict"] == "ALLOW"})
        return out


_memory_store = _MemoryStore()


def _store_call(name: str, *args, trace: list, default=None):
    try:
        from gate import store
        return getattr(store, name)(*args)
    except NotImplementedError:
        trace.append(f"store.{name}: not ready, using in-memory store")
        return getattr(_memory_store, name)(*args) if hasattr(_memory_store, name) else default
    except Exception as e:  # never lose a decision because the store failed; say so
        trace.append(f"store.{name} failed: {type(e).__name__}: {e}; using in-memory store")
        return getattr(_memory_store, name)(*args) if hasattr(_memory_store, name) else default


def _ledger(event: str, payload: dict, trace: list) -> None:
    try:
        from gate import ledger
        ledger.append(event, payload)
    except NotImplementedError:
        trace.append(f"ledger: not ready ({event} not recorded)")
    except Exception as e:
        trace.append(f"ledger.append failed: {type(e).__name__}: {e}")


# ------------------------------------------------------------------------------------------ run

@dataclass
class RunResult:
    decision: Decision
    trace: list[str] = field(default_factory=list)
    payout: Optional[dict] = None
    budget: dict = field(default_factory=dict)


def run(request: Request, budget: RunBudget, vendor: Optional[Vendor] = None,
        mock_claims: Optional[dict] = None, mock_checks: Optional[list[dict]] = None,
        execute: bool = True, today: Optional[date] = None) -> RunResult:
    trace: list[str] = []
    mock = os.environ.get("MOCK") == "1"
    stored_claims = mock or os.environ.get("MOCK_CLAIMS") == "1"   # live checks, stored extraction
    stored_checks = mock or os.environ.get("MOCK_CHECKS") == "1"   # live extraction, stored checks

    # 1. the trusted base record comes first; the email may only fill open slots
    if vendor is None:
        vendor = load_vendors().get(request.vendor_id or "")
    if vendor is None:
        vendor = Vendor(vendor_id=request.vendor_id or "UNKNOWN", legal_name="(unknown vendor)")
        trace.append("vendor: not on the vendor master")
    trace.append(f"vendor: {vendor.vendor_id} {vendor.legal_name}")
    _store_call("save_request", request, trace=trace)

    # 2. extract claims (the model never decides)
    try:
        claims = extractor.extract(request, budget, mock_claims=mock_claims if stored_claims else None)
        if not stored_claims and claims.extraction_notes.startswith("extraction failed") and mock_claims is not None:
            trace.append(f"extract: {claims.extraction_notes}; falling back to stored claims")
            claims = extractor.extract(request, budget, mock_claims=mock_claims)
    except BudgetExceeded as e:
        trace.append(f"extract: budget exceeded ({e})")
        claims = Claims(extraction_notes=f"budget exceeded: {e}")
    if claims.removed_hidden_content:
        trace.append(f"sanitize: removed {len(claims.removed_hidden_content)} hidden item(s)")

    # 3. verify every claim against records
    history = _store_call("history_for", None, trace=trace, default=[]) or []
    checks: list[Check]
    if stored_checks and mock_checks is not None:
        checks = [check_from_dict(c) for c in mock_checks]
        trace.append(f"verify: {len(checks)} stored checks")
    else:
        try:
            from gate import verifiers
            checks = verifiers.run_all(request, claims, vendor, history, budget)
            trace.append(f"verify: {len(checks)} live checks")
        except NotImplementedError:
            checks = [check_from_dict(c) for c in (mock_checks or [])]
            trace.append(f"verify: verifiers not ready, using {len(checks)} stored checks")
        except Exception as e:  # run_all must never raise; if it does, fail closed
            checks = [Check("verifiers", CheckStatus.UNVERIFIABLE, note=f"verifiers crashed: {type(e).__name__}: {e}")]
            trace.append(f"verify: crashed ({type(e).__name__}); everything unverifiable")

    # 4. decide in code
    decision = policy.decide(request, claims, vendor, checks, today=today)
    trace.append(f"decide: {decision.verdict.value} {decision.rule_ids}")
    _store_call("save_decision", decision, trace=trace)  # the store also writes the ledger event

    # 5. act only on ALLOW (ESCALATE waits for a person in the approval queue)
    payout = None
    if execute and decision.verdict == Verdict.ALLOW and decision.action:
        try:
            from gate import executor
            receipt = executor.issue_receipt(decision, "policy")
            payout = executor.execute(decision, receipt)
            trace.append(f"execute: {payout.get('status')} payout {payout.get('payout_id')}"
                         + (" (replayed, not paid twice)" if payout.get("replayed") else ""))
        except NotImplementedError:
            trace.append("execute: executor not ready; payment not sent")
        except Exception as e:
            trace.append(f"execute: refused or failed: {type(e).__name__}: {e}")
    return RunResult(decision, trace, payout, budget.summary())


def run_case(path: Path, budget: Optional[RunBudget] = None, **kw) -> tuple[dict, RunResult]:
    case = load_case(path)
    request = request_from_dict(case["request"])
    if case.get("vendor") and "vendor" not in kw:  # a case may carry the vendor master as it stands at that point
        kw["vendor"] = vendor_from_dict(case["vendor"])
        try:
            from gate import store
            store.upsert_vendor(kw["vendor"])
        except Exception:
            pass
    res = run(request, budget or RunBudget(max_credits=10), mock_claims=case.get("mock_claims"),
              mock_checks=case.get("mock_checks"), **kw)
    return case, res
