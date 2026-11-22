# Payables Sign-Off Gate: rules for every Claude session in this repo

Hackathon build (ContextCon 05, 22 Nov 2026). **Code freeze 18:00 IST.** Four people build in parallel. Read `docs/IMPLEMENTATION_PLAN.md` first; the research behind it is `docs/research/00_SYNTHESIS.md`.

## Ownership: edit only your own paths

| Owner | Paths |
|---|---|
| Krishna (core) | `gate/contracts.py`, `gate/extractor.py`, `gate/sanitize.py`, `gate/policy.py`, `gate/pipeline.py`, `gate/baseline_guard.py`, `gate/crosscheck.py`, `gate/llm_gemini.py`, `fixtures/`, `tests/core/`, `scripts/run_demo.py`, `README.md`, `docs/` |
| Lavya (checks) | `gate/verifiers/**`, `tests/verifiers/`, `scripts/warm_cache.py` |
| Ayush (pay + UI) | `gate/store.py`, `gate/ledger.py`, `gate/executor.py`, `gate/payments/**`, `app/**`, `tests/pay/` |
| Sibayan (eval + MCP) | `eval/**`, `mcp_server/**`, `tests/eval/` |

Rules for shared files:
- **`gate/contracts.py` is frozen.** Only Krishna changes it, and only after telling the team. If you need a field, ask; don't edit it.
- **`gate/runbudget.py` is shared.** Use it; don't change its interface.
- **`gate/keys.py` is shared (Krishna owns it).** Always use `invoice_key()`, `norm_invoice_number()`, `financial_year()`, `account_hash()` and `idempotency_key(payment_fingerprint(...))` from it. Don't use the prototype versions; the prototype `norm_inv` has a prefix bug.
- **`requirements.txt`:** add a line only if you must, and say so in your commit message.
- **Bugs in someone else's file:** don't fix them. Add the failing test and the exact error to `docs/ISSUES.md` and tell the owner.

## Git
- Run `git pull --rebase` before every push. Never force-push. Commit small and often (at least every 30 minutes).
- Prefix commit messages with `[core]`, `[checks]`, `[pay]` or `[eval]`.
- Run `python -m pytest -q` before every push. Tests must pass offline (`MOCK=1`).
- Never commit `.env`, keys, `cache/`, `runs/`, `fixtures/private/` or raw Crustdata person responses.

## Design rules (judges score these)
- **The LLM only extracts claims; plain code decides.** The decider sees typed fields, never raw email text.
- **Fail closed.** A timeout, error, "not found", stale record (> 30 days) or conflict means `UNVERIFIABLE`, never a pass. `verifiers.run_all` never raises.
- **Every Check carries Sources:** endpoint or URL, request id, record id, retrieved_at, record date. A person must be able to open the source.
- **Urgency, politeness and authority never relax a rule.**
- **A person approves anything that can't be undone:** bank changes, first payments to new accounts, anything ESCALATE.
- **Exactly once.** A payment's idempotency key comes from the invoice fingerprint, not from the attempt. A restart never pays twice.
- **Every external call goes through `RunBudget`**, which enforces the credit and time ceiling and logs each call.
- **Data minimisation.** Store account numbers as the last 4 digits plus a keyed hash only. Keep only the personal fields a check needs. Agents never email or message real people.

## Environment
- Python 3.14. Install with `pip install -r requirements.txt`. Copy `.env.example` to `.env` and use your own `CRUSTDATA_API_KEY`.
- Crustdata: base `https://api.crustdata.com`, headers `Authorization: Bearer <key>` and `x-api-version: 2025-11-01`. The rate limit is **5 requests per minute** on search, enrich and identify, so cache everything.
- Model provider: `GATE_PROVIDER=gemini` (free tier; your **own** `GEMINI_API_KEY` from aistudio.google.com/apikey, so each person has their own daily quota) or `anthropic` (`GATE_MODEL`, default `claude-opus-5-5`). Gemini's free tier may use prompts for training, so send it **synthetic** cases only, never `fixtures/private/`.
- Reusable, tested code: `prototypes/engineering_snippets.py` (invoice normalisation, fingerprint, idempotency key, lookalike domains, RDAP domain age, hash-chained ledger) and `prototypes/crustdata_cached.py` (the cache pattern).
