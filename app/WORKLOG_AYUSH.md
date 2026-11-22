# Ayush worklog: payments and UI

Owner paths: `gate/store.py`, `gate/ledger.py`, `gate/executor.py`, `gate/payments/**`, `app/**`, `tests/pay/`.
Newest entries go at the bottom. Each entry lists what changed, how it was tested, and anything open.

---

## 22 Nov 2026, 13:45–14:30 IST: Stage 1 (Kickoff), steps 1–5

### `gate/store.py`: SQLite store (WAL)
- DB at `GATE_DB` (default `runs/gate.sqlite`). Opens one connection per call so it's safe across Streamlit threads. Writers use `BEGIN IMMEDIATE` through `store.tx()`.
- Tables: `vendors`, `vendor_accounts`, `requests`, `decisions`, `approvals`, `receipts`, `outbox`, `payouts`, `calls`, `ledger` (+ `mock_payouts`, owned by the mock provider).
- Account numbers are stored as last 4 + HMAC-SHA256(`ACCOUNT_HASH_KEY`) only. `Claims.pay_to_account` is replaced with `pay_to_account_last4` / `pay_to_account_hash` before storing. Raw email text is stored only as a SHA-256.
- All stubs are implemented: `init_db`, `upsert_vendor`, `get_vendor`, `save_request`, `save_decision` (ESCALATE → state `ESCALATED`; a decision that is APPROVED, REJECTED or PAID is never reopened by a re-run), `history_for` (documented keys + `state`, `received_at`), `pending_escalations`, `record_approval` (one conditional UPDATE; returns False on a double click).
- Extras for teammates and the UI: `load_fixtures(path)`, `hash_account()`, `last4()`, `get_decision()`, `decision_from_dict()`, `list_decisions()`, `list_payouts()`, `list_outbox()`, `find_vendor_by_domain()`, `record_calls(budget)` (mirrors RunBudget lines), `credits_summary()`.
- Every request, decision and approval write appends a ledger event in the same transaction.

### `gate/ledger.py`: hash-chained audit ledger
- `hash = sha256(prev_hash + canonical_json({event_type, at, payload}))`, genesis = 64 zeros.
- SQLite triggers `RAISE(ABORT)` on UPDATE and DELETE.
- `verify(path=None)` replays the chain → `{ok, rows, first_bad_row, reason}`. It can check an auditor's copy of the DB.
- `events()` returns rows for the UI.

### `gate/payments/razorpayx.py`
- `PAYMENTS_MODE=mock` (default): an in-SQLite provider. The same key and body return the same payout; the same key with a different body raises `PayoutRejected`. It settles `processing → processed` on the first poll.
- `PAYMENTS_MODE=test`: `requests` calls to `POST /v1/payouts` with basic auth and the `X-Payout-Idempotency` header, a composite `fund_account` (bank_account, IMPS, "vendor bill") and `reference_id` = outbox key. `get_payout` and `find_by_reference` use `GET /v1/payouts?reference_id=`. Non-`rzp_test_` keys are refused. The beneficiary account comes from `RAZORPAYX_TEST_BENEFICIARY` because we never store full numbers.
- `PayoutError` = outcome unknown (retry with the same key). `PayoutRejected` = definite 4xx.

### `gate/executor.py`
- `issue_receipt(decision, approver)` returns `{request_id, action_hash, nonce, expires_at (+10 min), approver, signature}` with an HMAC signature. ALLOW only, or ESCALATE that a named person APPROVED. BLOCK and REJECTED are refused.
- `execute(decision, receipt)` checks the signature, request id, `action_hash == contracts.action_hash(action)`, expiry and the single-use nonce. In one transaction it spends the nonce and inserts the outbox row (`state='unknown'`, exact JSON body) plus a ledger `payout_intent`. It then calls `create_payout(stored bytes, same key)` and records the payout, `sent`, decision `PAID` and ledger `payout_sent`.
- An existing key with the same action is replayed (`replayed=True`, no new payout). An existing key with a different action is refused.
- `resume()`: for each `unknown` row, it first runs `find_by_reference` (adopting the payout if found), otherwise resends the identical body and key.
- Also added `refresh_payouts()` (polls status) and `pay(decision, approver)` (receipt + execute).
- `GATE_CRASH_AT=after_unknown|after_payout` → `os._exit(17)` for the crash demo.

### `tests/pay/`: 20 tests, all passing offline
- `test_crash.py`: a subprocess crashes right after the `unknown` write, and also after the provider call but before recording. `resume()` leaves exactly one provider payout. A second resume and a re-execute are no-ops.
- `test_executor.py`: execute twice gives one payout; the same invoice from a new request is replayed; key reuse with a different action is refused; nonce reuse, a wrong action hash, forged and expired receipts, BLOCK and unapproved or rejected ESCALATE are all refused; a provider timeout leaves `unknown` and `resume()` finishes it.
- `test_store_ledger.py`: vendor round trip with no full account number anywhere in the DB file; claims redaction; double-click approve returns False; ledger triggers block edits; a tampered or deleted row in a raw DB copy is caught by `verify()`.

