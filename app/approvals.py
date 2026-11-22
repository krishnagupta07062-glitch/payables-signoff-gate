"""Streamlit approval queue and decision viewer.

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

from app import demo, hero, report, theme, worker  # noqa: E402
from gate import executor, ledger, store  # noqa: E402
from gate.payments import razorpayx  # noqa: E402

st.set_page_config(page_title="Payables Sign-Off Gate", layout="wide")
theme.inject()
store.init_db()

STATE_NOTE = {"DECIDED": "", "ESCALATED": "waiting for a person", "APPROVED": "approved", "REJECTED": "rejected",
              "PAID": "paid"}


def badge(verdict: str, big: bool = False) -> str:
    return theme.badge(verdict, "md" if big else "sm")


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
        st.dataframe(credits, hide_index=True, width="stretch")
    else:
        st.caption("No external calls recorded yet.")
    v = ledger.verify()
    st.markdown(f"<div class='sg-muted' style='font-size:.92rem'>"
                f"{theme.status_dot('VERIFIED' if v['ok'] else 'CONTRADICTED')} &nbsp;"
                + html.escape("Ledger chain OK" if v["ok"] else f"Ledger broken at row {v['first_bad_row']}")
                + f" · <span class='sg-mono'>{v['rows']}</span> rows</div>", unsafe_allow_html=True)
    with st.expander("Developer"):
        if st.button("Seed demo decisions"):
            from app import dev_seed
            st.success(f"Seeded: {dev_seed.seed() or 'already present'}")
            st.rerun()

# ----------------------------------------------------------------------------- humans / agents switch

if "view" not in st.session_state:  # ?view=agents opens the agent view directly
    st.session_state["view"] = "Agents" if str(st.query_params.get("view", "")).lower() == "agents" else "Humans"
_, switch_col = st.columns([5, 2])
view = switch_col.segmented_control("View", ["Humans", "Agents"], key="view", label_visibility="collapsed",
                                    width="stretch") or "Humans"
st.query_params["view"] = view.lower()
if view == "Agents":
    from app import agent_view
    agent_view.render()
    st.stop()

tab_demo, tab_run, tab_inbox, tab_ledger, tab_payouts = st.tabs(["Demo", "Run a request", "Inbox", "Ledger", "Payouts"])


# --------------------------------------------------------------------------------------- inbox

def decision_card(request_id: str, where: str = "inbox") -> None:
    row = store.get_decision_row(request_id)
    if not row:
        st.warning("Decision not found.")
        return
    d = json.loads(row["decision"])
    req = store.get_request_row(request_id) or {}
    vendor = store.get_vendor(row["vendor_id"]) if row["vendor_id"] else None

    st.markdown(f"<div class='sg-head'>{badge(d['verdict'], big=True)}"
                f"<span class='sg-id'>{html.escape(request_id)}</span>"
                f"{theme.state_note(STATE_NOTE.get(row['state'], row['state']), row['state'] == store.ESCALATED)}"
                f"</div>", unsafe_allow_html=True)
    meta = [("Kind", req.get('kind', '?')), ("From", req.get('sender') or '?'),
            ("Vendor", vendor.legal_name if vendor else row['vendor_id'] or 'unknown'),
            ("Policy", d.get('policy_version')), ("Decided", d.get('decided_at'))]
    st.markdown("<div style='font-size:.95rem;line-height:1.9'>" + " &nbsp;·&nbsp; ".join(
        f"<span class='sg-muted'>{k}:</span> {html.escape(str(v))}" for k, v in meta) + "</div>",
        unsafe_allow_html=True)

    st.markdown("#### Why")
    for r in d.get("reasons", []):
        checks = ", ".join(r.get("check_names") or []) or "—"
        st.markdown(f"<div class='sg-reason'><span class='sg-rule'>{html.escape(r['rule_id'])}</span>"
                    f"<span>{html.escape(r['text'])} <span class='sg-muted' style='font-size:.85em'>"
                    f"(checks: {html.escape(checks)})</span></span></div>", unsafe_allow_html=True)

    st.markdown("#### Checks")
    for c in d.get("checks", []):
        srcs = "<br>".join(
            f"{html.escape(s.get('kind') or '')}: {link(s.get('ref'))}"
            + (f" · req <code>{html.escape(s['request_id'])}</code>" if s.get("request_id") else "")
            + (f" · record <code>{html.escape(str(s['record_id']))}</code>" if s.get("record_id") else "")
            + (f" · dated {html.escape(s['record_date'])}" if s.get("record_date") else "")
            + (f" · retrieved {html.escape(s['retrieved_at'])}" if s.get("retrieved_at") else "")
            + (f"<br><i>“{html.escape(s['excerpt'])}”</i>" if s.get("excerpt") else "")
            for s in c.get("sources", [])) or "<span style='color:var(--bad)'>no source</span>"
        value = html.escape(json.dumps(c.get("value") or {}, ensure_ascii=False))
        note = f"<br><span class='sg-muted'>{html.escape(c['note'])}</span>" if c.get("note") else ""
        st.markdown(
            f"<div class='sg-check' style='--c:{theme.STATUS.get(c['status'], theme.MUTED)}'>"
            f"{theme.status_dot(c['status'])} <b>{html.escape(c['name'])}</b>"
            f"<span class='sg-status'>{html.escape(c['status'])}</span> "
            f"<span class='sg-mono sg-muted' style='font-size:0.8em'>{value}</span>{note}"
            f"<div class='sg-src'>{srcs}</div></div>", unsafe_allow_html=True)

    claims = d.get("claims") or {}
    action = d.get("action") or {}
    new_last4 = claims.get("pay_to_account_last4") or action.get("account_last4")
    if new_last4 or claims.get("requested_change") == "bank_change":
        st.markdown("#### Bank account")
        old_col, new_col = st.columns(2)
        with old_col:
            rows = "".join(
                f"<div style='margin:.2rem 0'><span class='sg-mono'>{html.escape(a.ifsc)} · ••••"
                f"{html.escape(a.account_last4)}</span> · {html.escape(a.holder_name or '')}"
                f"<br><span class='sg-muted' style='font-size:0.9em'>added {html.escape(str(a.added_at or '?'))}, "
                f"verified {html.escape(str(a.verified_at or 'never'))}</span></div>"
                for a in (vendor.bank_accounts if vendor else []))
            if not vendor or not vendor.bank_accounts:
                rows = "<span class='sg-muted'>No account on file.</span>"
            st.markdown(f"<div class='sg-acct trusted'><div class='sg-label'>On the vendor master (trusted)</div>"
                        f"{rows}</div>", unsafe_allow_html=True)
        with new_col:
            on_file = vendor and any(a.account_last4 == new_last4 and
                                     a.account_hash in (claims.get("pay_to_account_hash"), action.get("account_hash"))
                                     for a in vendor.bank_accounts)
            tag = "<span class='sg-onfile'>(on file)</span>" if on_file else "<span class='sg-new'>(NEW)</span>"
            st.markdown(f"<div class='sg-acct claimed'><div class='sg-label'>Claimed in this request (untrusted)</div>"
                        f"<div style='margin:.2rem 0'><span class='sg-mono'>"
                        f"{html.escape(claims.get('pay_to_ifsc') or action.get('ifsc') or '?')} · ••••"
                        f"{html.escape(new_last4 or '?')}</span> · {html.escape(claims.get('pay_to_holder') or '')} "
                        f"{tag}</div></div>", unsafe_allow_html=True)

    if action:
        st.markdown("#### Payment")
        st.markdown(f"<div class='sg-amount'>₹{action['amount_paise'] / 100:,.2f} "
                    f"<span class='sg-muted' style='font-size:.55em'>to ••••{html.escape(action['account_last4'])} "
                    f"(<code>{html.escape(action['ifsc'])}</code>)</span></div>"
                    f"<div class='sg-muted' style='font-size:.9rem'>invoice <code>{html.escape(action['invoice_key'])}"
                    f"</code> · key <code>{html.escape(action['idempotency_key'])}</code></div>",
                    unsafe_allow_html=True)
    if claims.get("urgency_cues"):
        st.caption("Urgency cues (logged only, never relax a rule): " + ", ".join(claims["urgency_cues"]))
    st.download_button("Export decision report (Markdown)", data=report.decision_report_md(request_id),
                       file_name=f"decision-{request_id}.md", mime="text/markdown", key=f"{where}-export-{request_id}",
                       icon=":material/download:")
    for a in store.approvals_for(request_id):
        st.info(f"{'Approved' if a['approve'] else 'Rejected'} by {a['approver']} at {a['at']}"
                + (f": {a['note']}" if a["note"] else ""))

    if row["state"] == store.ESCALATED:
        note = st.text_input("Note (e.g. call-back done on the number on file)", key=f"{where}-note-{request_id}")
        a_col, r_col, _ = st.columns([1, 1, 4])
        if a_col.button("Approve", key=f"{where}-approve-{request_id}", type="primary", icon=":material/check:",
                        width="stretch"):
            if store.record_approval(request_id, approver, True, note):
                res = worker.pay_approved(request_id, approver)
                st.session_state["flash"] = f"Approved. Payment: {res}"
            else:
                st.session_state["flash"] = "Already decided (double click ignored)."
            st.rerun()
        if r_col.button("Reject", key=f"{where}-reject-{request_id}", icon=":material/close:", width="stretch"):
            ok = store.record_approval(request_id, approver, False, note)
            st.session_state["flash"] = "Rejected." if ok else "Already decided (double click ignored)."
            st.rerun()
    elif row["state"] == store.APPROVED and action:
        if st.button("Retry payment", key=f"{where}-retry-{request_id}", icon=":material/refresh:"):
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
        wait = (f"<span class='sg-state wait'><span class='sg-dot sg-live' style='color:var(--warn)'></span>"
                f"<b class='sg-mono'>{len(pending)}</b>&nbsp;waiting for a person</span>" if pending
                else f"<span class='sg-muted'>{len(pending)} waiting for a person</span>")
        st.markdown(f"<div style='font-size:.9rem;margin-bottom:.6rem'><span class='sg-muted'>"
                    f"<span class='sg-mono'>{len(decisions)}</span> decisions ·</span> {wait}</div>",
                    unsafe_allow_html=True)
        left, right = st.columns([2, 5])
        sel = st.session_state.get("selected") or (pending[0]["request_id"] if pending else decisions[0]["request_id"])
        with left.container(key="queue"):
            filt = st.radio("Show", ["All", "Waiting for a person", "ALLOW", "BLOCK", "ESCALATE"], horizontal=False)
            shown = [d for d in decisions if filt == "All" or (filt == "Waiting for a person" and d["state"] == store.ESCALATED)
                     or d["verdict"] == filt]
            for d in shown:
                label = f"{d['verdict']} · {d['request_id']}"
                sub = f"{d.get('kind') or ''} · {', '.join(d['rule_ids'])} · {STATE_NOTE.get(d['state'], d['state'])}"
                if st.button(label, key=f"pick-{d['request_id']}", help=sub, width="stretch",
                             type="primary" if d["request_id"] == sel else "secondary"):
                    st.session_state["selected"] = sel = d["request_id"]
                    st.rerun()
                st.markdown(f"<div style='margin:-10px 0 10px 10px;font-size:0.85em' class='sg-muted'>"
                            f"{badge(d['verdict'])} &nbsp;{html.escape(sub)}</div>", unsafe_allow_html=True)
        with right:
            decision_card(sel)


# ---------------------------------------------------------------------------------------- demo

def big_badge(verdict: str, rules: list[str]) -> str:
    return (f"<div class='sg-big'>{theme.badge(verdict, 'xl')}"
            f"<span class='sg-rules'>{html.escape(' · '.join(rules))}</span></div>")


def evidence(request_id: str, only_problems: bool = True) -> None:
    d = store.get_decision(request_id)
    if not d:
        return
    for r in d.reasons:
        st.markdown(f"<div class='sg-reason' style='font-size:1.08rem'><span class='sg-rule'>"
                    f"{html.escape(r.rule_id)}</span><span>{html.escape(r.text)}</span></div>",
                    unsafe_allow_html=True)
    rows = [c for c in d.checks if not only_problems or c.status.value != "VERIFIED"]
    for c in rows:
        srcs = " · ".join(f"{html.escape(s.kind)}: {link(s.ref)}" for s in c.sources)
        st.markdown(f"<div class='sg-check lg' style='--c:{theme.STATUS.get(c.status.value, theme.MUTED)}'>"
                    f"{theme.status_dot(c.status.value)} <b>{html.escape(c.name)}</b>"
                    f"<span class='sg-status'>{c.status.value}</span><br>{html.escape(c.note or '')}"
                    f"<div class='sg-src'>{srcs}</div></div>", unsafe_allow_html=True)


with tab_demo:
    ds = st.session_state.setdefault("demo", {})
    hero.render()
    top_r, _ = st.columns([2, 3], vertical_alignment="center")
    if top_r.button("Start fresh demo", type="primary", width="stretch", icon=":material/restart_alt:"):
        st.session_state["demo"] = ds = {"db": demo.fresh_db()}
        st.rerun()
    top_r.caption(f"DB `{Path(store.db_path()).name}` · payments **{razorpayx.mode()}**")
    for i, step in enumerate(demo.STEPS, 1):
        res = ds.get(step["id"])
        st.divider()
        h_l, h_r = st.columns([4, 1])
        h_l.markdown(f"<h2 style='font-size:1.4rem;margin:0 0 .3rem'><span class='sg-step'>{i:02d}</span>"
                     f"{html.escape(step['title'])}</h2>", unsafe_allow_html=True)
        h_l.caption(":material/mic: " + step["say"])
        crash = step["id"] == "crash"
        if h_r.button("Run" + (" + crash" if crash else ""), key=f"demo-run-{step['id']}", width="stretch",
                      icon=":material/play_arrow:"):
            ds[step["id"]] = demo.run_step(step["id"], crash=crash)
            st.rerun()
        if not res:
            continue
        rid = res["request_id"]
        row = store.get_decision_row(rid) or {}
        st.markdown(big_badge(res["verdict"], res["rule_ids"]), unsafe_allow_html=True)
        evidence(rid, only_problems=res["verdict"] != "ALLOW")
        if row.get("state") == store.ESCALATED:
            if st.button(f"Approve as {approver}", key=f"demo-approve-{step['id']}", type="primary",
                         icon=":material/check:"):
                res["approval"] = demo.approve(rid, approver, "Called back on the number on file; confirmed.")
                st.rerun()
        if res.get("approval"):
            ap = res["approval"]
            if ap.get("payout_id"):
                st.success(f"Approved by {approver} → receipt → executor → payout **{ap['payout_id']}** ({ap.get('payout_status') or ap['status']})")
            elif ap.get("status") == "no_payment":
                st.info(f"Approved by {approver}. The new account is on the vendor master; nothing to pay on a bank change.")
            else:
                st.warning(f"Approval result: {ap}")
        if res.get("payout"):
            st.success(f"Payout **{res['payout'].get('payout_id')}** · {res['payout'].get('status')}")
        if crash and res.get("crash"):
            cr = res["crash"]
            if cr.get("outbox_state") == "unknown":
                st.error(f"Payer killed (exit {cr['returncode']}). Outbox row **unknown**: the intent was saved; "
                         "did the money go?", icon=":material/bolt:")
                if st.button("Resume", key="demo-resume", type="primary", icon=":material/replay:"):
                    res["resumed"] = demo.resume()
                    st.rerun()
        if crash and res.get("resumed") is not None:
            n = len(demo.payouts_for_case("01_calm"))
            st.success(f"Resumed with the same key and the same bytes → payouts for this invoice: **{n}**")
        if step["id"] == "dup":
            n = len(demo.payouts_for_case("01_calm"))
            st.markdown(f"<div class='sg-count'>Payouts for invoice <span class='sg-mono'>2026-27-42</span>: "
                        f"<b>{n}</b></div>", unsafe_allow_html=True)
        st.download_button("Export decision report", data=report.decision_report_md(rid),
                           file_name=f"decision-{rid}.md", mime="text/markdown", key=f"demo-export-{step['id']}",
                           icon=":material/download:")


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
        if st.button("Run the gate", type="primary", icon=":material/play_arrow:"):
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
                st.error(f"Payer crashed (exit {cr['returncode']}). Outbox row is **{cr['outbox_state']}**: "
                         f"the intent is saved and the provider may or may not have the payout.", icon=":material/bolt:")
                if st.button("Resume", type="primary", icon=":material/replay:"):
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
    if c1.button("Verify chain", type="primary", icon=":material/link:"):
        res = ledger.verify()
        if res["ok"]:
            c2.success(f"Chain intact: {res['rows']} rows replayed, head {res.get('head', '')[:16]}…")
        else:
            c2.error(f"Chain broken at row {res['first_bad_row']}: {res['reason']}")
    evts = ledger.events(limit=300)
    st.dataframe([{"id": e["id"], "at": e["at"], "event": e["event_type"], "hash": e["hash"][:16] + "…",
                   "prev": e["prev_hash"][:16] + "…", "payload": json.dumps(e["payload"], ensure_ascii=False)[:200]}
                  for e in evts], hide_index=True, width="stretch")


# ------------------------------------------------------------------------------------- payouts

with tab_payouts:
    b1, b2, _ = st.columns([1, 1, 4])
    if b1.button("Refresh status", icon=":material/refresh:"):
        st.session_state["pflash"] = f"Status changes: {executor.refresh_payouts() or 'none'}"
    if b2.button("Resume unfinished", icon=":material/replay:"):
        st.session_state["pflash"] = f"Resumed: {executor.resume() or 'nothing to resume'}"
    if st.session_state.get("pflash"):
        st.info(st.session_state.pop("pflash"))
    if razorpayx.mode() == "test":
        st.caption("RazorpayX test mode: payouts stay 'processing' until moved in the dashboard.")
    st.markdown("#### Payouts")
    st.dataframe(store.list_payouts(), hide_index=True, width="stretch")
    st.markdown("#### Outbox")
    st.dataframe([{k: v for k, v in o.items() if k != "body"} for o in store.list_outbox()],
                 hide_index=True, width="stretch")
    if razorpayx.mode() == "mock":
        st.markdown("#### Provider view (mock): one row per real payout")
        st.dataframe(razorpayx.mock_payouts(), hide_index=True, width="stretch")
