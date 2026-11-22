"""Exactly once through a crash: the payer process dies (os._exit) mid-payout; resume() finishes it."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from gate import executor, ledger, store
from gate.payments import razorpayx

from tests.pay.conftest import make_decision, make_vendor

ROOT = Path(__file__).resolve().parents[2]
CHILD = """
import sys
from gate import executor, store
store.init_db(sys.argv[1])
d = store.get_decision(sys.argv[2])
executor.pay(d)
print("NOT REACHED")
"""


@pytest.mark.parametrize("crash_at", ["after_unknown", "after_payout"])
def test_crash_then_resume_pays_exactly_once(db, crash_at):
    store.upsert_vendor(make_vendor())
    d = make_decision(request_id="CRASH-1")
    store.save_decision(d)
    env = dict(os.environ, GATE_DB=db, GATE_CRASH_AT=crash_at, PAYMENTS_MODE="mock", PYTHONPATH=str(ROOT))
    p = subprocess.run([sys.executable, "-c", CHILD, db, "CRASH-1"], env=env, cwd=ROOT,
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 17, p.stderr
    assert "NOT REACHED" not in p.stdout
    outbox = store.list_outbox()
    assert len(outbox) == 1 and outbox[0]["state"] == "unknown"
    assert len(razorpayx.mock_payouts()) == (0 if crash_at == "after_unknown" else 1)

    results = executor.resume()
    assert [r["status"] for r in results] == ["sent"]
    assert len(razorpayx.mock_payouts()) == 1          # exactly one payout at the provider
    assert len(store.list_payouts()) == 1
    assert store.list_outbox()[0]["state"] == "sent"
    # a second resume and a fresh execute are both no-ops
    assert executor.resume() == []
    again = executor.pay(store.get_decision("CRASH-1"))
    assert again["replayed"] is True
    assert len(razorpayx.mock_payouts()) == 1
    assert ledger.verify()["ok"]
