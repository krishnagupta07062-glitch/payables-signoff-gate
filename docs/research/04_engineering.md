# Research 4: Engineering building blocks for the Sign-Off Gate for payables
Date: 2026-11-22. Machine egress IP geolocates to **IN**. Everything marked **[TESTED]** was run live today from this machine. Everything marked **[DOC]** comes from official docs fetched today.

---

## 0. TL;DR recommended stack (for about 5 hours)

| Layer | Choice | Why |
|---|---|---|
| Durable state | **Plain SQLite (WAL) state machine plus a transactional outbox**, written by hand (about 150 LOC) | No new framework to learn. Crash and resume is easy to show and explain to judges. DBOS is the fallback if you want a library (it defaults to SQLite, `pip install dbos`, v3.6.0 on 2026-11-17). |
| Payment rail | **RazorpayX Payouts, test mode** (`POST /v1/payouts` with `X-Payout-Idempotency`) | This is the real "pay a vendor" primitive. Test mode needs no KYC. The idempotency header is mandatory, so exactly-once is native. Stripe is **invite-only in India**, so avoid it. |
| Fallback rail | Razorpay **Payment Links**, test mode (unique `reference_id` returns a 400 on reuse) | Use this if the RazorpayX dashboard won't open for your login. The same PG test keys work. |
| Vendor checks | Offline GSTIN checksum, GST portal `goodservice` (no captcha) [TESTED], Razorpay IFSC API [TESTED], RDAP domain age [TESTED], RazorpayX fund-account validation (penny drop) | All free. |
| Approval UI | **Streamlit** (1.67.0, 2026-11-05), with conditional SQL `UPDATE ... WHERE state='ESCALATED'` | Fastest to build. FastAPI+HTMX if you already have FastAPI. |
| Audit | Append-only, SHA-256 hash-chained `ledger` table plus a `verify()` replay script [TESTED: detects tampering] | Lets an auditor replay the decisions. |
| Paid lookups | Crustdata through a **body-hash cache** plus a credits ledger and a run ceiling [TESTED: 7 credits spent, `X-Credits-Used` header present] | A crash or retry never re-spends credits. |

---

## 1. Exactly-once payments

### 1.1 RazorpayX Payouts (recommended)

**Setup steps (about 10 minutes) [DOC]**
1. Sign up at https://x.razorpay.com/auth/signup (or log in with an existing Razorpay PG account, which uses the same credentials). Signup needs email, password, name, phone, business category and an email OTP. **KYC is only for live mode.** Reddit threads from 2026 confirm that test keys work before KYC.
2. Profile icon → switch to **Test Mode**.
3. My Account & Settings → Developer Controls → **Generate Key**. Test mode needs no OTP. **Download the key secret immediately**, because it is shown only once.
4. Dashboard → **+ Add test balance** (any dummy amount). Payouts need balance; without it they go `queued` (with `queue_if_low_balance:true`) or fail.
5. Note your **test "Customer Identifier" / account_number** (My Account & Settings → Banking). It is different in test and live. Pass it as `account_number`, **not** the vendor's account.
6. **IP allowlisting applies only in live mode** [DOC], so test mode works from a laptop.

**Gotchas [DOC]**
- **The `razorpay` Python SDK (v2.0.1) has no payout or contact resource.** I checked the `razorpay/resources` listing on GitHub. Use `requests` directly with basic auth `(key_id, key_secret)`.
- `X-Payout-Idempotency` has been **mandatory since 2025-03-15**. Without it you get a 400 "Idempotency key is missing". The key is 4 to 36 characters from `[A-Za-z0-9 _-]`; Razorpay recommends UUIDv4. A **UUIDv5 of the invoice fingerprint is 36 characters and fits.**
- On retry the **body must be identical**. A different payload with the same key gets a 400 ("Different request body sent for the same Idempotency Header"). **Store the exact JSON body in the outbox and replay those bytes. Do not rebuild the body.**
- Razorpay saves the first response and maps every retry to one payout. "Do **not** retry with a *fresh* key while the first attempt is still `processing`, or you will get two payouts." Rotate the key only after a terminal `failed`.
- **In test mode, payouts stay in `processing` until you move them manually in the dashboard.** Plan the demo around this: show `processing`, then click it to `processed`, or treat `processing` as "sent, awaiting confirmation".
- The approval workflow (`pending` / `rejected` states) is **not available in test mode**. That is fine, because your own gate does the approval.
- States: `queued`, `pending`, `processing`, `processed`, `reversed`, `cancelled`, `failed`. `processed` can still flip to `reversed` within T+3 days.
- Webhooks can fire more than once, so dedupe on `(payout_id, status)`. Test-mode webhook events are `payout.queued`, `payout.initiated`, `payout.processed`, `payout.reversed` and `transaction.created`. Webhooks need a public URL (ngrok). For a demo, **poll `GET /v1/payouts/{id}`**, which is fine at hackathon scale even though Razorpay prefers webhooks.
- Reconciliation hook: `GET /v1/payouts?account_number=…&reference_id=<your invoice id>` lists payouts by your own reference [DOC: `reference_id` is a documented query parameter]. Set `reference_id` (40 characters max) to your invoice/outbox id. This is a second line of defence after a crash.
- `narration`: 30 characters max, `[A-Za-z0-9 ]` only.
- Amounts are in paise, minimum 100. `mode` must be upper case (`IMPS`/`NEFT`/`RTGS`/`UPI`).
- Rate limit guideline: 5 to 10 TPS.

