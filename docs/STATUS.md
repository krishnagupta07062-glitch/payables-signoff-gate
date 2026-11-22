# Build status

*Krishna's Claude session updates this file as teammates push. Last update: 13:55 IST.*

## Checkpoints

| Checkpoint | Target | State |
|---|---|---|
| Skeleton, contracts and prompts pushed | 14:00 | ✅ 13:43 |
| Each module works on its own, offline tests pass | 15:15 | core ✅ · checks ⏳ · pay ⏳ |
| One request end to end (case 1 → payout) | 15:30 | core path ✅ on mocks; waiting for store/executor |
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
| `gate/baseline_guard.py` + `--contrast` | ⏳ next | |
| README for judges | ⏳ 16:45 | |

## Checks (Lavya)

Waiting for first push. Expected: `gate/verifiers/{crustdata_client,crustdata_checks,india_checks,history_checks}.py`, `run_all`.

## Payments and UI (Ayush)

Waiting for first push. Expected: `gate/store.py`, `gate/ledger.py`, `gate/executor.py`, `gate/payments/razorpayx.py`, `app/approvals.py`, `tests/pay/`.

## How the fixtures plug in (for Lavya and Ayush)

- `fixtures/vendors.json` holds the trusted vendor records. `pipeline.load_vendors()` turns them into `contracts.Vendor`.
- `fixtures/requests/NN_variant.json` holds `request`, `mock_claims`, `mock_checks`, `expected_verdict` and `expected_rules`.
  - **Lavya:** for each case, your live checks should return the statuses in `mock_checks`. That file is the spec.
- `gate.pipeline.run_case(path, budget)` returns `(case, RunResult)`. `RunResult.decision` is a `Decision`, and `RunResult.trace` is a list of human-readable steps.
  - **Ayush:** call this from the UI.

## Open items

- `ANTHROPIC_API_KEY` is not set on Krishna's machine yet, so live extraction falls back to stored claims (the trace says so).
