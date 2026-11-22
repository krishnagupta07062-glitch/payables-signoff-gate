"""The Stage 3 demo walkthrough end to end (offline, mock payouts), plus the decision report."""
from pathlib import Path

import pytest

from app import demo, report
from gate import ledger, store
from gate.payments import razorpayx

APP = str(Path(__file__).resolve().parents[2] / "app" / "approvals.py")


@pytest.fixture
def mock_env(db, monkeypatch):
    monkeypatch.setenv("MOCK", "1")
    # fixtures/vendors.json hashes were made with the default key; the team key must match them too
    monkeypatch.delenv("ACCOUNT_HASH_KEY", raising=False)
    demo.load_vendor_master()


def test_demo_walkthrough(mock_env):
    r = demo.run_step("fraud")
    assert r["verdict"] == "BLOCK" and "B2" in r["rule_ids"]

    r = demo.run_step("bank")
    assert r["verdict"] == "ESCALATE" and "E1" in r["rule_ids"]
    assert demo.approve(r["request_id"], "controller")["status"] == "no_payment"

    r = demo.run_step("first")
    assert r["verdict"] == "ESCALATE" and "E2" in r["rule_ids"]
    paid = demo.approve(r["request_id"], "controller")
    assert paid["status"] == "sent" and paid["payout_id"]
    assert demo.approve(r["request_id"], "controller")["status"] == "already_decided"

    r = demo.run_step("crash", crash=True)
    assert r["verdict"] == "ALLOW" and r["crash"]["outbox_state"] == "unknown"
    assert demo.payouts_for_case("01_calm") == []
    assert [x["status"] for x in demo.resume()] == ["sent"]
    assert len(demo.payouts_for_case("01_calm")) == 1

    r = demo.run_step("dup")
    assert r["verdict"] == "BLOCK" and "B1" in r["rule_ids"]
    assert len(demo.payouts_for_case("01_calm")) == 1
    assert len(razorpayx.mock_payouts()) == 2          # 05b and 01, each exactly once
    assert ledger.verify()["ok"]


def test_report_has_claims_checks_sources_rules(mock_env):
    r = demo.run_step("first")
    demo.approve(r["request_id"], "controller", "called back")
    md = report.decision_report_md(r["request_id"])
    for needle in ("Decision report", "**Verdict: ESCALATE**", "E2", "## Checks", "## Claims",
                   "Idempotency key", "Approved by **controller**", "## Payouts", "pout_mock_", "Chain: **intact**"):
        assert needle in md, needle
    assert "555566667777" not in md and "5555 6666 7777" not in md      # never the full account
    assert "Please find below" not in md                                 # never the raw email
    assert "No decision found" in report.decision_report_md("nope")


def test_demo_tab_clicks_through(mock_env):
    st_testing = pytest.importorskip("streamlit.testing.v1")
    at = st_testing.AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception

    def click(label_end):
        next(b for b in at.button if b.label.endswith(label_end)).click().run()
        assert not at.exception

    click("Start fresh demo")
    store.init_db(store.db_path())
    for key in ("demo-run-fraud", "demo-run-bank"):
        next(b for b in at.button if b.key == key).click().run()
    next(b for b in at.button if b.key == "demo-approve-bank").click().run()
    next(b for b in at.button if b.key == "demo-run-first").click().run()
    next(b for b in at.button if b.key == "demo-approve-first").click().run()
    next(b for b in at.button if b.key == "demo-run-crash").click().run()
    assert any("Payer killed" in e.value for e in at.error)
    next(b for b in at.button if b.key == "demo-resume").click().run()
    next(b for b in at.button if b.key == "demo-run-dup").click().run()
    assert not at.exception
    assert any("payouts for this invoice: **1**" in s.value for s in at.success)
    assert len(razorpayx.mock_payouts()) == 2
