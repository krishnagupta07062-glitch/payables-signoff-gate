"""Decision report export (Markdown). OWNER: Ayush.

decision_report_md(request_id) -> a self-contained Markdown report an auditor can read without the
app: every claim, every check with its status, value, note and sources, every rule fired, the payment
action and its hash, approvals, payouts, and the ledger rows for this request with the chain status.
Account numbers appear as last 4 only; raw email text is never included (only its SHA-256).
"""
from __future__ import annotations

import json

from gate import ledger, store
from gate.contracts import now_iso

ICON = {"VERIFIED": "✅", "CONTRADICTED": "❌", "UNVERIFIABLE": "⚠️"}


def _cell(v) -> str:
    if v is None or v == "" or v == [] or v == {}:
        return "—"
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return s.replace("|", "\\|").replace("\n", " ")


def decision_report_md(request_id: str) -> str:
    row = store.get_decision_row(request_id)
    if not row:
        return f"# Decision report\n\nNo decision found for `{request_id}`.\n"
    d = json.loads(row["decision"])
    req = store.get_request_row(request_id) or {}
    vendor = store.get_vendor(row["vendor_id"]) if row["vendor_id"] else None
    out: list[str] = []
    w = out.append

    w(f"# Decision report: {request_id}")
    w("")
    w(f"**Verdict: {d['verdict']}** · rules {', '.join(d.get('rule_ids') or []) or '—'} · state {row['state']} · "
      f"policy `{d.get('policy_version')}` · decided {d.get('decided_at')}")
    w("")
    w(f"*Generated {now_iso()} by the Payables Sign-Off Gate.*")
    w("")

    w("## Request")
    w("")
    w("| Field | Value |")
    w("|---|---|")
    for k, label in (("kind", "Kind"), ("sender", "Sender"), ("sender_display", "Display name"),
                     ("reply_to", "Reply-to"), ("received_at", "Received"), ("raw_text_hash", "Raw text SHA-256")):
        w(f"| {label} | {_cell(req.get(k))} |")
    w(f"| Vendor | {_cell(f'{vendor.legal_name} ({vendor.vendor_id})' if vendor else row['vendor_id'])} |")
    if req.get("po"):
        w(f"| Purchase order (buyer's system) | {_cell(json.loads(req['po']))} |")
    w("")
    w("The raw email is untrusted and is not reproduced; only its hash is kept.")
    w("")

    w("## Rules fired")
    w("")
    for r in d.get("reasons") or []:
        checks = ", ".join(f"`{c}`" for c in r.get("check_names") or [])
        w(f"- **{r['rule_id']}**: {r['text']}" + (f" (checks: {checks})" if checks else ""))
    if not d.get("reasons"):
        w("- none")
    w("")

    claims = d.get("claims") or {}
    w("## Claims extracted from the request (untrusted)")
    w("")
    w("| Claim | Value |")
    w("|---|---|")
    shown = False
    for k, v in claims.items():
        if k in ("pay_to_account", "pay_to_account_hash") or v in (None, "", [], "none"):
            continue
        if k == "pay_to_account_last4":
            k, v = "pay_to_account", f"••••{v}"
        w(f"| {k} | {_cell(v)} |")
        shown = True
    if not shown:
        w("| — | — |")
    if claims.get("urgency_cues"):
        w("")
        w("Urgency cues are logged only; they never relax a rule.")
    w("")

    w("## Checks")
    w("")
    w("| Check | Status | Value | Note | Sources |")
    w("|---|---|---|---|---|")
    for c in d.get("checks") or []:
        srcs = []
        for s in c.get("sources") or []:
            bits = [f"{s.get('kind')}: {s.get('ref')}"]
            for key, label in (("request_id", "req"), ("record_id", "record"), ("record_date", "dated"),
                               ("retrieved_at", "retrieved")):
                if s.get(key):
                    bits.append(f"{label} {s[key]}")
            if s.get("excerpt"):
                bits.append(f"“{s['excerpt']}”")
            srcs.append(" · ".join(bits))
        w(f"| `{c['name']}` | {ICON.get(c['status'], '')} {c['status']} | {_cell(c.get('value'))} | "
          f"{_cell(c.get('note'))} | {_cell('<br>'.join(srcs)) if srcs else '**no source**'} |")
    w("")

    a = d.get("action")
    w("## Payment action")
    w("")
    if a:
        w(f"- Amount: ₹{a['amount_paise'] / 100:,.2f} ({a['amount_paise']} paise)")
        w(f"- To: ••••{a['account_last4']} at `{a['ifsc']}` (account hash `{a['account_hash'][:16]}…`)")
        w(f"- Invoice key: `{a['invoice_key']}`")
        w(f"- Idempotency key: `{a['idempotency_key']}`")
        w(f"- Action hash: `{d.get('action_hash')}`")
    else:
        w("No payment for this request.")
    w("")

    if vendor and (claims.get("pay_to_account_last4") or claims.get("requested_change") == "bank_change"):
        w("## Bank accounts")
        w("")
        w("| | IFSC | Account | Holder | Added | Verified |")
        w("|---|---|---|---|---|---|")
        for acct in vendor.bank_accounts:
            w(f"| Vendor master | {acct.ifsc} | ••••{acct.account_last4} | {_cell(acct.holder_name)} | "
              f"{_cell(acct.added_at)} | {_cell(acct.verified_at)} |")
        w(f"| Claimed in request | {_cell(claims.get('pay_to_ifsc'))} | ••••{claims.get('pay_to_account_last4') or '?'} | "
          f"{_cell(claims.get('pay_to_holder'))} | — | — |")
        w("")

    approvals = store.approvals_for(request_id)
    w("## Approvals")
    w("")
    for ap in approvals:
        w(f"- {'Approved' if ap['approve'] else 'Rejected'} by **{ap['approver']}** at {ap['at']}"
          + (f": {ap['note']}" if ap["note"] else ""))
    if not approvals:
        w("- none" + (" (waiting for a person)" if row["state"] == store.ESCALATED else ""))
    w("")

    pays = [p for p in store.list_payouts() if p["request_id"] == request_id
            or (a and p["idempotency_key"] == a["idempotency_key"])]
    w("## Payouts")
    w("")
    for p in pays:
        w(f"- `{p['payout_id']}` · {p['status']} · ₹{(p['amount_paise'] or 0) / 100:,.2f} · {p['mode']} · "
          f"key `{p['idempotency_key']}` · outbox {p.get('outbox_state')} after {p.get('attempts')} attempt(s)")
    if not pays:
        w("- none")
    w("")

    evts = [e for e in reversed(ledger.events(limit=5000))
            if isinstance(e["payload"], dict) and (e["payload"].get("request_id") == request_id
                                                   or (a and e["payload"].get("idempotency_key") == a["idempotency_key"]))]
    v = ledger.verify()
    w("## Audit ledger")
    w("")
    w(f"Chain: **{'intact' if v['ok'] else 'BROKEN at row ' + str(v['first_bad_row'])}** "
      f"({v['rows']} rows replayed). Rows for this request:")
    w("")
    w("| Row | At | Event | Hash |")
    w("|---|---|---|---|")
    for e in evts:
        w(f"| {e['id']} | {e['at']} | {e['event_type']} | `{e['hash'][:16]}…` |")
    w("")
    return "\n".join(out)
