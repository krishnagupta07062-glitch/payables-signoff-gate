"""Streamlit approval queue and decision viewer. OWNER: Ayush.

Run: streamlit run app/approvals.py

Tabs: Inbox (decisions with verdict badges, decision card, Approve/Reject for ESCALATED),
Ledger (events + Verify chain), Payouts (payouts, outbox, refresh, resume).
The UI never pays: Approve records the approval, then app.worker issues a receipt for the executor.
"""
from __future__ import annotations

import html
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:  # .env is optional; python-dotenv is not a dependency
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            if v.strip():
                os.environ.setdefault(k.strip(), v.strip())
except OSError:
    pass

import streamlit as st  # noqa: E402

from app import worker  # noqa: E402
from gate import executor, ledger, store  # noqa: E402
from gate.payments import razorpayx  # noqa: E402

st.set_page_config(page_title="Payables Sign-Off Gate", layout="wide")
store.init_db()

BADGE = {"ALLOW": ("#1a7f37", "ALLOW"), "BLOCK": ("#cf222e", "BLOCK"), "ESCALATE": ("#bf8700", "ESCALATE")}
ICON = {"VERIFIED": "✅", "CONTRADICTED": "❌", "UNVERIFIABLE": "⚠️"}
STATE_NOTE = {"DECIDED": "", "ESCALATED": "waiting for a person", "APPROVED": "approved", "REJECTED": "rejected",
              "PAID": "paid"}


def badge(verdict: str, big: bool = False) -> str:
    color, label = BADGE.get(verdict, ("#57606a", verdict))
    size = "1.4rem" if big else "0.8rem"
    pad = "6px 16px" if big else "2px 8px"
    return (f"<span style='background:{color};color:#fff;border-radius:6px;padding:{pad};"
            f"font-weight:700;font-size:{size}'>{html.escape(label)}</span>")


def link(ref: str) -> str:
    ref = ref or ""
    if ref.startswith(("http://", "https://")):
        return f"<a href='{html.escape(ref, quote=True)}' target='_blank' rel='noopener'>{html.escape(ref)}</a>"
    return f"<code>{html.escape(ref)}</code>"


# ------------------------------------------------------------------------------------- sidebar

with st.sidebar:
    st.header("Sign-Off Gate")
    approver = st.text_input("Signed in as (approver)", value=st.session_state.get("approver", "finance.controller"))
    st.session_state["approver"] = approver
    st.caption(f"Payments: **{razorpayx.mode()}** · DB: `{Path(store.db_path()).name}`")
    st.subheader("Run credits")
    credits = store.credits_summary()
    if credits:
        total = sum((c["credits"] or 0) for c in credits)
        st.metric("Credits spent (all runs)", f"{total:.2f}")
        st.dataframe(credits, hide_index=True, use_container_width=True)
    else:
        st.caption("No external calls recorded yet.")
    v = ledger.verify()
    st.caption(("🔒 Ledger chain OK" if v["ok"] else f"🚨 Ledger broken at row {v['first_bad_row']}")
               + f" · {v['rows']} rows")
    with st.expander("Developer"):
        if st.button("Seed demo decisions"):
            from app import dev_seed
            st.success(f"Seeded: {dev_seed.seed() or 'already present'}")
            st.rerun()

tab_run, tab_inbox, tab_ledger, tab_payouts = st.tabs(["Run a request", "Inbox", "Ledger", "Payouts"])


# --------------------------------------------------------------------------------------- inbox