**Flow:** Contact (`POST /v1/contacts`) → Fund account (`POST /v1/fund_accounts`, bank_account or vpa) → optional validation (`POST /v1/fund_accounts/validations`, penny drop of ₹1, returns `results.account_status` and `registered_name`, plus `name_match_score` in newer responses) → Payout (`POST /v1/payouts`). The composite APIs do contact, fund account and payout in one call and also accept the idempotency header.

```python
# payout.py  (requests, not the SDK)
import requests, json, uuid
RZP = "https://api.razorpay.com/v1"
AUTH = (KEY_ID, KEY_SECRET)                     # rzp_test_...
NS = uuid.UUID("6f1c2a4e-9b1d-4c33-8e0a-5a7d2b9c0f11")

def make_payout_body(inv, fund_account_id):
    return {"account_number": RZPX_TEST_ACCOUNT_NO, "fund_account_id": fund_account_id,
            "amount": inv.amount_paise, "currency": "INR", "mode": "IMPS",
            "purpose": "vendor bill", "queue_if_low_balance": True,
            "reference_id": inv.outbox_id[:40], "narration": "Inv " + inv.short_no[:20],
            "notes": {"invoice_fp": inv.fingerprint[:250]}}

def send_payout(idem_key: str, body_json: str, timeout=15):
    # body_json is the EXACT string stored in the outbox; never re-serialize
    r = requests.post(f"{RZP}/payouts", auth=AUTH, data=body_json, timeout=timeout,
                      headers={"Content-Type": "application/json", "X-Payout-Idempotency": idem_key})
    return r.status_code, r.json()
```

### 1.2 Stripe test mode: not recommended for this team
- [DOC, support.stripe.com] **"Stripe services are invite-only in India. Businesses from India can't sign up for a new Stripe account through our website"** (since May 2024 and still in force in 2026). Signing up as another country to get a sandbox misrepresents your country, and it gives you USD card PaymentIntents, which is the wrong primitive for paying Indian vendors.
- Idempotency facts [DOC], in case a teammate already has a Stripe sandbox: header `Idempotency-Key` up to 255 characters, on all v1 POSTs. Stripe saves the status and body of the first request *after endpoint execution begins*, **including 500s**. Keys may be pruned after **24 hours**, after which a reused key creates a new object. Stripe errors if the parameters differ. Validation failures and concurrent conflicts are not saved, so they are safe to retry. API v2 behaves differently: it retries failed work to completion.
- Verdict: Razorpay is faster (minutes, no invite) and India-native.

### 1.3 Durable execution options compared

| Option | Setup cost | Resume semantics | Fit for 5 hours |
|---|---|---|---|
| **Hand-rolled SQLite state machine + outbox** | 0 deps | You define the states. A worker loop picks up non-terminal rows on start. | **Best.** Easiest to explain to judges. |
| DBOS Transact Python (`pip install dbos`, 3.6.0) | Low. Defaults to SQLite with no config; Postgres via `DBOS_SYSTEM_DATABASE_URL` [DOC + Crustdata search] | `@DBOS.workflow` / `@DBOS.step` checkpoints. `SetWorkflowID(key)` makes a workflow start at most once. Recovery on restart. | Good, but steps run *at least once*, so the payout step still needs the Razorpay idempotency key. |
| LangGraph + `langgraph-checkpoint-sqlite` 3.1.3 | Medium | Checkpoint after every node. `interrupt()` for human-in-the-loop. **The node re-runs from the start on resume** [DOC], so side effects before the interrupt must be idempotent. | Only if the team already uses LangGraph. |
| Temporal / Restate / Inngest | High (server or cloud account) | Strong | Overkill for 5 hours. |

**Key point for judges:** no engine gives exactly-once *external* side effects. Every engine gives at-least-once execution plus deduplication. Exactly-once payment comes from **(a)** a durable intent committed *before* the call (the outbox), **(b)** a provider idempotency key derived deterministically from that intent, and **(c)** reconciliation by `reference_id` after a crash.

### 1.4 Recommended design: SQLite state machine + outbox

```
RECEIVED → EXTRACTED → VERIFYING → DECIDED{ALLOW|BLOCK|ESCALATE}
   ESCALATE → (human) APPROVED | REJECTED
   ALLOW/APPROVED → PAYOUT_QUEUED (outbox row + frozen body + idem key, same txn)
   PAYOUT_QUEUED → PAYOUT_SENT (got 2xx, payout_id stored) → PAYOUT_CONFIRMED (processed)
                 → PAYOUT_UNKNOWN (timeout/5xx) → retried with SAME key+body → PAYOUT_SENT
   any check timeout → HOLD(retry_at) ; attempts exhausted → ESCALATE (never ALLOW)
```

