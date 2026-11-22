"""Headless smoke test of the Streamlit approval UI (skipped if streamlit is not installed)."""
from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")

from app import dev_seed  # noqa: E402
from gate import store  # noqa: E402
from gate.payments import razorpayx  # noqa: E402

APP = str(Path(__file__).resolve().parents[2] / "app" / "approvals.py")


def test_ui_renders_and_approves(db):
    dev_seed.seed()
    at = st_testing.AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert len(at.tabs) == 5
    # select the escalated bank change and approve it
    next(b for b in at.button if b.label == "ESCALATE · DEMO-5-bankchange").click().run()
    assert not at.exception
    next(b for b in at.button if b.label.endswith("Approve")).click().run()
    assert not at.exception
    assert store.get_decision_row("DEMO-5-bankchange")["state"] == store.PAID
    assert len(razorpayx.mock_payouts()) == 2          # seed paid DEMO-1; approval paid DEMO-5
    # verify chain button
    next(b for b in at.button if b.label == "Verify chain").click().run()
    assert any("Chain intact" in s.value for s in at.success)


def test_ui_run_case_crash_then_resume(db, monkeypatch):
    monkeypatch.setenv("MOCK", "1")
    at = st_testing.AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    sb = at.selectbox[0]
    sb.select(next(o for o in sb.options if o.startswith("01_calm"))).run()
    at.toggle[0].set_value(True).run()
    next(b for b in at.button if b.label.endswith("Run the gate")).click().run()
    assert not at.exception
    assert any("crashed" in e.value for e in at.error)
    assert razorpayx.mock_payouts() == []                      # crashed before the provider call
    assert store.list_outbox()[0]["state"] == "unknown"
    next(b for b in at.button if b.label.endswith("Resume")).click().run()
    assert not at.exception
    assert len(razorpayx.mock_payouts()) == 1
    assert any("payouts for this invoice: 1" in s.value for s in at.success)
    # run the same invoice again without a crash: replayed, still one payout
    at.toggle[0].set_value(False).run()
    next(b for b in at.button if b.label.endswith("Run the gate")).click().run()
    assert len(razorpayx.mock_payouts()) == 1


def test_agent_view_lists_everything_copyable(db):
    dev_seed.seed()
    at = st_testing.AppTest.from_file(APP, default_timeout=30)
    at.session_state["view"] = "Agents"
    at.run()
    assert not at.exception
    assert len(at.tabs) == 0                                   # the human tabs are not rendered
    code = "\n".join(c.value for c in at.code)
    for rid in ("DEMO-1-clean", "DEMO-3-lookalike", "DEMO-5-bankchange", "DEMO-6-unknown-requester"):
        assert rid in code                                     # every decision is present as copyable text
    assert '"ledger_ok": true' in code
    assert any(b.label.startswith("Download full state") for b in at.get("download_button"))
    # the agent view never changes state
    assert store.get_decision_row("DEMO-5-bankchange")["state"] == store.ESCALATED


def test_agent_view_query_param_and_switch_back(db):
    dev_seed.seed()
    at = st_testing.AppTest.from_file(APP, default_timeout=30)
    at.query_params["view"] = "agents"
    at.run()
    assert not at.exception and len(at.tabs) == 0
    at.session_state["view"] = "Humans"
    at.run()
    assert not at.exception and len(at.tabs) == 5


def test_agent_view_empty_db(db):
    at = st_testing.AppTest.from_file(APP, default_timeout=30)
    at.session_state["view"] = "Agents"
    at.run()
    assert not at.exception
    assert any("No decisions yet" in c.value for c in at.caption)


def test_nudges_on_waiting_approve_and_double_click(db):
    dev_seed.seed()
    at = st_testing.AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("waiting for a person" in t.value for t in at.toast)        # nudge: people are waiting
    next(b for b in at.button if b.label == "ESCALATE · DEMO-5-bankchange").click().run()
    next(b for b in at.button if b.label.endswith("Approve")).click().run()
    assert not at.exception
    assert any("Approved DEMO-5-bankchange" in t.value for t in at.toast)
    assert store.get_decision_row("DEMO-5-bankchange")["state"] == store.PAID


def test_nudges_on_run_mismatch_free_and_crash(db, monkeypatch):
    monkeypatch.setenv("MOCK", "1")
    at = st_testing.AppTest.from_file(APP, default_timeout=60).run()
    sb = at.selectbox[0]
    sb.select(next(o for o in sb.options if o.startswith("01_calm"))).run()
    at.toggle[0].set_value(True).run()
    next(b for b in at.button if b.label.endswith("Run the gate")).click().run()
    assert not at.exception
    toasts = [t.value for t in at.toast]
    assert any(t.startswith("Gate says ALLOW") and "expected" not in t for t in toasts)
    assert any("crashed mid-payout" in t for t in toasts)
    next(b for b in at.button if b.label == "Verify chain").click().run()
    assert any(t.value == "Chain intact" for t in at.toast)
