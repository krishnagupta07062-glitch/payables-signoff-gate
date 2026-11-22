"""MCP server for the Payables Sign-Off Gate. OWNER: Sibayan (eval + MCP).

Exposes the gate to any MCP client (Claude Code, Claude Desktop) as two tools:
  - gate_evaluate(request, vendor_id): run the gate on one request and return the decision with every
    check and its sources. execute=False: it never pays, never approves and never changes bank details.
  - ledger_verify(): replay the hash-chained audit ledger.

Run (stdio):   python mcp_server/server.py
Add to Claude Code:   claude mcp add payables-gate -- python mcp_server/server.py
Uses the official MCP Python SDK 2.x (`MCPServer`, formerly FastMCP).
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_dotenv() -> None:
    try:
        for line in (ROOT / ".env").read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                if v.strip():
                    os.environ.setdefault(k.strip(), v.strip())
    except OSError:
        pass


def gate_evaluate(request: dict, vendor_id: str, max_credits: float = 5.0) -> dict:
    """Run the Sign-Off Gate on one vendor email or invoice and return ALLOW, BLOCK or ESCALATE, with the
    rules fired, their reasons, and every check with its status and sources. Never executes a payment.

    request: {"raw_text": str, "kind": "invoice"|"bank_change"|"email", "sender_email": str,
              "sender_display"?: str, "reply_to"?: str, "request_id"?: str, "po"?: {...},
              "mock_claims"?: {...}, "mock_checks"?: [...]}   (mock_* only for offline runs, MOCK=1)
    vendor_id: the vendor on the trusted vendor master (e.g. "V-ACME").
    """
    from gate import pipeline, store
    from gate.contracts import to_dict
    from gate.runbudget import RunBudget

    if not isinstance(request, dict) or not request.get("raw_text"):
        return {"error": "request must be an object with raw_text"}
    req_d = {k: v for k, v in request.items() if k not in ("mock_claims", "mock_checks")}
    req_d.setdefault("kind", "email")
    req_d.setdefault("request_id", "MCP-" + uuid.uuid4().hex[:10])
    req_d["vendor_id"] = vendor_id
    try:
        req = pipeline.request_from_dict(req_d)
    except (TypeError, ValueError) as e:
        return {"error": f"invalid request: {e}"}
    vendor = store.get_vendor(vendor_id) or pipeline.load_vendors().get(vendor_id)
    if vendor is None:
        return {"error": f"vendor {vendor_id!r} is not on the vendor master"}
    budget = RunBudget(max_credits=max_credits)
    res = pipeline.run(req, budget, vendor=vendor, mock_claims=request.get("mock_claims"),
                       mock_checks=request.get("mock_checks"), execute=False)
    d = res.decision
    return {
        "request_id": d.request_id,
        "verdict": d.verdict.value,
        "rule_ids": d.rule_ids,
        "reasons": to_dict(d.reasons),
        "checks": [{"name": c.name, "status": c.status.value, "value": c.value, "note": c.note,
                    "sources": to_dict(c.sources)} for c in d.checks],
        "policy_version": d.policy_version,
        "executed": False,
        "note": "Evaluation only: nothing was paid. ESCALATE decisions wait for a person in the approval UI.",
        "budget": res.budget,
    }


def ledger_verify() -> dict:
    """Replay the hash-chained audit ledger. Returns {ok, rows, first_bad_row, reason}."""
    from gate import ledger
    return ledger.verify()


def build_server():
    from mcp.server.mcpserver import MCPServer
    server = MCPServer(name="payables-gate", version="1.0",
                       instructions="Payables Sign-Off Gate. gate_evaluate returns ALLOW/BLOCK/ESCALATE with "
                                    "sourced checks and never pays. ledger_verify replays the audit chain.")
    server.tool(name="gate_evaluate")(gate_evaluate)
    server.tool(name="ledger_verify")(ledger_verify)
    return server


def main() -> None:
    _load_dotenv()
    os.environ.setdefault("PAYMENTS_MODE", "mock")
    build_server().run("stdio")


if __name__ == "__main__":
    main()
