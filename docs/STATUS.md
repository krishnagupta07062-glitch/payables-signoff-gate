# Build status

*Krishna's Claude session updates this file as teammates push. Last update: 14:40 IST.*

## Checkpoints

| Checkpoint | Target | State |
|---|---|---|
| Skeleton, contracts and prompts pushed | 14:00 | ✅ 13:43 |
| Each module works on its own, offline tests pass | 15:15 | core ✅ · checks ⏳ · pay ✅ |
| One request end to end (case 1 → payout) | 15:30 | ✅ with Ayush's real store, ledger and executor (mock payouts); checks still mocked |
| All 10 cases pass with `scripts/run_demo.py` | 16:30 | ✅ offline (13/13 incl. variants); live run needs verifiers and an `ANTHROPIC_API_KEY` |
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

Waiting for first push. Expected: `gate/verifiers/{crustdata_client,crustdata_checks,india_checks,history_checks}.py`, `run_all`.

## Payments and UI (Ayush)

✅ Pushed 14:30: SQLite store (WAL), hash-chained ledger with UPDATE/DELETE triggers, mock + RazorpayX test-mode payouts, exactly-once executor (signed single-use receipts, outbox, resume), crash tests, Streamlit inbox/ledger/payouts. 78 tests pass with core.
- Pipeline now uses the real store; the duplicate ledger writes Ayush flagged are removed (the store writes them).
- `run_demo.py` uses a fresh `runs/demo-HHMMSS.sqlite` per run unless `GATE_DB` is set, so a re-run never sees its own earlier payments as duplicates.
- Next for Ayush: wire the UI's "Run a request" panel to `gate.pipeline.run_case`.

## How the fixtures plug in (for Lavya and Ayush)

- `fixtures/vendors.json` holds the trusted vendor records. `pipeline.load_vendors()` turns them into `contracts.Vendor`.
- `fixtures/requests/NN_variant.json` holds `request`, `mock_claims`, `mock_checks`, `expected_verdict` and `expected_rules`.
  - **Lavya:** for each case, your live checks should return the statuses in `mock_checks`. That file is the spec.
- `gate.pipeline.run_case(path, budget)` returns `(case, RunResult)`. `RunResult.decision` is a `Decision`, and `RunResult.trace` is a list of human-readable steps.
  - **Ayush:** call this from the UI.

## Open items

- `ANTHROPIC_API_KEY` is not set on Krishna's machine yet, so live extraction falls back to stored claims (the trace says so).
