# Payables Sign-Off Gate as an MCP server

Lets any MCP client (Claude Code, Claude Desktop, another agent) ask the gate before it acts. The server never pays: `gate_evaluate` runs the pipeline with `execute=False`, so an ALLOW is only advice, and payments still go through the executor and its signed receipts.

| Tool | What it does |
|---|---|
| `gate_evaluate(request, vendor_id)` | Runs sanitize → extract → verify → decide on one email or invoice. Returns `verdict` (ALLOW/BLOCK/ESCALATE), `rule_ids`, `reasons`, and every check with its status, note and sources. Never executes. |
| `ledger_verify()` | Replays the hash-chained audit ledger: `{ok, rows, first_bad_row, reason}`. |

## Add it to Claude Code

From the repo root (with the project's virtualenv):

```bash
claude mcp add payables-gate -- python mcp_server/server.py
# or, explicitly with the venv:
claude mcp add payables-gate -- .venv/bin/python mcp_server/server.py
```

The server reads `.env`: `GATE_PROVIDER`/`GEMINI_API_KEY` for live extraction, `CRUSTDATA_API_KEY` for live checks, and `GATE_DB` for the database. Without keys, start it with `MOCK=1` and pass `mock_claims`/`mock_checks` in the request (as in `fixtures/requests/*.json`).

## Example

Ask Claude: *"Before updating Acme's bank details, run this email through payables-gate."* The model calls:

```json
{"request": {"kind": "bank_change", "sender_email": "vikram.sethi@acmeleathers.in",
             "raw_text": "We have moved our banking to ICICI Bank..."},
 "vendor_id": "V-ACME"}
```

and gets back `{"verdict": "BLOCK", "rule_ids": ["B2", ...], "checks": [...]}`, with the lookalike-domain and domain-age checks and their sources.

Tests: `python -m pytest -q tests/eval/test_mcp.py` (offline).