def decision_card(request_id: str, where: str = "inbox") -> None:
    row = store.get_decision_row(request_id)
    if not row:
        st.warning("Decision not found.")
        return
    d = json.loads(row["decision"])
    req = store.get_request_row(request_id) or {}
    vendor = store.get_vendor(row["vendor_id"]) if row["vendor_id"] else None

    st.markdown(f"{badge(d['verdict'], big=True)} &nbsp; <b>{html.escape(request_id)}</b> &nbsp; "
                f"<span style='color:#57606a'>{html.escape(STATE_NOTE.get(row['state'], row['state']))}</span>",
                unsafe_allow_html=True)
    meta = [f"**Kind:** {req.get('kind', '?')}", f"**From:** {req.get('sender') or '?'}",
            f"**Vendor:** {vendor.legal_name if vendor else row['vendor_id'] or 'unknown'}",
            f"**Policy:** {d.get('policy_version')}", f"**Decided:** {d.get('decided_at')}"]
    st.markdown(" · ".join(meta))

    st.markdown("#### Why")
    for r in d.get("reasons", []):
        checks = ", ".join(r.get("check_names") or []) or "—"
        st.markdown(f"<div style='margin:4px 0'><b>{html.escape(r['rule_id'])}</b> {html.escape(r['text'])}"
                    f" <span style='color:#57606a'>(checks: {html.escape(checks)})</span></div>",
                    unsafe_allow_html=True)

    st.markdown("#### Checks")
    for c in d.get("checks", []):
        srcs = "<br>".join(
            f"{html.escape(s.get('kind') or '')}: {link(s.get('ref'))}"
            + (f" · req <code>{html.escape(s['request_id'])}</code>" if s.get("request_id") else "")
            + (f" · record <code>{html.escape(str(s['record_id']))}</code>" if s.get("record_id") else "")
            + (f" · dated {html.escape(s['record_date'])}" if s.get("record_date") else "")
            + (f" · retrieved {html.escape(s['retrieved_at'])}" if s.get("retrieved_at") else "")
            + (f"<br><i>“{html.escape(s['excerpt'])}”</i>" if s.get("excerpt") else "")
            for s in c.get("sources", [])) or "<span style='color:#cf222e'>no source</span>"
        value = html.escape(json.dumps(c.get("value") or {}, ensure_ascii=False))
        note = f"<br><span style='color:#57606a'>{html.escape(c['note'])}</span>" if c.get("note") else ""
        st.markdown(
            f"<div style='border:1px solid #d0d7de;border-radius:6px;padding:8px;margin:6px 0'>"
            f"{ICON.get(c['status'], '•')} <b>{html.escape(c['name'])}</b> "
            f"<code>{html.escape(c['status'])}</code> <span style='font-size:0.85em'>{value}</span>{note}"
            f"<div style='font-size:0.85em;margin-top:4px'>{srcs}</div></div>", unsafe_allow_html=True)

    claims = d.get("claims") or {}
    action = d.get("action") or {}
    new_last4 = claims.get("pay_to_account_last4") or action.get("account_last4")
    if new_last4 or claims.get("requested_change") == "bank_change":
        st.markdown("#### Bank account")
        old_col, new_col = st.columns(2)
        with old_col:
            st.markdown("**On the vendor master (trusted)**")
            for a in (vendor.bank_accounts if vendor else []):
                st.markdown(f"`{a.ifsc}` · ••••{a.account_last4} · {a.holder_name}"
                            f"<br><span style='color:#57606a;font-size:0.85em'>added {a.added_at or '?'}, "
                            f"verified {a.verified_at or 'never'}</span>", unsafe_allow_html=True)
            if not vendor or not vendor.bank_accounts:
                st.caption("No account on file.")
        with new_col:
            st.markdown("**Claimed in this request (untrusted)**")
            on_file = vendor and any(a.account_last4 == new_last4 and
                                     a.account_hash in (claims.get("pay_to_account_hash"), action.get("account_hash"))
                                     for a in vendor.bank_accounts)
            st.markdown(f"`{claims.get('pay_to_ifsc') or action.get('ifsc') or '?'}` · ••••{new_last4 or '?'} · "
                        f"{claims.get('pay_to_holder') or ''} {'(on file)' if on_file else '**(NEW)**'}")

    if action:
        st.markdown(f"#### Payment\n₹{action['amount_paise'] / 100:,.2f} to ••••{action['account_last4']} "
                    f"(`{action['ifsc']}`) · invoice `{action['invoice_key']}` · key `{action['idempotency_key']}`")
    if claims.get("urgency_cues"):
        st.caption("Urgency cues (logged only, never relax a rule): " + ", ".join(claims["urgency_cues"]))
    for a in store.approvals_for(request_id):
        st.info(f"{'Approved' if a['approve'] else 'Rejected'} by {a['approver']} at {a['at']}"
                + (f": {a['note']}" if a["note"] else ""))

    if row["state"] == store.ESCALATED:
        note = st.text_input("Note (e.g. call-back done on the number on file)", key=f"{where}-note-{request_id}")
        a_col, r_col, _ = st.columns([1, 1, 4])
        if a_col.button("✅ Approve", key=f"{where}-approve-{request_id}", type="primary"):
            if store.record_approval(request_id, approver, True, note):
                res = worker.pay_approved(request_id, approver)
                st.session_state["flash"] = f"Approved. Payment: {res}"
            else:
                st.session_state["flash"] = "Already decided (double click ignored)."
            st.rerun()
        if r_col.button("❌ Reject", key=f"{where}-reject-{request_id}"):
            ok = store.record_approval(request_id, approver, False, note)
            st.session_state["flash"] = "Rejected." if ok else "Already decided (double click ignored)."
            st.rerun()
    elif row["state"] == store.APPROVED and action:
        if st.button("Retry payment", key=f"{where}-retry-{request_id}"):
            st.session_state["flash"] = f"Payment: {worker.pay_approved(request_id, approver)}"
            st.rerun()


