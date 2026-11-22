# Lavya's work log: verification checks

ContextCon 05, 22 Nov 2026. Lavya owns `gate/verifiers/**`, `tests/verifiers/` and `scripts/warm_cache.py`.
Newest entries at the top.

## Status at a glance

| Piece | File | State |
|---|---|---|
| Crustdata client (cache, 5/min limiter, 429 retry, budget, MOCK) | `crustdata_client.py` | ✅ done, tested offline |
| Shared helpers (HTTP with MOCK, domains, names, dates) | `common.py` | ✅ done |
| GSTIN checksum / matches vendor / exists, IFSC, RDAP domain age, lookalike domain | `india_checks.py` | ✅ done, tested offline |
| Duplicate, near-duplicate, account on master, account shared, PO match, penny drop (simulated) | `history_checks.py` | ✅ done, tested |
| Sender domain matches vendor, vendor active, requester role / departed, current role holder | `crustdata_checks.py` | ✅ done, tested with fake Crustdata responses |
| `run_all()` (parallel, shared 20 s deadline, never raises) | `__init__.py` | ✅ done |
| `scripts/warm_cache.py` | `scripts/warm_cache.py` | ✅ done; run once without a Crustdata key, 0-credit second run tested |
| Live run against real Crustdata / RDAP / IFSC | | ⏳ needs `.env` with Lavya's key |
| `vendor_news` | | ✂️ cut (first item in the team's cut list) |

Tests: `tests/verifiers/` has 39 tests. Full suite: 96 passed, offline.

## Log

### ~15:20: `scripts/warm_cache.py`
- Runs the same checks as `run_all` (`verifiers.plan`), but one at a time with no deadline, so a cold cache fills completely under the 5-per-minute limit.
- Prints check, status, the spec's status, credits, seconds and source for every case, then a summary: credits, live vs cached Crustdata calls, slowest checks, and every check that differs from the spec.
- Uses each case's stored claims by default (no model tokens); `--extract` uses the live extractor instead.
- New test: the second run spends 0 credits and makes no new calls.
- Fixed in the client: Crustdata 4xx answers are now cached and replayed as the same error. Before, they were re-asked every run, wasting rate-limit slots. 5xx, 429 and timeouts are still retried.
- First real run (free sources only, no Crustdata key yet): 13 cases, 152 checks, 10 s. IFSC and the GST portal match the spec.
- **Finding, logged for Krishna:** the synthetic vendor domains (`acmeleather.in`, `kanpurtannery.co.in`) aren't registered (RDAP 404), so domain age is CONTRADICTED. Live, genuine cases would BLOCK (B2). The live demo needs real, registered vendor domains.

### ~15:00: reviewed the decisions; lookalike domains should escalate
- Lavya's call: a lookalike sender domain should ESCALATE to a person, not BLOCK.
- The rule lives in Krishna's `gate/policy.py` (B2), so I logged a change request in `docs/ISSUES.md` under `## checks` instead of editing it. A new or unregistered domain (`domain_age_days`) stays a BLOCK, so cases 3 and 8 still block.
- `sender_domain_lookalike` itself is unchanged: it still reports CONTRADICTED with `closest`, `distance` and `reason`.
- First commit and push of the checks.

### ~14:40: compared the real checks with the spec (each case's `mock_checks`)
- Every check that doesn't need the network now gives the status the spec expects, for all 13 demo requests.
- Changed to match the spec:
  - `penny_drop_name_match`: a simulated penny drop only echoes the name the sender typed, so for a new account it is UNVERIFIABLE (or CONTRADICTED if even that name doesn't match). It is never VERIFIED.
  - `account_on_vendor_master` runs only for payments. A bank change names a new account by definition, and E1 already holds it for a person.
  - `sender_domain_matches_vendor`: fail closed. If Crustdata is down, or has no record listing the domain, the result is UNVERIFIABLE even when the domain is on our vendor master (cases 6 and 9).
- **Found an integration gap, logged in `docs/ISSUES.md`:** the synthetic vendors in `fixtures/vendors.json` have no `crustdata_company_id`, and their domains aren't in Crustdata. So in a live run the Crustdata checks can only say UNVERIFIABLE, and case 1 would ESCALATE instead of ALLOW. The live demo needs real vendors in `fixtures/private/`, or a Crustdata id on a vendor.

### ~14:30: built all checks and `run_all`
- Wrote `crustdata_client.py`, `common.py`, `india_checks.py`, `history_checks.py`, `crustdata_checks.py` and `__init__.py`.
- Design rules followed:
  - fail closed (errors, timeouts, not found, stale > 30 days → UNVERIFIABLE with a note);
  - every Check carries Sources;
  - every external call goes through `RunBudget`;
  - only name, title and dates are kept from person records;
  - shared keys come from `gate/keys.py`.
- Research gotchas handled:
  - identify confidence 1.0 isn't proof unless the domain is in `all_domains`;
  - an "active" index record isn't proof the site is alive (live fetch, expired/parked page → CONTRADICTED);
  - filter `company_id` but read `crustdata_company_id`;
  - departures are read from `past[].end_date`.

### ~14:00: read the repo and planned
- Read `CLAUDE.md`, the implementation plan, the team prompts, `contracts.py`, `runbudget.py`, `keys.py`, `policy.py`, and research reports 04 and 05.
- Cloned the repo to `Desktop/payables-signoff-gate`.

## Next
1. Fill in `.env` (own `CRUSTDATA_API_KEY`, and the team's `ACCOUNT_HASH_KEY`), then run a few live calls to confirm the response shapes (especially the `/company/search` filter on `crustdata_company_id` and the `/web/enrich/live` shape).
2. Write `scripts/warm_cache.py`; run it twice and confirm the second run spends 0 credits.
3. Polish edge cases (15:30 / 16:45 prompts): Zomato/Eternal-style rebrands, Hindi dates (always send location "US").
