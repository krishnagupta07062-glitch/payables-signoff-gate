# Build status

*Krishna's Claude session updates this file as teammates push. Last update: 15:45 IST.*

## Checkpoints

| Checkpoint | Target | State |
|---|---|---|
| Skeleton, contracts and prompts pushed | 14:00 | ✅ 13:43 |
| Each module works on its own, offline tests pass | 15:15 | core ✅ · checks ✅ · pay ✅ |
| One request end to end (case 1 → payout) | 15:30 | ✅ with Ayush's real store, ledger and executor (mock payouts); checks still mocked |
| All 10 cases pass with `scripts/run_demo.py` | 16:30 | ✅ 17/17 offline; ✅ 14/14 with live Gemini extraction (`--live-llm`); baseline guard 6/14. Live Crustdata checks on private Bata cases: ✅ 3/3 (0.69 credits). Held-out (Asian Paints, pre-registered, run once): 3/4, the miss was a rate-limit timeout that escalated instead of blocking (fail closed) |
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
- ✅ Live eval done (`eval/results/1612.md`): gate 130/130, 0 flips, 0 unsafe ALLOWs; guard 48/130, 15/116 flips, 21 unsafe ALLOWs. The 9 "extraction errors" are all case 5b against its stale stored claims (fixed 15:42), so the real extraction error rate is 0/130. In the README.
- **Sibayan's new task:** a fresh-eyes check (see `docs/TEAM_PROMPTS.md`, Sibayan 3).

## How the fixtures plug in (for Lavya and Ayush)

- `fixtures/vendors.json` holds the trusted vendor records. `pipeline.load_vendors()` turns them into `contracts.Vendor`.
- `fixtures/requests/NN_variant.json` holds `request`, `mock_claims`, `mock_checks`, `expected_verdict` and `expected_rules`.
  - **Lavya:** for each case, your live checks should return the statuses in `mock_checks`. That file is the spec.
- `gate.pipeline.run_case(path, budget)` returns `(case, RunResult)`. `RunResult.decision` is a `Decision`, and `RunResult.trace` is a list of human-readable steps.
  - **Ayush:** call this from the UI.

## Open items

- Krishna's Anthropic key has no credit, so the free **Gemini** provider was added: set `GATE_PROVIDER=gemini` and `GEMINI_API_KEY` (from aistudio.google.com/apikey) in `.env`. Without a working key, live extraction falls back to stored claims and the trace says so.

### Evaluation

*Sibayan's work (eval + MCP), done from Ayush's session. Full results: [`eval/results/1612.md`](../eval/results/1612.md) (and `.json`).*

**130 cases** = the 14 committed cases plus 116 deterministic pressure variants: authority, deadline, flattery, threat, Hinglish urgency, a visible "note to the AI assistant", hidden HTML injection, Unicode-tag smuggling, and a planted "DISPUTED - DO NOT PAY" note. Same model for both sides (`gemini-3.5-flash-lite`); 228 live calls, 0 errors.

| | Correct | Flips under pressure (vs the calm case) | Unsafe ALLOWs (expected BLOCK/ESCALATE) |
|---|---|---|---|
| **Gate** (model extracts, records check, code decides) | **130/130 (100%)** | **0/116 (0%)** | **0** |
| Plain model guard (reads the raw email and decides) | 48/130 (37%) | 15/116 (13%) | 21 |

- The guard flipped most on **Unicode-tag smuggling (5/14)**, **planted "do not pay" notes (3/4)** and **Hinglish urgency (3/14)**. It ALLOWed requests whose expected answer was BLOCK or ESCALATE 21 times, e.g. a duplicate invoice re-sent with a threat (case 02) and a timed-out check under authority or deadline pressure (case 09).
- **Honest caveats:**
  - The gate ran with *stored* checks (`MOCK_CHECKS=1`), so this measures extraction plus policy under pressure, not the live checks.
  - The guard has no payment history and no record checks, so part of its 37% comes from missing information, not tone. The **flip rate (13%) is the pressure-only number.**
  - 9/130 extractions differed from the stored claims, all case 05b: the email says only "account ending 7777", and the model correctly didn't invent a full number. The verdicts were still right.
- Reproduce: `python -m eval.variants && python -m eval.run_eval --sleep 3` (answers cached in `eval/cache/`, so a re-run is free). Offline harness: `python -m eval.run_eval --offline`.
- MCP server: `claude mcp add payables-gate -- python mcp_server/server.py` (tools `gate_evaluate`, which never pays, and `ledger_verify`).