with tab_inbox:
    if st.session_state.get("flash"):
        st.success(st.session_state.pop("flash"))
    decisions = store.list_decisions()
    if not decisions:
        st.info("No decisions yet. Run the pipeline, or use Developer → Seed demo decisions in the sidebar.")
    else:
        pending = [d for d in decisions if d["state"] == store.ESCALATED]
        st.caption(f"{len(decisions)} decisions · {len(pending)} waiting for a person")
        left, right = st.columns([2, 5])
        with left:
            filt = st.radio("Show", ["All", "Waiting for a person", "ALLOW", "BLOCK", "ESCALATE"], horizontal=False)
            shown = [d for d in decisions if filt == "All" or (filt == "Waiting for a person" and d["state"] == store.ESCALATED)
                     or d["verdict"] == filt]
            for d in shown:
                label = f"{d['verdict']} · {d['request_id']}"
                sub = f"{d.get('kind') or ''} · {', '.join(d['rule_ids'])} · {STATE_NOTE.get(d['state'], d['state'])}"
                if st.button(label, key=f"pick-{d['request_id']}", help=sub, use_container_width=True):
                    st.session_state["selected"] = d["request_id"]
                st.markdown(f"<div style='margin:-8px 0 8px 4px;font-size:0.8em'>{badge(d['verdict'])} "
                            f"{html.escape(sub)}</div>", unsafe_allow_html=True)
        with right:
            sel = st.session_state.get("selected") or (pending[0]["request_id"] if pending else decisions[0]["request_id"])
            decision_card(sel)


# -------------------------------------------------------------------------------- run a request

def _case_files() -> list[Path]:
    try:
        from gate import pipeline
        return pipeline.all_case_files()
    except Exception:  # pipeline missing or broken: show nothing rather than crash the UI
        return []


def _load_vendor_master() -> None:
    for p in (ROOT / "fixtures" / "vendors.json", ROOT / "fixtures" / "private" / "vendors.json"):
        if p.exists():
            store.load_fixtures(str(p))


