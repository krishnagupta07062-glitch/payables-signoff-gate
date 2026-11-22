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
    assert len(at.tabs) == 3
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
