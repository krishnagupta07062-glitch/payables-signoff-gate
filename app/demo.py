"""The 2-minute demo walkthrough, as plain functions (the Demo tab renders them).

Order (docs/DEMO_SCRIPT.md):
  1. case 03  lookalike-domain bank change naming the real CFO   -> BLOCK, contradicting source shown
  2. case 05  genuine bank change from a verified contact        -> ESCALATE E1 -> a person approves
  3. case 05b first invoice to the newly approved account        -> ESCALATE E2 -> approve -> payout
  4. case 01  clean invoice, payer crashes mid-payout            -> outbox 'unknown' -> Resume -> 1 payout
  5. case 02  the same invoice re-sent as "2026-27-42"           -> BLOCK B1, still exactly 1 payout
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from app import worker
from gate import executor, store

ROOT = Path(__file__).resolve().parent.parent

STEPS = [
    {"id": "fraud", "case": "03_calm", "title": "Bank-change fraud from a lookalike domain",
     "say": "An email signed by the vendor's real CFO asks us to change their bank account. "
            "The gate checks the sender's domain against live records: it's one letter off the real "
            "one and was registered four days ago. Blocked, with the source on screen."},
    {"id": "bank", "case": "05_calm", "title": "A genuine bank change",
     "say": "Same request, now from the real domain and a person who really works there today. "
            "Everything checks out, but a bank change can't be undone, so it goes to a person, "
            "who calls back on the number we already had on file and approves it."},
    {"id": "first", "case": "05b_calm", "title": "First invoice to the new account",
     "say": "The first invoice to that new account escalates again (cooling-off). The person approves; "
            "only now does the executor accept a signed receipt bound to this exact payment, and the payout goes out."},
    {"id": "crash", "case": "01_calm", "title": "Pay an invoice, crash mid-payout",
     "say": "A clean invoice is allowed. We kill the payer right after it records the intent to pay, "
            "the worst moment. Did the money go or not? Resume replays the same request with the same key."},
    {"id": "dup", "case": "02_calm", "title": "The same invoice re-sent",
     "say": "The vendor re-sends the same invoice with the number reformatted. The gate normalises it, "
            "finds the payment in its history and blocks it. One invoice, one payout, through a crash and a re-send."},
]


def case_path(case: str) -> Path:
    return ROOT / "fixtures" / "requests" / f"{case}.json"


def fresh_db() -> str:
    """Point the store at a new, empty demo database and load the vendor master."""
    path = str(ROOT / "runs" / f"demo-ui-{time.strftime('%H%M%S')}.sqlite")
    store.init_db(path)
    load_vendor_master()
    return path


def load_vendor_master() -> None:
    for p in (ROOT / "fixtures" / "vendors.json",):  # the demo uses the committed synthetic vendors
        if p.exists():
            store.load_fixtures(str(p))


def run_step(step_id: str, crash: bool = False, max_credits: float = 10.0) -> dict:
    """Run one demo step through the real pipeline. Returns a summary for the UI."""
    from gate import pipeline
    from gate.runbudget import RunBudget

    step = next(s for s in STEPS if s["id"] == step_id)
    if not store.list_vendors():
        load_vendor_master()
    budget = RunBudget(max_credits=max_credits)
    _, res = pipeline.run_case(case_path(step["case"]), budget, execute=not crash)
    store.record_calls(budget)
    out = {"step": step_id, "request_id": res.decision.request_id, "verdict": res.decision.verdict.value,
           "rule_ids": res.decision.rule_ids, "payout": res.payout, "trace": res.trace, "budget": res.budget}
    if crash and res.decision.verdict.value == "ALLOW" and res.decision.action:
        out["crash"] = worker.pay_with_crash(res.decision.request_id)
    return out


def approve(request_id: str, approver: str, note: str = "") -> dict:
    """A person approves; if the request carries a payment, the worker pays it (receipt -> executor)."""
    try:
        if not store.record_approval(request_id, approver, True, note):
            return {"status": "already_decided"}
    except store.ApprovalRefused as e:
        return {"status": "refused_by_rule", "error": f"Not approved: {e}."}
    except store.SecondApproverNeeded as e:
        return {"status": "needs_second_approver", "error": f"First approval recorded: {e}."}
    return worker.pay_approved(request_id, approver)


def resume() -> list[dict]:
    return executor.resume()


def payouts_for_case(case: str) -> list[dict]:
    """Payouts for the invoice in this case (matched by its idempotency key)."""
    d = store.get_decision(_request_id(case))
    if not d or not d.action:
        return []
    return [p for p in store.list_payouts() if p["idempotency_key"] == d.action.idempotency_key]


def payouts_for_invoice_of(case: str, other_case: str) -> int:
    """How many payouts exist for the invoice that `other_case` is a re-send of (case 02 -> case 01)."""
    return len(payouts_for_case(other_case))


def _request_id(case: str) -> Optional[str]:
    import json
    try:
        return json.loads(case_path(case).read_text(encoding="utf-8"))["request"]["request_id"]
    except (OSError, KeyError, ValueError):
        return None