with tab_run:
    files = _case_files()
    if not files:
        st.info("No request fixtures found (fixtures/requests/), or the pipeline is not importable.")
    else:
        labels = {f"{'🔒 ' if 'private' in f.parts else ''}{f.stem}": f for f in files}
        c1, c2 = st.columns([3, 2])
        choice = c1.selectbox("Request", list(labels))
        case = json.loads(labels[choice].read_text(encoding="utf-8"))
        c1.caption(f"Case {case.get('case')}: {case.get('title', '')} · expected **{case.get('expected_verdict')}** "
                   f"{case.get('expected_rules', '')}")
        credits_cap = c2.number_input("Run credit ceiling", min_value=0.0, max_value=100.0, value=10.0, step=1.0)
        crash = c2.toggle("Simulate crash mid-payout", help="Pays in a child process that dies right after the "
                          "outbox 'unknown' write. Then press Resume to finish it exactly once.")
        with st.expander("Raw request (untrusted)"):
            req = case.get("request", {})
            st.text(f"From: {req.get('sender_display') or ''} <{req.get('sender_email') or ''}>")
            st.text(req.get("raw_text", ""))
        if st.button("▶ Run the gate", type="primary"):
            from gate import pipeline
            from gate.runbudget import RunBudget
            _load_vendor_master()
            budget = RunBudget(max_credits=credits_cap)
            with st.spinner("extract → verify → decide…"):
                _, res = pipeline.run_case(labels[choice], budget, execute=not crash)
            store.record_calls(budget)
            st.session_state["last_run"] = {"request_id": res.decision.request_id, "trace": res.trace,
                                            "payout": res.payout, "budget": res.budget,
                                            "expected": case.get("expected_verdict")}
            if crash and res.decision.verdict.value == "ALLOW" and res.decision.action:
                st.session_state["last_run"]["crash"] = worker.pay_with_crash(res.decision.request_id)
            st.session_state["selected"] = res.decision.request_id
        last = st.session_state.get("last_run")
        if last:
            row = store.get_decision_row(last["request_id"])
            got = row["verdict"] if row else "?"
            st.markdown(f"Expected **{last['expected']}**, gate says {badge(got)} "
                        f"{'✔' if got == last['expected'] else '✘ mismatch'} · credits {last['budget'].get('credits')}"
                        f" · {last['budget'].get('calls')} calls ({last['budget'].get('cached_calls')} cached) · "
                        f"{last['budget'].get('seconds')}s", unsafe_allow_html=True)
            with st.expander("Trace", expanded=False):
                for t in last["trace"]:
                    st.text(t)
            if last.get("payout"):
                p = last["payout"]
                st.success(f"Payout {p.get('payout_id')} · {p.get('status')}"
                           + (" · replayed, not paid twice" if p.get("replayed") else ""))
            if last.get("crash"):
                cr = last["crash"]
                st.error(f"💥 Payer crashed (exit {cr['returncode']}). Outbox row is **{cr['outbox_state']}**: "
                         f"the intent is saved and the provider may or may not have the payout.")
                if st.button("♻ Resume", type="primary"):
                    out = executor.resume()
                    n = len([p for p in store.list_payouts() if p["idempotency_key"] == cr["idempotency_key"]])
                    last["crash"] = None
                    st.session_state["flash_run"] = f"Resumed: {out or 'nothing pending'} · payouts for this invoice: {n}"
                    st.rerun()
            if st.session_state.get("flash_run"):
                st.success(st.session_state.pop("flash_run"))
            st.divider()
            decision_card(last["request_id"], where="run")


# -------------------------------------------------------------------------------------- ledger

with tab_ledger:
    c1, c2 = st.columns([1, 4])
    if c1.button("Verify chain", type="primary"):
        res = ledger.verify()
        if res["ok"]:
            c2.success(f"Chain intact: {res['rows']} rows replayed, head {res.get('head', '')[:16]}…")
        else:
            c2.error(f"Chain broken at row {res['first_bad_row']}: {res['reason']}")
    evts = ledger.events(limit=300)
    st.dataframe([{"id": e["id"], "at": e["at"], "event": e["event_type"], "hash": e["hash"][:16] + "…",
                   "prev": e["prev_hash"][:16] + "…", "payload": json.dumps(e["payload"], ensure_ascii=False)[:200]}
                  for e in evts], hide_index=True, use_container_width=True)


# ------------------------------------------------------------------------------------- payouts

with tab_payouts:
    b1, b2, _ = st.columns([1, 1, 4])
    if b1.button("Refresh status"):
        st.session_state["pflash"] = f"Status changes: {executor.refresh_payouts() or 'none'}"
    if b2.button("Resume unfinished"):
        st.session_state["pflash"] = f"Resumed: {executor.resume() or 'nothing to resume'}"
    if st.session_state.get("pflash"):
        st.info(st.session_state.pop("pflash"))
    if razorpayx.mode() == "test":
        st.caption("RazorpayX test mode: payouts stay 'processing' until moved in the dashboard.")
    st.markdown("#### Payouts")
    st.dataframe(store.list_payouts(), hide_index=True, use_container_width=True)
    st.markdown("#### Outbox")
    st.dataframe([{k: v for k, v in o.items() if k != "body"} for o in store.list_outbox()],
                 hide_index=True, use_container_width=True)
    if razorpayx.mode() == "mock":
        st.markdown("#### Provider view (mock): one row per real payout")
        st.dataframe(razorpayx.mock_payouts(), hide_index=True, use_container_width=True)
