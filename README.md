# Payables Sign-Off Gate

Built at **ContextCon 05, BITS Pilani** (22 Nov 2026), on the themes *6.1 The Payables Desk* and *10.2 The Sign-Off Gate*.

An accounts-payable agent that pays each vendor invoice exactly once, and a gate in front of every irreversible action (paying, changing a vendor's bank details) that answers **ALLOW**, **BLOCK** or **ESCALATE**, with a source for every reason.

> Status: research and design in progress. This README will grow as the build does.

## The problem

The costliest payables fraud is a polite email asking to change a vendor's bank details. Duplicates also slip through in new formats. Outsourced accounting firms are paid today to stand between an invoice and the company's bank account.

## How the gate decides

1. **Extract.** A language model reads the email or invoice and names the claims in it: who is asking, for which vendor, which change, which amounts.
2. **Verify, with live data.** Each claim is checked against records, and each fact keeps its source and date:
   - Crustdata company identify and enrich: is the vendor real and active, and is the sender's domain its real domain?
   - Crustdata person search and enrich: does the named person work at the vendor today, in the claimed role?
   - Live web search: recent news of the vendor, such as an acquisition or a rebrand.
3. **Decide, in code.** A written payment policy is applied by plain code, not by the model, so pressure, urgency and politeness never change the answer.
4. **Escalate the exceptions.** A fact that can't be verified, or a disagreement between checks, goes to a person with the reason. Anything that can't be undone waits for approval.
5. **Pay once.** Payments run in a payment provider's test mode with idempotency keys and a crash-safe run log, so a restart never pays twice.

## Prior work, declared

The extract-then-code gate design comes from the team's earlier research project, *Gatekeeper*: measuring tone-driven errors in small policy guards. No code from it is copied here. Everything in this repo was written during the event, from 10:15 AM on 22 Nov 2026.

## Setup

```bash
cp .env.example .env   # add your Crustdata API key
python crustdata.py    # prints your credit balance and enabled endpoints
```

## Repo layout

- `crustdata.py`: a minimal Crustdata API client (API version 2025-11-01).
- `docs/research/`: the research behind the design.