```python
# store.py
import sqlite3, json, uuid, time
db = sqlite3.connect("gate.db", isolation_level=None, check_same_thread=False)
db.execute("pragma journal_mode=WAL"); db.execute("pragma synchronous=FULL")
db.executescript("""
create table if not exists invoices(id text primary key, fp text unique, state text, verdict text,
   reasons text, updated real);
create table if not exists outbox(id text primary key, invoice_id text unique references invoices(id),
   idem_key text unique, body text, status text, payout_id text, attempts int default 0, updated real);
""")
NS = uuid.UUID("6f1c2a4e-9b1d-4c33-8e0a-5a7d2b9c0f11")

def enqueue_payout(inv_id, fp, body: dict):
    key = str(uuid.uuid5(NS, fp))                  # deterministic: same invoice -> same key forever
    body_s = json.dumps(body, sort_keys=True, separators=(",", ":"))
    db.execute("begin immediate")
    try:
        cur = db.execute("update invoices set state='PAYOUT_QUEUED', updated=? where id=? and state in ('ALLOW','APPROVED')",
                         (time.time(), inv_id))
        if cur.rowcount == 1:                      # conditional transition = no double-enqueue
            db.execute("insert or ignore into outbox(id,invoice_id,idem_key,body,status,updated) values(?,?,?,?, 'QUEUED',?)",
                       (inv_id, inv_id, key, body_s, time.time()))
        db.execute("commit")
    except: db.execute("rollback"); raise

def drain_outbox():                                # called on startup AND in the loop
    for oid, key, body, status, pid in db.execute(
            "select id,idem_key,body,status,payout_id from outbox where status in ('QUEUED','UNKNOWN','SENT')").fetchall():
        if status == "SENT":                       # already have payout_id: just poll status
            poll_and_maybe_confirm(oid, pid); continue
        db.execute("update outbox set attempts=attempts+1, status='UNKNOWN', updated=? where id=?", (time.time(), oid))
        try:
            code, resp = send_payout(key, body)    # same key + same bytes every time
        except requests.Timeout:
            continue                               # stays UNKNOWN; next loop retries with SAME key
        if code < 300:
            db.execute("update outbox set status='SENT', payout_id=? where id=?", (resp["id"], oid))
            ledger.append("payout_sent", {"outbox": oid, "payout_id": resp["id"], "status": resp["status"]})
        elif code == 400 and "Different request body" in json.dumps(resp):
            db.execute("update outbox set status='HALT' where id=?", (oid,))   # bug guard: human looks
        elif resp.get("status") == "failed":
            db.execute("update outbox set status='FAILED' where id=?", (oid,))  # only now may a NEW key be issued, by a human
```

Notes:
- Mark the row `UNKNOWN` **before** the HTTP call. A crash mid-call then resumes as "maybe sent", and the resend with the same key is deduplicated by Razorpay.
- Belt and braces on startup: for `UNKNOWN` rows, call `GET /v1/payouts?account_number=…&reference_id=<oid>` first. If a payout exists, adopt its id.
- Demo script: start the worker, `kill -9` it mid-payout, restart, show one payout in the RazorpayX dashboard and the ledger lines "payout_sent (attempt 2, same key)".
- A bank-detail change is an irreversible action too. Model it as a `vendor_change` row that is **always ESCALATE**, and only apply it to the vendor master (new fund account) after human approval plus a penny-drop name match.

### 1.5 Time and credit ceiling, plus a call ledger (covers the Crustdata request)

