import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from gate import executor, ledger, store
from gate.contracts import Verdict
from gate.executor import ExecutionRefused
from gate.payments import razorpayx

from tests.pay.conftest import make_decision, make_vendor


@pytest.fixture
def vendor(db):
    store.upsert_vendor(make_vendor())


def test_allow_pays_once(vendor):
    d = make_decision()
    store.save_decision(d)
    r1 = executor.execute(d, executor.issue_receipt(d))
    assert r1["status"] == "sent" and r1["replayed"] is False
    r2 = executor.execute(d, executor.issue_receipt(d))
    assert r2["replayed"] is True and r2["payout_id"] == r1["payout_id"]
    assert len(razorpayx.mock_payouts()) == 1
    assert len(store.list_payouts()) == 1
    assert store.get_decision_row(d.request_id)["state"] == store.PAID
    assert store.history_for("V-ACME")[0]["paid"] is True
    assert ledger.verify()["ok"]


def test_same_invoice_new_request_is_replayed_not_repaid(vendor):
    d1 = make_decision(request_id="A")
    d2 = make_decision(request_id="B")      # same invoice fingerprint -> same key
    store.save_decision(d1); store.save_decision(d2)
    r1 = executor.pay(d1)
    r2 = executor.pay(d2)
    assert r2["replayed"] and r1["payout_id"] == r2["payout_id"]
    assert len(razorpayx.mock_payouts()) == 1


def test_key_reused_for_different_action_refused(vendor):
    d1 = make_decision(request_id="A")
    executor.pay(d1)
    d2 = make_decision(request_id="B", amount_paise=999)
    d2.action = dataclasses.replace(d2.action, idempotency_key=d1.action.idempotency_key)
    from gate.contracts import action_hash
    d2.action_hash = action_hash(d2.action)
    with pytest.raises(ExecutionRefused):
        executor.pay(d2)
    assert len(razorpayx.mock_payouts()) == 1


def test_receipt_reuse_refused(vendor):
    d = make_decision()
    rc = executor.issue_receipt(d)
    executor.execute(d, rc)
    with pytest.raises(ExecutionRefused, match="nonce"):
        executor.execute(d, rc)


def test_wrong_action_hash_refused(vendor):
    d = make_decision()
    rc = executor.issue_receipt(d)
    d.action = dataclasses.replace(d.action, amount_paise=d.action.amount_paise + 1)   # tampered after approval
    d.action_hash = None
    with pytest.raises(ExecutionRefused, match="hash"):
        executor.execute(d, rc)
    assert razorpayx.mock_payouts() == []


def test_forged_and_expired_receipts_refused(vendor):
    d = make_decision()
    rc = executor.issue_receipt(d)
    forged = dict(rc, approver="mallory")
    with pytest.raises(ExecutionRefused, match="signature"):
        executor.execute(d, forged)
    past = dict(rc, expires_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="seconds"))
    past["signature"] = executor._sign(past)
    with pytest.raises(ExecutionRefused, match="expired"):
        executor.execute(d, past)
    assert razorpayx.mock_payouts() == []


def test_block_and_unapproved_escalate_refused(vendor):
    b = make_decision(Verdict.BLOCK)
    store.save_decision(b)
    with pytest.raises(ExecutionRefused):
        executor.issue_receipt(b)
    e = make_decision(Verdict.ESCALATE, request_id="E1")
    store.save_decision(e)
    with pytest.raises(ExecutionRefused):
        executor.issue_receipt(e, "alice")
    assert store.record_approval("E1", "alice", True)
    r = executor.pay(e, "alice")
    assert r["status"] == "sent"


def test_rejected_escalate_never_paid(vendor):
    e = make_decision(Verdict.ESCALATE, request_id="E2")
    store.save_decision(e)
    store.record_approval("E2", "alice", False)
    with pytest.raises(ExecutionRefused):
        executor.issue_receipt(e, "alice")


def test_provider_error_leaves_unknown_then_resume(vendor, monkeypatch):
    d = make_decision()
    real = razorpayx._mock_create
    monkeypatch.setattr(razorpayx, "_mock_create", lambda *a: (_ for _ in ()).throw(razorpayx.PayoutError("timeout")))
    r = executor.pay(d)
    assert r["status"] == "unknown"
    monkeypatch.setattr(razorpayx, "_mock_create", real)
    out = executor.resume()
    assert out[0]["status"] == "sent"
    assert len(razorpayx.mock_payouts()) == 1
    assert executor.resume() == []


def test_mock_same_key_different_body_rejected(db):
    razorpayx.create_payout({"amount": 1, "reference_id": "x"}, "key-1234")
    with pytest.raises(razorpayx.PayoutRejected):
        razorpayx.create_payout({"amount": 2, "reference_id": "x"}, "key-1234")


def test_refresh_payouts(vendor):
    d = make_decision()
    executor.pay(d)
    changed = executor.refresh_payouts()
    assert changed and changed[0]["to"] == "processed"
