# Build status

*Krishna's Claude session updates this file as teammates push. Last update: 15:45 IST.*

## Checkpoints

| Checkpoint | Target | State |
|---|---|---|
| Skeleton, contracts and prompts pushed | 14:00 | ✅ 13:43 |
| Each module works on its own, offline tests pass | 15:15 | core ✅ · checks ✅ · pay ✅ |
| One request end to end (case 1 → payout) | 15:30 | ✅ with Ayush's real store, ledger and executor (mock payouts); checks still mocked |
| All 10 cases pass with `scripts/run_demo.py` | 16:30 | ✅ 17/17 offline; ✅ 14/14 with live Gemini extraction (`--live-llm`); baseline guard 6/14. Live Crustdata checks on private Bata cases: ✅ 3/3 (0.69 credits) |
| Feature freeze | 17:15 | |
| Repo public and submitted | 17:45 | |

## Core (Krishna)

| Module | State | Notes |
|---|---|---|
| `gate/contracts.py` | ✅ frozen | |
| `gate/keys.py` | ✅ shared | `invoice_key`, `norm_invoice_number`, `financial_year`, `account_hash`, `idempotency_key(payment_fingerprint())`. **Lavya and Ayush: use these.** |
| `gate/sanitize.py` | ✅ | hidden HTML, comments, zero-width and Unicode tag characters |
| `gate/extractor.py` | ✅ | Claude `claude-opus-5-5` (effort low), structured JSON output, field validation; `MOCK=1` uses stored claims |
| `gate/policy.py` | ✅ | B1–B6, E1–E9, A1; 42 rule tests, including tone invariance |
| `gate/pipeline.py` | ✅ | vendor first → extract → verify → decide → store → ledger → execute; falls back to mocks while teammates' modules are stubs |
| `fixtures/` | ✅ | 2 synthetic vendors and 13 requests (10 cases plus pushy and Hinglish variants), built by `fixtures/build_fixtures.py` |
| `scripts/run_demo.py` | ✅ | `--live`, `--case N`, `--trace`; 13/13 offline |
| `gate/baseline_guard.py` + `--contrast` | ✅ | needs `ANTHROPIC_API_KEY` to run; prints n/a without it |
| README for judges | ✅ draft | final pass at 16:45 with real results |
| Private live-demo cases (Bata India, real role holders) | ✅ on Krishna's machine | `fixtures/private/` is gitignored; cases 11–13 |

## Checks (Lavya)

✅ Pushed: Crustdata client (cache, limiter, budget), Crustdata checks, India checks (GSTIN, IFSC, RDAP, lookalike), history checks, `run_all`; 129 tests pass together. Decided her two questions in ISSUES.md (lookalike strong=BLOCK / weak=E10; live demo uses the private Bata cases).

- ✅ Polish pushed (`6b15a99`): related-company domains flagged (parent domain, rebrand sharing a domain), Crustdata 429 and timeout mid-`run_all` give UNVERIFIABLE, tests for each. Cache warmed twice: 0.89 credits cold, 0.00 warm. Next for Lavya: two clean full runs at the 17:15 freeze.

## Payments and UI (Ayush)

✅ Pushed 14:30: SQLite store (WAL), hash-chained ledger with UPDATE/DELETE triggers, mock + RazorpayX test-mode payouts, exactly-once executor (signed single-use receipts, outbox, resume), crash tests, Streamlit inbox/ledger/payouts. 78 tests pass with core.
- Pipeline now uses the real store; the duplicate ledger writes Ayush flagged are removed (the store writes them).
- `run_demo.py` uses a fresh `runs/demo-HHMMSS.sqlite` per run unless `GATE_DB` is set, so a re-run never sees its own earlier payments as duplicates.
- ✅ UI wired to the pipeline (Run-a-request, simulate crash, Resume). ✅ RazorpayX **test mode verified live**: real test payout, replay gives the same payout, provider rejects a changed body, crash + reconcile adopts the payout.
- Case 5b added for him (approve → payout). ✅ Stage 3 pushed: Demo tab, decision report export, `docs/DEMO_SCRIPT.md`. Next: video ~17:15.

## Evaluation and MCP server (Sibayan, joined ~14:50)

**Built by Ayush** (pushed from his account), because Sibayan wasn't set up yet:
- ✅ `eval/variants.py`: 116 pressure variants of the 14 synthetic cases, with the expected verdicts unchanged.
- ✅ `eval/run_eval.py`: gate vs plain guard; reports accuracy, flip rate, unsafe ALLOWs and extraction errors; cached.
- ✅ `mcp_server/server.py`: `gate_evaluate`, which never pays, and `ledger_verify`. It needs `mcp>=2.3`, so run `pip install -r requirements.txt` again.
- ⏳ The full live eval (130 cases, gate + guard) is running on Ayush's machine; results will go in `eval/results/`.
- **Sibayan's new task:** a fresh-eyes check (see `docs/TEAM_PROMPTS.md`, Sibayan 3).

## How the fixtures plug in (for Lavya and Ayush)

- `fixtures/vendors.json` holds the trusted vendor records. `pipeline.load_vendors()` turns them into `contracts.Vendor`.
- `fixtures/requests/NN_variant.json` holds `request`, `mock_claims`, `mock_checks`, `expected_verdict` and `expected_rules`.
  - **Lavya:** for each case, your live checks should return the statuses in `mock_checks`. That file is the spec.
- `gate.pipeline.run_case(path, budget)` returns `(case, RunResult)`. `RunResult.decision` is a `Decision`, and `RunResult.trace` is a list of human-readable steps.
  - **Ayush:** call this from the UI.

## Open items

- Krishna's Anthropic key has no credit, so the free **Gemini** provider was added: set `GATE_PROVIDER=gemini` and `GEMINI_API_KEY` (from aistudio.google.com/apikey) in `.env`. Without a working key, live extraction falls back to stored claims and the trace says so.