```python
# calls.py: every external call (LLM, Crustdata, GST, RDAP, Razorpay) goes through here
db.executescript("""
create table if not exists calls(id integer primary key, run_id text, provider text, endpoint text,
  req_hash text, status text, credits real, cost_inr real, latency_ms int, cache_hit int, ts real);
create table if not exists cd_cache(req_hash text primary key, path text, body text, resp text, credits real, ts real);
create table if not exists runs(run_id text primary key, started real, deadline real, credit_ceiling real);
""")
def req_hash(path, body): return hashlib.sha256((path + "\n" + canon(body) + "\n2025-11-01").encode()).hexdigest()

def crustdata(run_id, path, body, expected_cost=1.0):
    h = req_hash(path, body)
    hit = db.execute("select resp from cd_cache where req_hash=?", (h,)).fetchone()
    if hit:                                                       # crash/retry never re-spends
        log_call(run_id, "crustdata", path, h, "cache", 0, cache_hit=1); return json.loads(hit[0])
    spent = db.execute("select coalesce(sum(credits),0) from calls where run_id=?", (run_id,)).fetchone()[0]
    ceiling, deadline = db.execute("select credit_ceiling, deadline from runs where run_id=?", (run_id,)).fetchone()
    if spent + expected_cost > ceiling or time.time() > deadline:
        raise BudgetExceeded()                                    # caller -> HOLD/ESCALATE, never ALLOW
    # write the intent first: if we crash after the provider charged us, the ceiling still counts it
    cid = log_call(run_id, "crustdata", path, h, "inflight", expected_cost)
    r = requests.post("https://api.crustdata.com" + path, json=body, timeout=30,
        headers={"Authorization": f"Bearer {KEY}", "x-api-version": "2025-11-01"})
    credits = float(r.headers.get("X-Credits-Used") or expected_cost)
    db.execute("update calls set status=?, credits=? where id=?", (str(r.status_code), credits, cid))
    if r.ok: db.execute("insert or replace into cd_cache values(?,?,?,?,?,?)", (h, path, canon(body), r.text, credits, time.time()))
    return r.json()
```
- Cache key = sha256(path + canonical JSON (sort_keys, no spaces) + api version).
- An in-flight row with no response, found after a crash, is counted at `expected_cost`. This is conservative: the ledger never under-counts.
- Do the same for LLM calls: log `usage.input_tokens/output_tokens` and the computed cost. Cache extraction results by `sha256(file bytes + prompt version + model)` so a restart doesn't re-bill extraction.
- Crustdata gotchas [TESTED/DOC]:
  - `/web/search/live` costs 1 credit per page (`page:N` costs N). The rate limit is **10 req/min**.
  - `/web/enrich/live` takes up to 10 URLs per call, returns raw HTML in `content`, and failed entries come back with `url:null`.
  - Search results are often **`google.com/goto?url=…` redirect links**, not the target URL, so unwrap them or use snippets.
  - `location:"IN"` returned **Hindi-localised dates** ("8 अक्टू॰ 2026"). Use `"US"` for cleaner parsing.
  - `X-Credits-Used` was present and equal to 1.0 on every call. My test cache is at `scratchpad\r4\cd_cache.sqlite`; 7 credits were spent in total.

---

## 2. Indian invoice and vendor verification sources

### 2.1 GSTIN: format and checksum [TESTED]
Structure: `SS` state code (01 to 38, 97 = other territory, 99 = Centre/CBIC) + **10-character PAN** (positions 3 to 12) + entity number (1 to 9, then A to Z) + `Z` (default) + check character.
Regex for ordinary taxpayers: `^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$`. Other layouts exist (TDS deductor has `D` at position 14, UIN, non-resident OIDAR), and all use the same check digit.

**Check-digit algorithm (mod 36, alternating weights 1,2):**
```python
A = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
def gstin_check_char(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        p = A.index(ch) * (1 if i % 2 == 0 else 2)   # weight 1 on odd positions (1st,3rd..), 2 on even
        total += p // 36 + p % 36                     # add quotient + remainder
    return A[(36 - total % 36) % 36]
def gstin_valid(g: str) -> bool:
    g = g.strip().upper()
    return bool(re.fullmatch(r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z][A-Z][0-9A-Z]", g)) and gstin_check_char(g[:14]) == g[14]
```
Tested: `27AAACR5055K1Z7` (Reliance) True; `33AAACC1206D1ZN` (Central Warehousing Corp) True; `33AAACC1206D1ZM` False; `29AAACR5055K1ZX` False (correct is `3`).
Cross-checks to apply:
- GSTIN[2:12] must equal the vendor's PAN.
- GSTIN[0:2] must match the state in the vendor address / place of supply. Use the free state master: `GET https://services.gst.gov.in/master/allstates?includeCbic=true` [TESTED, no captcha].

### 2.2 GST portal lookups
- **No official free API.** The official route is the GST API through a licensed **GSP** (paid, needs onboarding), which is not feasible today.
- The public "Search Taxpayer" (legal name, status Active/Cancelled, registration date) is **captcha-gated**: `GET /services/captcha` then `POST https://services.gst.gov.in/services/api/search/taxpayerDetails {"gstin","captcha"}`. The captcha is single-use and session-bound. Human-in-the-loop option: show the captcha image in the approval UI and let the approver solve it. That is honest, and judges like it.
- **Captcha-free endpoints [TESTED today, via Python urllib with a browser User-Agent and `Referer: https://services.gst.gov.in/services/searchtp`, after first GETting `/services/searchtp` for cookies]:**
  - `GET https://services.gst.gov.in/services/api/search/goodservice?gstin=27AAACR5055K1Z7` returned `{"bzgddtls":[{"gdes":…,"hsncd":"55151190"},…]}` (goods HSN) or `bzsdtls` (services SAC).
  - For a checksum-valid but fake GSTIN (`27AAPFU0939F1ZV`) it returned `{"errorCode":"FO8000","message":"No records found"}`. **This is a free existence signal** and lets you **cross-check invoice HSN against the vendor's registered HSN/SAC**.
  - `GET /services/api/dropdownfinyear?gstin=…` returns the years with returns. It answered with a stub even for the fake GSTIN, so it is not a signal.
  - **Gotchas:** **curl gets "Connection reset"** (TLS/WAF fingerprinting), while Python `urllib`/`httpx` works. Treat FO8000 as "ESCALATE: cannot confirm registration", not as BLOCK, because some genuine registrations may list no HSN. Space out requests; the WAF blocks IPs. Unofficial endpoints may change, so timeouts must map to HOLD.
  - Reference library: `gst-validator` (PyPI, MIT, needs Python 3.13+; endpoint map at github.com/rahulgurujala/gst-validator/docs/portal.md).

