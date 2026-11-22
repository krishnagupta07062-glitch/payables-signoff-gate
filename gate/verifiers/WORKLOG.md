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
| Same-name requester matching (case 12) | `crustdata_checks.py` | ✅ done, live-verified |
| Rebrand / parent-company domains flagged, not contradicted | `crustdata_checks.py` | ✅ done, live-verified on `bata.com` |
| Polish prompt (Lavya 3) edge cases | | ✅ all five covered |
| `vendor_news` | | ✂️ cut (first item in the team's cut list) |

Tests: `tests/verifiers/` has 39 tests. Full suite: 96 passed, offline.

## Log

### ~16:10: near-duplicate false alarm on sequential invoices (bug fix, from the SOP gatekeeper results)
- Lesson from our earlier gatekeeper research (`Desktop/SOP/gatekeeper`): measure over-refusal ("valid sent to a person"), not just missed fraud, and test near-misses. "Extract-then-code leaks near-misses."
- Tested `near_duplicate_invoice` on near-misses. In the standard Indian format `INV/2026-27/NNNN`, the vendor's **next** bill scored 90-95 against the last one (`0042` vs `0043`, `0142`, `0024`), so every next invoice would have escalated (E4).
- Fix: a similar number counts only if the **amount matches too** (±0.5%), or an amount is unreadable (stay cautious). Same amount within 10 days still counts whatever the number. A re-sent bill with a tweaked number is still caught.
- 3 new tests. 151 passed; demo 17/17 offline, 3/3 live private.

### ~15:55: finished the Integration prompt (Lavya 2)
- Looked for new instructions for Lavya: none in the repo since the last push.
- The Lavya 2 prompt still had open parts, now done:
  - **Every Check carries a Source.** The vendor-not-linked path now points at the vendor record. `run_all` adds a fallback source naming the request and vendor to anything that consulted no outside record. New test: `test_every_check_has_a_source`.
  - **Krishna's demo:** `run_demo.py --live-checks --only-private` gives 3/3, and `MOCK=1` gives 17/17.
  - **Summary in `docs/ISSUES.md`:** credits (0.89 cold, 0.00 warm), slowest checks, and nothing UNVERIFIABLE that shouldn't be.
- Tests: 148 passed.

### ~15:45: polish prompt (Lavya 3) done
Each of the five edge cases, with its test:
1. **Unknown small vendor** → `requester_current_role` UNVERIFIABLE, "call back on the number on file". Already done; `test_requester_small_vendor_unlinked`, `test_requester_not_found_says_call_back`.
2. **Crustdata 429 and a timeout in the middle of `run_all`.** New `test_run_all_429_and_timeout_mid_run`: identify is rate-limited (1 try + 3 retries, then gives up) and person search times out. The three Crustdata checks fail closed (UNVERIFIABLE, naming the cause), while RDAP, IFSC and lookalike still give real answers. Nothing raises.
3. **Expired domain that Crustdata still calls active** → CONTRADICTED. Already done; `test_vendor_index_active_but_domain_expired`.
4. **Same company under two names (Zomato/Eternal, Bata India/Bata Group).** New `_related()`: if the domain belongs to another Crustdata record but is on our vendor master, or that record lists one of the vendor's domains, the result is UNVERIFIABLE with "possibly the same company under another name (rebrand, parent or subsidiary); confirm by hand". It is not CONTRADICTED. Unrelated companies are still CONTRADICTED. Also fixed: a vendor with no Crustdata id no longer gets VERIFIED just because the domain is on the master while Crustdata names a different company. 3 new tests; live `bata.com` → UNVERIFIABLE "Bata Group ... separate record from Bata India".
5. **Hindi dates in web results:** not applicable. No check uses `/web/search/live` (where dates are localised); `vendor_active` uses `/web/enrich/live`, which returns a numeric timestamp and an HTTP status.

- Deleted `cache/` and ran `warm_cache.py` twice: **0.89 credits cold, 0.00 warm.** Private cases 11-13 still BLOCK / BLOCK / ESCALATE.
- Tests: 147 passed.
- From 17:15 (feature freeze): bug fixes only, as Krishna or Ayush report them.

### ~15:25: same-name fix (Krishna's case 12 bug), private cases, warm_cache defaults
- Pulled main and read `docs/ISSUES.md`. Two items were addressed to Lavya: the same-name bug (top) and `warm_cache.py` defaulting to the private cases.
- Installed Krishna's private fixtures (`fixtures/private/build_private.py`, gitignored) and built cases 11-13 against Bata India.
- **Same-name bug, reproduced live:** two people with the departed finance head's name both worked at Bata (a 2015 sales intern and the finance head who left 2026-10). The check took the first result, the intern.
  - Fix: score each candidate by role match to the claimed role, then by most recent role.
  - If it's still ambiguous (best < 60, or runner-up within 10 points) → UNVERIFIABLE, never CONTRADICTED.
  - The chosen person's id, title and dates go into `value`/`sources`.
  - Search limit raised from 3 to 10. 4 new offline tests.
- `warm_cache.py` now runs only the private live-demo cases by default (`--all` adds the synthetic ones). `--case` handles ids like "05b".
- **Live, private cases 11-13:** BLOCK / BLOCK / ESCALATE, all as expected. Case 12 now matches the finance head (person 190891848). 0.69 credits cold, 0.00 warm.
- Noted for Krishna: case 11 blocks because `bata-india.co` is unregistered (domain age), not because of the lookalike, which is weak (E10) under his split.
- Tests: 143 passed.

### ~15:50: first live Crustdata run (Lavya's key in `.env`)
- Tested live against Bata India (Crustdata id 573), the vendor in Krishna's live demo. 1.89 credits.
  - `bata.in` → sender domain VERIFIED (id 573, with request id and record id in the source).
  - `bata.com` → UNVERIFIABLE: Crustdata says it belongs to Bata Group (id 1135086), the parent. That's correct fail-closed behaviour for a parent/subsidiary domain.
  - `bata-india.co` → CONTRADICTED (no record ties it to Bata India; free call).
  - Current CFO, found by `current_role_holder` → `requester_current_role` VERIFIED (record updated 2026-11-11). The same person claiming a different role → CONTRADICTED. The person search filtered by company id 573 works, as Krishna asked.
- **Fixed: `vendor_active` said Bata's site "did not load".** `bata.in` answers Crustdata's fetcher with HTTP 403 "Access Denied" (bot protection), even with `human_mode`. The check now retries with `human_mode` on 401/403/429. If the site still refuses, it counts as alive only when the Crustdata record is active and fresh (≤ 30 days); otherwise UNVERIFIABLE. Bata → VERIFIED.
- **Fixed: one call waited 51 s.** Web fetches shared the 5-per-minute bucket with search. `/web/*` now has its own 10-per-minute limiter, as the account allows.
- `warm_cache.py` live, all 14 cases: run 1 spent 1.00 credit (4 live calls), run 2 spent 0.00 (all 21 cached). Definition of done met.
- Credits per case, as Krishna asked: synthetic cases cost ~0 (unmatched identify is free). The 1 credit is the web fetch of `acmeleather.in`. A Bata request costs ~0.2 (domain) + ~0.7 (person search) + ~1-2 (vendor active, payments only), so about 1-3 credits cold and 0 warm.

### ~15:35: lookalike strength, to match Krishna's B2/E10 split
- Krishna answered the 15:00 request: strong imitation still BLOCKS (B2), weak signals ESCALATE (new E10). The policy reads the start of the check's `reason`.
- Fixed the check to compare the name and the ending separately. Before, `acmeleaf.co` vs `acmeleaf.in` counted as "2 characters away" (strong). Now it is "same name under a different ending" (weak).
  - Strong: punycode, look-alike characters, 1-2 characters from the vendor's name.
  - Weak: same name under a different ending, contains the vendor's name.
- Added `value["strength"]` ("strong"/"weak"). Case 3's `acmeleathers.in` is still strong, so it still blocks.
- Krishna's other answers: synthetic cases stay the offline spec, and case 1 escalating live is correct fail-closed behaviour. The live demo uses private cases 11-13 against Bata India (Crustdata id 573), and he'll send the fixture file directly. `warm_cache.py` already reads `fixtures/private/vendors.json` and `fixtures/private/requests/` through his loaders.

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
