# Demo script: 2 minutes

*Owner: Ayush. Recorded from the **Demo** tab of `app/approvals.py`. Every step runs the real pipeline, store, executor and ledger. Payouts go to RazorpayX test mode when `PAYMENTS_MODE=test`, otherwise to the mock provider (same idempotency rules).*

## Before recording (5 minutes)

```bash
cd payables-signoff-gate
MOCK=1 .venv/bin/streamlit run app/approvals.py      # MOCK=1: stored claims and checks, no credits, no flakiness
```

1. Sidebar: set "Signed in as" to `finance.controller`.
2. Demo tab: click **⟲ Start fresh demo** (new empty database, vendor master loaded).
3. Browser zoom at 125%, window ~1400 px wide, notifications off.
4. Leave `ACCOUNT_HASH_KEY` empty in `.env` for the synthetic demo. The committed fixtures were hashed with the default key.
5. If showing RazorpayX: have the dashboard open in a second tab on **Payouts** (test mode).

## The script

**0:00–0:15 · The customer, in their own words** *(Demo tab header on screen)*

> "Every week we pay a few hundred vendor invoices. Two things keep me up at night: paying the same invoice twice, and a polite email that says *'we've changed banks, please update our account'* and turns out to be a fraudster. My team can't call every vendor back, and I can't have a bot that a pushy email can talk into paying."
> (Finance controller, mid-size exporter)

Say: "We replace the outsourced payables desk with a gate. A model only *reads* the email. Live records *check* every claim. Plain code *decides*: allow, block or escalate to a person."

**0:15–0:40 · 1. Bank-change fraud → BLOCK** *(click ▶ Run on step 1)*

- On screen: a big red **BLOCK** with **B2**, and the contradicting checks with their sources.
- Say: "This email names the vendor's real CFO and asks us to move their payments to a new account. The gate doesn't care how convincing it sounds. The sender's domain `acmeleathers.in` is one letter off the vendor's real `acmeleather.in`, and RDAP says it was registered four days ago. Blocked, and here's the record that says so."

**0:40–1:05 · 2 and 3. A genuine bank change → ESCALATE → a person approves → paid once** *(▶ Run step 2, ✅ Approve; ▶ Run step 3, ✅ Approve)*

- Step 2, amber **ESCALATE E1**. Say: "Same request from the real domain, signed by someone who works there *today*. Every check passes, but a bank change can't be undone, so a person approves it after calling back on the number we already had on file."
- Step 3, **ESCALATE E2** (cooling-off on the first payment to a new account) → Approve → the green "payout pout_…" line.
- Say: "Only after a person signs off does the executor accept a receipt bound to the hash of *this exact payment*. Change one rupee and it refuses."

**1:05–1:35 · 4. Crash mid-payout → Resume → exactly one payout** *(▶ Run + crash on step 4, then ♻ Resume)*

- On screen: "💥 Payer killed… Outbox row **unknown**".
- Say: "We kill the payer at the worst moment: after it decided to pay, before we know if the bank got it. Did the money go?" Click **Resume**.
- On screen: "payouts for this invoice: **1**".
- Say: "The intent was saved before the call, and the payment key comes from the invoice itself, not the attempt. Resume sends the same bytes with the same key, and the provider dedupes it. One payout."

**1:35–1:50 · 5. The same invoice re-sent → BLOCK** *(▶ Run step 5)*

- Big red **BLOCK B1**, "Payouts for invoice 2026-27-42: **1**".
- Say: "The vendor re-sends it as `2026-27-42` instead of `INV/2026-27/0042`. We normalise the number per CGST Rule 46, find it already paid, and block it."

**1:50–2:00 · Close** *(switch to the Ledger tab, click **Verify chain**)*

- Say: "Every step is in a hash-chained ledger an auditor can replay. Chain intact. Pressure works on any model that has to judge a claim it can't check, so our gate never asks it to."

## Backup lines (if asked, or if a step misbehaves)

- **"What if Crustdata times out?"** Then the check is UNVERIFIABLE, which escalates (case 9); it never passes.
- **"Can the model be prompt-injected?"** Hidden HTML is stripped (case 7), and the decider never sees the email text, only typed fields.
- **"Is the payout real?"** It's RazorpayX test mode. Payouts stay `processing` until moved in the dashboard; the Payouts tab shows that honestly. Live check done at 14:40: the same key resent returned the same payout, and the same key with a changed amount was rejected by Razorpay.
- **A step shows the wrong verdict:** click **⟲ Start fresh demo** and run the steps in order (step 3 needs step 2's approval; step 5 needs step 4's payout).
- **Export:** every card has **⬇ Export decision report**, a Markdown file with every claim, check, status, source, rule, approval, payout and ledger row.
