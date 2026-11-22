"""Approver rules: allow-list, maker-checker, call-back note on bank changes, two-person rule for large payments."""
import pytest

from app import dev_seed, worker
from gate import ledger, store
from gate.payments import razorpayx
from tests.pay.conftest import make_decision, make_vendor


def _escalated(amount_paise=1250000, kind="invoice", sender="billing@acme-test.example"):
    from gate.contracts import Verdict
    store.upsert_vendor(make_vendor())
    d = make_decision(Verdict.ESCALATE, amount_paise=amount_paise)
    store.save_decision(d)
    with store.tx() as c:
        c.execute("INSERT OR REPLACE INTO requests(request_id, kind, sender) VALUES(?,?,?)", (d.request_id, kind, sender))
    return d.request_id


def test_unknown_approver_refused_and_nothing_recorded(db):
    rid = _escalated()
    with pytest.raises(store.ApprovalRefused, match="not an approver"):
        store.record_approval(rid, "mallory", True, "ok")
    assert store.get_decision_row(rid)["state"] == store.ESCALATED
    assert store.approvals_for(rid) == []


def test_requester_cannot_approve_own_request(db):
    rid = _escalated(sender="alice@acme-test.example")
    with pytest.raises(store.ApprovalRefused, match="maker-checker"):
        store.record_approval(rid, "alice", True, "ok")
    assert store.record_approval(rid, "bob", True, "ok") is True


def test_bank_change_needs_callback_note(db):
    dev_seed.seed()
    with pytest.raises(store.ApprovalRefused, match="call-back"):
        store.record_approval("DEMO-5-bankchange", "finance.controller", True, "  ")
    assert store.record_approval("DEMO-5-bankchange", "finance.controller", True, "Called back on file") is True
    # a reject needs no note
    assert store.record_approval("DEMO-6-unknown-requester", "ap.lead", False) is True


def test_two_person_rule_for_large_payments(db, monkeypatch):
    monkeypatch.setenv("TWO_PERSON_MIN_INR", "100000")
    rid = _escalated(amount_paise=50_000_000)                     # ₹5,00,000 >= ₹1,00,000
    with pytest.raises(store.SecondApproverNeeded):
        store.record_approval(rid, "alice", True, "first")
    assert store.get_decision_row(rid)["state"] == store.ESCALATED  # not payable yet
    assert worker.pay_approved(rid, "alice")["status"] == "refused"
    with pytest.raises(store.ApprovalRefused, match="different approver"):
        store.record_approval(rid, "alice", True, "again")
    assert store.record_approval(rid, "bob", True, "second") is True
    assert store.get_decision_row(rid)["state"] == store.APPROVED
    assert [a["approver"] for a in store.approvals_for(rid)] == ["alice", "bob"]
    assert ledger.verify()["ok"]


def test_small_payment_needs_one_approver(db, monkeypatch):
    monkeypatch.setenv("TWO_PERSON_MIN_INR", "100000")
    rid = _escalated(amount_paise=1_250_000)                      # ₹12,500
    assert store.record_approval(rid, "alice", True, "ok") is True
    assert store.get_decision_row(rid)["state"] == store.APPROVED
    assert razorpayx.mock_payouts() == []                         # approving alone never pays
