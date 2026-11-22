"""Payment worker for the UI. OWNER: Ayush.

The UI never pays directly: after a person approves, it calls pay_approved(), which issues a receipt
bound to the decision's action hash and hands it to the executor (the single enforcement point).
"""
from __future__ import annotations

from gate import executor, store


def pay_approved(request_id: str, approver: str) -> dict:
    row = store.get_decision_row(request_id)
    if not row or row["state"] != store.APPROVED:
        return {"status": "refused", "error": f"state is {row['state'] if row else 'missing'}, not APPROVED"}
    decision = store.get_decision(request_id)
    if decision.action is None:
        return {"status": "no_payment", "error": "approved, but this request has no payment action"}
    try:
        return executor.execute(decision, executor.issue_receipt(decision, approver))
    except executor.ExecutionRefused as e:
        return {"status": "refused", "error": str(e)}
