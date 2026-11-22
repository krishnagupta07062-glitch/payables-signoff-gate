"""Payment worker for the UI.

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


# ------------------------------------------------------------------------ crash demo (on stage)

_CRASH_CHILD = """
import sys
from gate import executor, store
store.init_db(sys.argv[1])
d = store.get_decision(sys.argv[2])
executor.execute(d, executor.issue_receipt(d, sys.argv[3]))
"""


def pay_with_crash(request_id: str, approver: str = "policy", crash_at: str = "after_unknown") -> dict:
    """Run the payout in a child process that os._exit()s at `crash_at` (Streamlit itself must not
    die). Afterwards the outbox row is left 'unknown'; executor.resume() finishes it exactly once."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    env = dict(os.environ, GATE_CRASH_AT=crash_at, PYTHONPATH=str(root))
    p = subprocess.run([sys.executable, "-c", _CRASH_CHILD, store.db_path(), request_id, approver],
                       env=env, cwd=root, capture_output=True, text=True, timeout=60)
    row = store.get_decision_row(request_id) or {}
    key = (store.get_decision(request_id).action.idempotency_key
           if row and store.get_decision(request_id).action else None)
    outbox = next((o for o in store.list_outbox() if o["idempotency_key"] == key), None)
    return {"crashed": p.returncode == 17, "returncode": p.returncode, "stderr": p.stderr[-500:],
            "outbox_state": outbox["state"] if outbox else None, "idempotency_key": key}