### Open
- RazorpayX test keys: not set yet (`.env` missing). Mock mode is the default.

---

## 22 Nov 2026, ~14:45 IST: Stage 1, step 6: Streamlit approval UI

### `app/approvals.py` (`streamlit run app/approvals.py`)
- Sidebar: approver name, payments mode, run-credits panel (from the `calls` mirror), live ledger status, and Developer → "Seed demo decisions".
- **Inbox** tab: decisions with verdict badges (green ALLOW, red BLOCK, amber ESCALATE) and a filter. Clicking one opens the decision card:
  - rules fired, with their reasons and check names;
  - each Check with a status icon, value, note and clickable source links (http(s) only; all untrusted text is HTML-escaped);
  - the vendor-master bank account next to the claimed account (last 4 only), marked NEW or on file;
  - the payment summary and idempotency key, and urgency cues marked "logged only";
  - Approve / Reject for ESCALATED items. Approve calls `store.record_approval` first, then `app/worker.py`. A double click shows "already decided".
- **Ledger** tab: "Verify chain" button and the event table (hash and prev hash).
- **Payouts** tab: payouts, outbox, "Refresh status" (polls the provider), "Resume unfinished" (`executor.resume()`), and the mock provider's own view of its payouts.
- Loads `.env` if it exists (no new dependency).

### `app/worker.py`
- `pay_approved(request_id, approver)` runs only in the APPROVED state, then calls `issue_receipt` and `execute`. The UI never calls the provider itself.

### `app/dev_seed.py` (`python -m app.dev_seed`)
- One synthetic vendor and four decisions: a clean invoice (ALLOW, paid), a lookalike-domain bank change (BLOCK B2), a genuine bank change (ESCALATE E1/E2) and an unverifiable requester (ESCALATE E6). These are only for development until Krishna's pipeline is ready.

### Tests
- `tests/pay/test_ui.py`: headless `streamlit.testing` run. It renders 3 tabs, approves DEMO-5 (→ PAID, a 2nd mock payout) and checks that Verify chain says intact.
- Full suite: **29 passed** offline (`MOCK=1 python -m pytest -q`).

### Open / next (Stage 2, from 15:30)
- Wire the "Run a request" panel to `gate.pipeline.run` once Krishna's pipeline lands (it currently raises NotImplementedError).
- Add the simulate-crash toggle and on-stage Resume. The crash must run in a subprocess, because `os._exit` would kill Streamlit.
- RazorpayX test keys: still not set.

---

## 22 Nov 2026, ~14:30 IST: aligned with Krishna's `gate/keys.py`, pipeline verified

- `store.hash_account()` now calls the shared `gate.keys.account_hash` (as ISSUES.md 14:10 asks), so the store, verifiers and payouts agree byte for byte. `last4()` now keeps digits only.
- `app/dev_seed.py` and `tests/pay/conftest.py` build invoice keys and idempotency keys with `keys.invoice_key` / `keys.idempotency_key(keys.payment_fingerprint(...))`.
- Krishna's pipeline now uses the real store, ledger and executor; it no longer needs the in-memory fallbacks. `MOCK=1 python scripts/run_demo.py` gives **13/13 as expected**.
  - The ALLOW cases (01 calm/pushy, 07, 10) each pay once. They are four distinct invoices (42/45/43/44). Re-running the demo replays them ("replayed, not paid twice").
  - Ledger verify: OK.
- Full suite: **78 passed** offline.
- Note for Krishna: the pipeline appends its own `request` / `decision` ledger events, and the store also appends them inside the write transaction, so each request shows up twice in the ledger. That's harmless, but the pipeline's `_ledger` calls can be dropped.

---

## 22 Nov 2026, ~14:10 IST: Stage 2 (Integration), started early because the pipeline was ready

- New **"Run a request"** tab (first tab) in `app/approvals.py`:
  - lists every file in `fixtures/requests/` and `fixtures/private/requests/` (private ones marked 🔒);
  - shows the case title, expected verdict, and the raw request in an "untrusted" expander;
  - has a run credit ceiling (number input) → `RunBudget`;
  - "▶ Run the gate" loads the vendor master into the store (`fixtures/vendors.json` + private), calls `gate.pipeline.run_case`, mirrors the budget's calls into the `calls` table (sidebar credits panel), and shows expected vs actual, the trace, the payout and the live decision card.
- **Simulate crash** toggle: the pipeline runs with `execute=False`, then `app.worker.pay_with_crash()` pays in a **child process** that `os._exit()`s right after the outbox `unknown` write (Streamlit stays alive). The UI shows "Payer crashed, outbox row is unknown". **♻ Resume** calls `executor.resume()` and shows the payout count for that invoice (1).
- An escalated request can be approved from the run card or the Inbox: approval → `worker.pay_approved` → receipt → execute → payout, then the Payouts tab updates.
- `tests/pay/test_ui.py`: new headless test that runs case 01 with the crash on, checks for 0 provider payouts and an `unknown` outbox row, presses Resume (→ exactly 1 payout), then re-runs without a crash (replayed, still 1).
- Full suite: **79 passed** offline.

