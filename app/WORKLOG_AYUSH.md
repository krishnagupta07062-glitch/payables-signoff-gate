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