### 2.3 Razorpay IFSC API [TESTED, free, no auth]
- `GET https://ifsc.razorpay.com/HDFC0CAGSBK` returns 200 with `{"BANK":"HDFC Bank","BANKCODE":"HDFC","BRANCH":…,"CITY":…,"STATE":"KARNATAKA","IMPS":true,"NEFT":true,"RTGS":true,"UPI":true,"MICR":…,"SWIFT":…}`.
- An unknown IFSC returns **404 with body `"Not Found"`**.
- IFSC format: `^[A-Z]{4}0[A-Z0-9]{6}$`.
- Gate rules:
  - On a bank change, BLOCK or ESCALATE if the new IFSC's bank or city differs from the vendor's history or state.
  - If `IMPS:false`, pick mode NEFT.

### 2.4 PAN format
- `^[A-Z]{5}[0-9]{4}[A-Z]$`.
- 4th character = holder type: P individual, C company, H HUF, F firm/LLP, A AOP, T trust, B BOI, L local authority, J artificial juridical person, G government.
- 5th character = first letter of the surname (individuals) or of the entity name.
- The 10th character is a check letter, but **its algorithm is not public**. Validate format, the type letter and the name initial only.
- A free PAN-name lookup is not available. Penny-drop `registered_name` is your name signal.

### 2.5 MCA21 (CIN / DIN)
- CIN format: `^[LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$`, which encodes listed/unlisted, NIC industry code, state, incorporation year, ownership (PLC/PTC/FTC/GOI/NPL…) and a serial.
- The MCA V3 "View Company/LLP Master Data" is free but **captcha/login-gated with no public API**. Third-party APIs are paid.
- Recommendation: format-validate the CIN offline, check that the incorporation year in the CIN is not after the invoice date and that the state code is consistent, and otherwise list "MCA lookup" as a manual approver step.

### 2.6 UPI VPA validation
- Format: `^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$`.
- Real validation needs a provider. **RazorpayX "Validate a VPA"** uses `POST /v1/fund_accounts/validations` with a VPA fund account, or the composite VPA validation API [DOC]. It returns `account_status` (`active`/`invalid`) and `registered_name`.
- In test mode the results are simulated or dummy. Treat it as a demo of the *flow*, and state that clearly to judges.
- UPI Payment Links are **not supported in test mode** (documented 400).

### 2.7 Invoice field requirements: Rule 46 CGST [DOC, cbic.gov.in]
Mandatory particulars:
- (a) supplier name, address and GSTIN
- (b) **serial number ≤16 characters, using only alphanumerics, `-` and `/`, unique per financial year**. This is a free validation rule and the legal basis for duplicate detection.
- (c) date
- (d) recipient name, address and GSTIN
- (g) HSN/SAC
- (h) description
- (i) quantity and unit
- (j) total value
- (k) taxable value
- (l) tax rates (CGST/SGST/IGST/UTGST/cess)
- (m) tax amounts
- (n) place of supply and state (inter-state)
- (o) delivery address if different
- (p) reverse-charge flag
- (q) signature or DSC (not required for electronic invoices)
- (r) **QR code with IRN** where e-invoicing applies

Deterministic checks to run on extracted claims:
- `taxable + taxes ≈ total` (±₹1 rounding).
- Intra-state means CGST = SGST and IGST = 0. Inter-state means IGST only. Derive this from the supplier state code (GSTIN[0:2]) against the place of supply.
- Rate must be in {0, 0.25, 1.5, 3, 5, 12, 18, 28, 40}. GST 2.0 from 2025-09-22 consolidated most goods to 5/18 with 40 for sin goods; 12 and 28 survive only for legacy-dated invoices. Treat an unexpected rate as ESCALATE, not BLOCK.
- The invoice number must match the regex `^[A-Za-z0-9/-]{1,16}$`.

### 2.8 E-invoice IRN and signed QR (verifiable offline)
- The IRN is a 64-hex SHA-256 over supplier GSTIN + FY + document type + document number, unique per FY across GST [DOC ClearTax].
- **The signed QR content is a JWT** signed by the IRP (RS256) [DOC ClearTax, gstinapi]. The payload `data` is a JSON string with `SellerGstin, BuyerGstin, DocNo, DocTyp, DocDt, TotInvVal, ItemCnt, MainHsnCode, Irn, IrnDt`.
- Verify:
  ```python
  import jwt  # pyjwt 2.15.1 + cryptography
  claims = jwt.decode(qr_text, public_key_pem, algorithms=["RS256"], options={"verify_aud": False, "verify_exp": False})
  fields = json.loads(claims["data"])
  # then compare fields with LLM-extracted claims: GSTINs, DocNo (normalized), DocDt, TotInvVal
  ```