### Not done / blocked
- **RazorpayX test mode:** no `.env` and no `RAZORPAY_KEY_ID/SECRET` on this machine, so the live test-mode run of case 1 is not done. The code path exists (`PAYMENTS_MODE=test`). To finish it: put the test keys and `RAZORPAYX_ACCOUNT_NUMBER` in `.env`, set `PAYMENTS_MODE=test`, run case 1 from the UI, and use Payouts → Refresh status (test payouts stay `processing` until moved in the dashboard).
- **For the Stage 3 demo:** case 5 (genuine bank change) has no `PaymentAction`. Approving it records the approval, but there's nothing to pay yet ("approved, no payment action"). "Approved by a person, payout follows" needs an invoice to the new account after approval. Ask Krishna whether a fixture should carry that.

---

## 22 Nov 2026, ~14:40 IST: RazorpayX test mode verified live

- Ayush set up a RazorpayX test account: ₹10,00,000 test balance, Yes Bank current account (test). Keys and the account number are in the local `.env` only, never committed.
- Fix in `gate/payments/razorpayx.py`: narration and contact/beneficiary names are reduced to letters, digits and spaces (`_clean`), because RazorpayX rejects other characters, e.g. the `-` in "Inv 2026-27-42".
- Live results (DB `runs/razorpayx_live.sqlite`, `PAYMENTS_MODE=test`, `MOCK=1` for extraction/checks):
  - **Case 01 → ALLOW → real test payout `pout_U39vdsbD0keLmy`**, ₹1,18,000, status `processing` (test payouts stay processing until moved in the dashboard).
  - Running case 01 again replays `pout_U39vdsbD0keLmy` and doesn't pay twice.
  - Resending the exact outbox bytes with the same key directly to Razorpay returns the same payout id, so Razorpay's own idempotency confirms it.
  - The same key with a changed amount is rejected by Razorpay: `400 Different request body sent for the same Idempotency Header`.
  - **Live crash:** case 07 is paid in a child process that dies right after Razorpay accepted the payout (before we recorded it). `resume()` finds it by `reference_id` (`pout_U39vuKxQCDWYuO`) and adopts it instead of paying again, so there's exactly one payout.
- Full suite still **79 passed** offline (tests force `PAYMENTS_MODE=mock`).
- For the demo: start the UI with `PAYMENTS_MODE=test` (from `.env`). Payouts tab → "Refresh status" shows `processing` honestly. To show `processed`, move the payout in the RazorpayX dashboard (Payouts → the payout → mark processed in test mode).

---

## 22 Nov 2026, ~14:40–15:00 IST: Stage 3 (Polish)

Read `docs/ISSUES.md` after pulling. The `## pay` section was empty (no bugs reported against Ayush's files). Krishna added **case 5b** (first invoice to the new account → ESCALATE E2 → approve → payout) and said to start Stage 3.

- **Demo tab** (first tab in `app/approvals.py`; logic in `app/demo.py`, testable without the UI):
  - "⟲ Start fresh demo" creates a new `runs/demo-ui-HHMMSS.sqlite` and loads the vendor master;
  - five steps, each with a 🎙 "what to say" line, a ▶ Run button, a large verdict badge and the reasons;
  - non-verified checks are shown with their notes and sources (the contradicting source is on screen for the BLOCK);
  - the steps: 03 lookalike → BLOCK B2; 05 genuine bank change → ESCALATE E1 → Approve (nothing to pay, by design); 05b → ESCALATE E2 → Approve → payout; 01 + crash → "Payer killed, outbox unknown" → ♻ Resume → "payouts for this invoice: 1"; 02 re-sent → BLOCK B1, still 1 payout.
- **Export decision report** (`app/report.py`): Markdown with the request (raw text only as SHA-256), rules fired, claims (account last 4 only), every check with status/value/note/sources, the payment action and hashes, bank accounts old vs claimed, approvals, payouts, and the ledger rows for the request with chain status. Download buttons are on every decision card and every demo step.
- **`docs/DEMO_SCRIPT.md`**: the 2-minute script, opening with the customer's request in their own words, with timings, on-screen cues, what to say, setup and backup answers. (Krishna owns `docs/`, but the Stage 3 prompt assigns this file to Ayush.)
- Replaced the deprecated Streamlit `use_container_width` with `width="stretch"`.
- Tests: `tests/pay/test_demo.py` covers the whole walkthrough offline (2 payouts in total: 05b and 01, each once), the report contents (no full account number, no raw email), and a headless click-through of the Demo tab. **139 passed** (whole repo). A Streamlit server boot check passes (`/_stcore/health` ok).
- Found and reported in `docs/ISSUES.md` (for Krishna): the fixture account hashes were made with the default `ACCOUNT_HASH_KEY`. Setting the team key makes case 05b BLOCK. **For the demo, leave `ACCOUNT_HASH_KEY` empty.**

### Left for Ayush (human)
- Rehearse with `docs/DEMO_SCRIPT.md`, then **record the 2-minute video at ~17:15** from the Demo tab.
- From 17:15: bug fixes only.
