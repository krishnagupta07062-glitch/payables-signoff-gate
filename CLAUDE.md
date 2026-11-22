# Payables Sign-Off Gate: rules for every Claude session in this repo

Hackathon build (ContextCon 05, 22 Nov 2026). Read `docs/DESIGN.md` and `docs/ARCHITECTURE.md` first; the research behind it is `docs/research/00_SYNTHESIS.md`.

## Shared code
- **`gate/contracts.py`** holds the types every part codes against. Add optional fields with defaults; don't rename or remove fields.
- **`gate/runbudget.py`:** every external call goes through it; don't change its interface.
- **`gate/keys.py`:** always use `invoice_key()`, `norm_invoice_number()`, `financial_year()`, `account_hash()` and `idempotency_key(payment_fingerprint(...))` from it. Don't use the prototype versions; the prototype `norm_inv` has a prefix bug.

## Git
- Run `git pull --rebase` before every push. Never force-push. Commit small and often (at least every 30 minutes).
- Run `python -m pytest -q` before every push. Tests must pass offline (`MOCK=1`).
- Never commit `.env`, keys, `cache/`, `runs/`, `fixtures/private/` or raw Crustdata person responses.

## Design rules
- **The LLM only extracts claims; plain code decides.** The decider sees typed fields, never raw email text.
- **Fail closed.** A timeout, error, "not found", stale record (> 30 days) or conflict means `UNVERIFIABLE`, never a pass. `verifiers.run_all` never raises.
- **Every Check carries Sources:** endpoint or URL, request id, record id, retrieved_at, record date. A person must be able to open the source.
- **Urgency, politeness and authority never relax a rule.**
- **A person approves anything that can't be undone:** bank changes, first payments to new accounts, anything ESCALATE.
- **Exactly once.** A payment's idempotency key comes from the invoice fingerprint, not from the attempt. A restart never pays twice.
- **Every external call goes through `RunBudget`**, which enforces the credit and time ceiling and logs each call.
- **Data minimisation.** Store account numbers as the last 4 digits plus a keyed hash only. Keep only the personal fields a check needs. Agents never email or message real people.

## Environment
- Python 3.14. Install with `pip install -r requirements.txt`. Copy `.env.example` to `.env` and add a `CRUSTDATA_API_KEY`.
- Crustdata: base `https://api.crustdata.com`, headers `Authorization: Bearer <key>` and `x-api-version: 2025-11-01`. The rate limit is **5 requests per minute** on search, enrich and identify, so cache everything.
- Model provider: `GATE_PROVIDER=gemini` (free tier; `GEMINI_API_KEY` from aistudio.google.com/apikey) or `anthropic` (`GATE_MODEL`, default `claude-opus-5-5`). Gemini's free tier may use prompts for training, so send it **synthetic** cases only, never `fixtures/private/`.
- Reusable, tested code: `prototypes/engineering_snippets.py` (invoice normalisation, fingerprint, idempotency key, lookalike domains, RDAP domain age, hash-chained ledger) and `prototypes/crustdata_cached.py` (the cache pattern).