- Public keys (.pem and .cer per period, separate for production IRP1, IRP2 and sandbox) are listed at **https://einvoice1.gst.gov.in/Others/Publickeys**. The page rendered an empty table to non-browser fetches today, so **download the PEM manually in a browser** ahead of time. Each IRP (NIC1/NIC2 and the private IRPs) has its own key. The NIC "QR Code Verify" mobile app is the official offline verifier.
- QR decoding from PDF/image: `zxing-cpp` 3.1.1 (pip wheel, no system DLL) is easier on Windows than `pyzbar` (last release 2022, needs zbar DLL). Render the page to an image with PyMuPDF (`pymupdf` 2.1).
- Caveats:
  - A valid signature proves the invoice was *registered*. The IRN can still be cancelled within 24h, and only a GSP API can tell you that.
  - E-invoicing is mandatory above ₹5 cr AATO, so small-vendor invoices legitimately have no QR. "No QR" is therefore not a BLOCK.
  - **Demo honesty:** a self-generated test invoice won't carry a real IRP signature. Show (1) decoding, (2) a tampered QR failing signature verification against the real NIC PEM, and (3) a field mismatch with the extracted text giving BLOCK.

### 2.9 Extraction options
- Digital PDFs: `pdfplumber` 0.11.11 (2026-11-21) or `pymupdf` for text and tables, followed by an LLM (Claude) with a JSON schema / tool for the claims. Keep the raw text span for each claim as evidence for "facts & verification".
- Scanned PDFs or images: send the page images to a vision model. Render with PyMuPDF at 200 dpi.
- Always record `source_span`/page for each field. Make the LLM output *claims only*; deterministic code decides.

---

## 3. Duplicate invoices and lookalike domains

### 3.1 Duplicate detection [TESTED normalizer]
```python
PREFIX = {"TAX","INVOICE","INV","BILL","NO","NUMBER","TI"}
def norm_inv(s):
    s = unicodedata.normalize("NFKC", s).upper()
    toks = [t for t in re.split(r"[^A-Z0-9]+", s) if t]
    while toks and toks[0] in PREFIX: toks.pop(0)
    if toks: toks[0] = re.sub(r"^(INV|INVOICE|BILL)(?=\d)", "", toks[0])
    out = []
    for t in toks:
        if re.fullmatch(r"[0-9OIL]+", t) and re.search(r"\d", t):   # OCR O->0, I/L->1 only in numeric tokens
            t = t.translate(str.maketrans("OIL", "011"))
        out.append((t.lstrip("0") or "0") if t.isdigit() else t)
    return "-".join(out)
# 'INV/2026-27/0042', 'inv 2026 27 42', 'INV/2O26-27/0042', 'Invoice #2026-27-042'  -> all '2026-27-42'
```
Tiers:
1. **Hard duplicate, BLOCK:** same `(supplier GSTIN, norm_inv, FY)`, or the same IRN. Rule 46(b) requires uniqueness per FY. Enforce it with a `UNIQUE` index on the fingerprint so even a crash-race can't double-insert.
2. **Probable duplicate, ESCALATE:** same vendor, and either (a) `rapidfuzz.fuzz.ratio(norm_a, norm_b) ≥ 90`, or (b) same amount (±0.5%) within ±10 days with a different number, or (c) the same PDF SHA-256 or same text SHA-256 (resent file).
3. **Cross-vendor:** same amount and date, different GSTIN, but same bank account. This is a strong fraud signal, so ESCALATE.
- Fingerprint for the idempotency key: `GSTIN|norm_inv|FY|amount_paise`, hashed with uuid5 to give the Razorpay key. A tested example gives a 36-character key.

### 3.2 Lookalike sender domains [TESTED]
- Steps:
  - Lowercase the domain. Decode punycode (`xn--…`) with the `idna` codec (`idna` 3.20). Apply NFKC. Map confusables (Cyrillic а/е/о/р/с/і, digits 0→o, 1→l, 5→s) and multi-character tricks (`rn`→`m`, `vv`→`w`). Then compare the skeleton to the known vendor domains with Levenshtein distance ≤2, and use `tldextract` 5.4.0 to compare the registrable domain (e.g. `vendor.co.in` against `vendor-co.in`).
  - Also flag **brand-token-contained** domains (`razorpay-payments.com` has distance 9 but contains the token) and TLD swaps (`.com` vs `.in` vs `.co`).
  - For full Unicode TR39 coverage use `confusable-homoglyphs` (3.3.1). `dnstwist` can generate permutations offline.
