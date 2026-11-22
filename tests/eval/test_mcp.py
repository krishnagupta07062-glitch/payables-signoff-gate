"""Offline tests for the MCP server (no network, no model calls)."""
import asyncio
import json

import pytest

pytest.importorskip("mcp")

from mcp_server import server  # noqa: E402
from gate import store  # noqa: E402
from gate.payments import razorpayx  # noqa: E402


@pytest.fixture
def offline(tmp_path, monkeypatch):
    monkeypatch.setenv("MOCK", "1")
    monkeypatch.setenv("PAYMENTS_MODE", "mock")
    monkeypatch.delenv("ACCOUNT_HASH_KEY", raising=False)
    monkeypatch.setattr(store, "_db_path", store._db_path)
    store.init_db(str(tmp_path / "mcp.sqlite"))


def _case(name):
    return json.loads(open(f"fixtures/requests/{name}.json", encoding="utf-8").read())


def test_tools_registered():
    tools = asyncio.run(server.build_server().list_tools())
    assert {t.name for t in tools} == {"gate_evaluate", "ledger_verify"}


def test_gate_evaluate_block_with_sources_and_never_pays(offline):
    c = _case("03_calm")
    req = dict(c["request"], mock_claims=c["mock_claims"], mock_checks=c["mock_checks"])
    out = server.gate_evaluate(req, c["request"]["vendor_id"])
    assert out["verdict"] == "BLOCK" and "B2" in out["rule_ids"] and out["executed"] is False
    assert all(ch["sources"] for ch in out["checks"])


def test_gate_evaluate_allow_does_not_execute(offline):
    c = _case("01_calm")
    req = dict(c["request"], mock_claims=c["mock_claims"], mock_checks=c["mock_checks"])
    out = server.gate_evaluate(req, "V-ACME")
    assert out["verdict"] == "ALLOW"
    assert razorpayx.mock_payouts() == [] and store.list_outbox() == []
    assert server.ledger_verify()["ok"] is True


def test_gate_evaluate_bad_input(offline):
    assert "error" in server.gate_evaluate({}, "V-ACME")
    assert "error" in server.gate_evaluate({"raw_text": "hi"}, "V-NOPE")