- Test output: `rnzorpay.com`, `razorpaay.com`, `raz0rpay.com` and `xn--rzorpay-3ya.com` are flagged as lookalikes of `razorpay.com`. `razorpay-payments.com` needs the token rule.
- **RDAP domain age (free, no key) [TESTED today]:**
  - `.com`: `https://rdap.verisign.com/com/v1/domain/<d>`. `https://rdap.org/domain/<d>` also works as a bootstrap redirector (302 to Verisign).
  - `.in` / `.co.in`: `https://rdap.nixiregistry.in/rdap/domain/<d>`. razorpay.in registered 2013-04-02, irctc.co.in 2002-06-04.
  - IANA bootstrap file: `https://data.iana.org/rdap/dns.json` (publication 2026-11-20). It maps `in` to nixiregistry and `com` to Verisign.
  - An unregistered domain returns **404** (`razorpaay.in`, `razorpay-payments.com`, `xn--rzorpay-3ya.com` all 404).
  - **Gotcha:** read `registration` from the **top-level** `events[]` only. Nested entity/nameserver objects carry their own `events` entries, which are only "last update of RDAP database".
  - Policy: sender domain age under 90 days, or a lookalike, means ESCALATE. A bank-change request from such a domain means BLOCK. RDAP timeout or 5xx means `UNKNOWN`, which becomes HOLD and retry, never "ok".
  - Python helper tested: `domain_age_days()` in `scratchpad\r4\snippets_test.py`.
- Email-level signals:
  - Reply-To differs from From.
  - `Authentication-Results` is not `dmarc=pass`.
  - The display name matches the vendor but the domain doesn't.

---

## 4. Human approval UX and audit ledger

### 4.1 Approval queue in Streamlit (fastest)
```python
# app.py  -> streamlit run app.py
import streamlit as st, json
st.set_page_config(layout="wide"); st.title("Sign-Off Gate: approvals")
rows = db.execute("select id, verdict, reasons from invoices where state='ESCALATED' order by updated").fetchall()
for inv_id, verdict, reasons in rows:
    with st.container(border=True):
        st.subheader(inv_id); st.json(json.loads(reasons))            # show evidence + source spans
        who = st.text_input("Approver", key=f"who-{inv_id}")
        c1, c2 = st.columns(2)
        if c1.button("Approve", key=f"a-{inv_id}", disabled=not who):
            n = db.execute("update invoices set state='APPROVED' where id=? and state='ESCALATED'", (inv_id,)).rowcount
            if n: ledger.append("approval", {"invoice": inv_id, "by": who, "decision": "APPROVE"})
            st.rerun()
        if c2.button("Reject", key=f"r-{inv_id}", disabled=not who):
            n = db.execute("update invoices set state='REJECTED' where id=? and state='ESCALATED'", (inv_id,)).rowcount
            if n: ledger.append("approval", {"invoice": inv_id, "by": who, "decision": "REJECT"})
            st.rerun()
```
- Gotchas:
  - Streamlit **reruns the whole script on every click**, so never put side effects at the top level.
  - Use a **conditional UPDATE** (`WHERE state='ESCALATED'`) so a double click or two approvers can't approve twice (rowcount 0 means no-op).
  - The UI only flips state. The **worker** performs the payout from the outbox, so a UI crash can't pay.
  - Use `st.fragment(run_every=5)` or `st_autorefresh` to live-refresh the queue.
  - For bank changes, show old and new IFSC lookups, the penny-drop name match, the domain age and the lookalike result side by side.
- Alternative: FastAPI 0.165 + HTMX (`hx-post="/approve/{id}" hx-swap="outerHTML"`). It suits a team already serving webhooks, and costs about 30 more minutes.

### 4.2 Hash-chained audit ledger [TESTED: tamper detected]
```python
db.execute("create table if not exists ledger(seq integer primary key, ts text, kind text, body text, prev text, hash text)")
db.execute("create trigger if not exists no_upd before update on ledger begin select raise(abort,'append-only'); end")
db.execute("create trigger if not exists no_del before delete on ledger begin select raise(abort,'append-only'); end")
def canon(o): return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
def append(kind, body):                       # call inside the SAME txn as the state change
    seq, prev = db.execute("select coalesce(max(seq),0)+1, coalesce((select hash from ledger order by seq desc limit 1),?) from ledger", ("0"*64,)).fetchone()
    ts = datetime.now(timezone.utc).isoformat()
    h = hashlib.sha256(canon({"seq": seq, "ts": ts, "kind": kind, "body": body, "prev": prev}).encode()).hexdigest()
    db.execute("insert into ledger values(?,?,?,?,?,?)", (seq, ts, kind, canon(body), prev, h)); return h
def verify():                                 # auditor replay
    prev = "0"*64
    for seq, ts, kind, body, p, h in db.execute("select * from ledger order by seq"):
        exp = hashlib.sha256(canon({"seq": seq, "ts": ts, "kind": kind, "body": json.loads(body), "prev": p}).encode()).hexdigest()
        if p != prev or exp != h: return f"BROKEN at seq {seq}"
        prev = h
    return f"OK ({seq} entries, head {prev[:12]})"
```
- Event kinds:
  - `ingest` (file sha256)
  - `claim` (field, value, source span)
  - `check` (source, request hash, result or UNKNOWN, latency, credits)
  - `decision` (verdict, rule ids fired, policy version hash)
  - `approval`
  - `payout_enqueued` (idem key, body sha256)
  - `payout_sent` / `payout_status`
  - `budget_hold`
- Replay = `verify()` plus re-running the deterministic policy over the stored `claim` and `check` events. It must reproduce every `decision`, which proves the policy is deterministic.
- Optionally print the head hash on screen at the end of the demo. Anchor it externally by emailing or committing it.

---

## 5. Policy skeleton (deterministic)
```
BLOCK    : GSTIN checksum fail | hard duplicate | QR signature invalid | QR fields ≠ invoice
           | bank-change email from lookalike/new (<90d) domain | IFSC 404 | amount > hard cap
ESCALATE : any bank-detail change (always) | GST goodservice FO8000 | probable duplicate
           | penny-drop name_match low/invalid | new vendor | amount > soft cap | rate/tax math off
           | any check UNKNOWN after N retries | budget/time ceiling reached
ALLOW    : everything verified, known vendor, known bank account, under soft cap
Timeout handling: check → UNKNOWN → HOLD(retry_at = now + 2^attempt s, max 3) → ESCALATE. Never ALLOW on silence.
```

---

## 6. Verified endpoint table

| Endpoint | Auth | Result today |
|---|---|---|
| `GET https://ifsc.razorpay.com/{IFSC}` | none | 200 JSON; unknown IFSC gives 404 `"Not Found"` |
| `GET https://rdap.verisign.com/com/v1/domain/{d}` | none | 200 with registration date; unregistered gives 404 |
| `GET https://rdap.org/domain/{d}` | none | 302 to the authoritative RDAP server |
| `GET https://rdap.nixiregistry.in/rdap/domain/{d}` (.in, .co.in) | none | 200; unregistered gives 404 |
| `GET https://data.iana.org/rdap/dns.json` | none | 200, bootstrap |
| `GET https://services.gst.gov.in/master/allstates?includeCbic=true` | none | 200 |
| `GET https://services.gst.gov.in/services/api/search/goodservice?gstin=` | cookies + browser UA/Referer, **Python, not curl** | 200 HSN list, or FO8000 "No records found" |
| `POST …/api/search/taxpayerDetails` | captcha | not automated; needs a human captcha |
| `POST https://api.razorpay.com/v1/payouts` | test keys + `X-Payout-Idempotency` | docs verified; needs the team's keys |
| `POST https://api.razorpay.com/v1/fund_accounts/validations` | test keys | docs verified |
| `POST https://api.crustdata.com/web/search/live`, `/web/enrich/live` | Bearer + `x-api-version: 2025-11-01` | 200; `X-Credits-Used: 1` each |

## 7. Library versions (PyPI, checked today)
dbos 3.6.0 · streamlit 1.67.0 · fastapi 0.165.0 · pdfplumber 0.11.11 · pymupdf 2.1 · zxing-cpp 3.1.1 · pyjwt 2.15.1 · cryptography 50.0.2 · langgraph-checkpoint-sqlite 3.1.3 · idna 3.20 · tldextract 5.4.0 · confusable-homoglyphs 3.3.1 · dnstwist 20250130 · whoisit 4.1.0 (RDAP client) · razorpay 2.0.1 (no payouts resource) · rapidfuzz 3.x.

## 8. Sources (read today)
- Razorpay: docs/api/x/payout-idempotency(.md), …/make-request, docs/x/dashboard/test-mode.md, docs/x/dashboard/api-keys.md, docs/x/dashboard/allowlist-ip.md, docs/x/set-up.md, docs/api/x/account-validation/bank-account.md, docs/api/x/account-validation/vpa.md, docs/api/x/payouts/fetch-all.md, docs/api/x/payouts/fetch-with-id.md, docs/errors/x/payout-status-details.md, docs/x/payouts/best-practices.md, docs/api/payments/payment-links/create-standard.md, docs/_llms/india/*.txt, github razorpay/razorpay-python resources listing; Reddit r/Razorpay threads on test mode and KYC (2026).
- Stripe: docs.stripe.com/api/idempotent_requests; docs.stripe.com/india-accept-international-payments; support.stripe.com "Stripe accounts are invite-only in India".
- DBOS: docs.dbos.dev/quickstart; DBOS search results (SQLite default). LangGraph: docs.langchain.com human-in-the-loop / thinking-in-graph-api.
- GST: taxinformation.cbic.gov.in Rule 46; dev.to GSTIN checksum post; github rahulgurujala/gst-validator (README, docs/portal.md, client.py); shubham-dube/GST-Verification-API; einvoice1.gst.gov.in/Others/Publickeys; ClearTax e-invoicing basics (via Crustdata enrich); gstinapi.com e-invoice QR verification.
- RDAP: IANA dns.json, Verisign, NIXI, rdap.org (all live-tested).
- Crustdata: docs.crustdata.com/web-docs/search/introduction; 7 live calls (search ×6, enrich ×1).
