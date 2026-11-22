"""Agents view: every decision, check, source, payout and ledger fact as plain, copyable text.

Built for an AI agent (or a person) that reads the page instead of clicking through it:
- one index with anchor links (#summary, #decisions, #d-<request_id>, #ledger, #payouts, #export);
- every block is a code block with a copy button: the Markdown decision report and the stored JSON;
- the whole state is downloadable as one JSON file.
Open it directly with ?view=agents. Reads only; it never approves or pays.
Palette: near-black and grays with a hint of orange.
"""
from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components

from app import report
from gate import ledger, store
from gate.payments import razorpayx

ORANGE = "#FF7A1A"

CSS = """
<style>
:root { --a-bg:#0A0A0A; --a-card:#121212; --a-line:#262626; --a-text:#E6E6E6; --a-muted:#8F8F8F; --a-orange:#FF7A1A; }
.stApp, [data-testid="stAppViewContainer"] { background: var(--a-bg) !important; color: var(--a-text); }
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stSidebar"] { background: #0F0F0F !important; border-right: 1px solid var(--a-line); }
[data-testid="stSidebar"] *, .stApp p, .stApp li, .stApp span, .stApp label, .stApp h1, .stApp h2, .stApp h3
  { color: var(--a-text); }
.stApp h1, .stApp h2, .stApp h3 { font-family: 'Geist Mono', ui-monospace, monospace !important; letter-spacing: -0.01em; }
[data-testid="stMainBlockContainer"] h2 { font-size: 1.15rem !important; border-top: 1px solid var(--a-line);
  padding-top: 1.4rem !important; }
[data-testid="stMainBlockContainer"] h2::before { content: "## "; color: var(--a-orange); }
[data-testid="stMainBlockContainer"] h3 { font-size: .98rem !important; }
[data-testid="stMainBlockContainer"] h3::before { content: "### "; color: #5A5A5A; }
.stApp a { color: var(--a-text) !important; text-decoration-color: var(--a-orange) !important; }
.stApp a:hover { color: var(--a-orange) !important; }
[data-testid="stCaptionContainer"] p { color: var(--a-muted) !important; }
[data-testid="stCode"] pre { background: var(--a-card) !important; }
[data-testid="stCode"] pre code { background: transparent !important; color: #D4D4D4 !important; }
[data-testid="stCode"] pre code span { color: #CFCFCF !important; }
[data-testid="stCode"] .token.title, [data-testid="stCode"] .token.property,
[data-testid="stCode"] .token.bold, [data-testid="stCode"] .token.keyword { color: var(--a-orange) !important; }
[data-testid="stCode"] .token.string, [data-testid="stCode"] .token.url, [data-testid="stCode"] .token.code
  { color: #A8A8A8 !important; }
[data-testid="stCode"] .token.punctuation, [data-testid="stCode"] .token.table { color: #8A8A8A !important; }
.stApp input { background: #161616 !important; color: var(--a-text) !important; border-color: #333 !important; }
.stApp [data-baseweb="input"], .stApp [data-baseweb="base-input"] { background: #161616 !important; }
[data-testid="stButtonGroup"] button { background: #141414 !important; color: var(--a-muted) !important;
  border-color: #333 !important; }
[data-testid="stButtonGroup"] button[aria-checked="true"], [data-testid="stButtonGroup"] button[kind*="Active"]
  { background: #222 !important; color: var(--a-orange) !important; border-color: var(--a-orange) !important; }
[data-testid="stButtonGroup"] button p { color: inherit !important; }
[data-testid="stCode"] { border: 1px solid var(--a-line); border-radius: 10px; }
.stApp code { background: #1A1A1A !important; color: #E0E0E0 !important; }
.stApp [data-testid="stExpander"] details { background: var(--a-card) !important; border-color: var(--a-line) !important; }
.stApp .stButton button, .stApp .stDownloadButton button { background: #161616 !important; color: var(--a-text) !important;
  border: 1px solid #333 !important; }
.stApp .stButton button:hover, .stApp .stDownloadButton button:hover { border-color: var(--a-orange) !important;
  color: var(--a-orange) !important; }
.stApp [data-testid="stDataFrame"] { background: var(--a-card); }
.ag-kv { font-family: 'Geist Mono', ui-monospace, monospace; font-size: .95rem; line-height: 1.85; }
.ag-kv b { color: var(--a-muted); font-weight: 400; display: inline-block; min-width: 15ch; }
.ag-o { color: var(--a-orange) !important; }
.ag-toc { font-family: 'Geist Mono', ui-monospace, monospace; font-size: .95rem; line-height: 1.9; columns: 2; }
</style>
"""

ASCII = """<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
 html,body{margin:0;height:100%;background:#0A0A0A;overflow:hidden}
 pre{margin:0;font:13px/15px 'Geist Mono',ui-monospace,monospace;color:#3A3A3A;white-space:pre;cursor:crosshair;
     user-select:none;height:100%}
 .o{color:#FF7A1A}.w{color:#E6E6E6}.g{color:#7A7A7A}
</style></head><body><pre id="p" aria-hidden="true"></pre><script>
(() => {
 const el = document.getElementById('p'), RAMP = ' .:-=+*#%@';
 const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
 const LABEL = ['email', 'sanitize', 'extract', 'verify', 'decide', 'pay once'];
 let cols = 0, rows = 0, cw = 7.8, ch = 15, mx = -99, my = -99, ripples = [];
 function size() {
   const probe = document.createElement('span'); probe.textContent = 'M'.repeat(50); el.appendChild(probe);
   cw = probe.getBoundingClientRect().width / 50; el.removeChild(probe);
   cols = Math.floor(innerWidth / cw); rows = Math.floor(innerHeight / ch);
 }
 function esc(c) { return c === '<' ? '&lt;' : c === '>' ? '&gt;' : c === '&' ? '&amp;' : c; }
 function draw(t) {
   const mid = Math.floor(rows / 2), out = [];
   const step = Math.max(10, Math.floor((cols - 8) / LABEL.length));
   const pkt = Math.floor((t / 70) % (step * LABEL.length));              // a packet travelling the pipeline
   for (let y = 0; y < rows; y++) {
     let line = '';
     for (let x = 0; x < cols; x++) {
       const dx = (x - mx) * cw / ch, dy = y - my, d = Math.hypot(dx, dy);
       let v = 0.5 + 0.5 * Math.sin(x * 0.18 + t / 900) * Math.cos(y * 0.35 - t / 1300);
       v *= 0.35;
       if (d < 9) v += (1 - d / 9) * 0.75;
       for (const r of ripples) { const rr = (t - r.t) / 45, dd = Math.abs(Math.hypot((x - r.x) * cw / ch, y - r.y) - rr);
         if (dd < 1.2) v += 0.6 * (1 - dd / 1.2) * Math.max(0, 1 - rr / 40); }
       let c = RAMP[Math.min(RAMP.length - 1, Math.floor(v * RAMP.length))];
       let cls = d < 4 ? 'o' : v > 0.7 ? 'g' : '';
       if (y === mid) {                                                    // the pipeline rail
         const i = Math.floor((x - 4) / step), off = (x - 4) % step;
         if (x >= 4 && i < LABEL.length) {
           const lab = '[' + LABEL[i] + ']';
           if (off < lab.length) { c = lab[off]; cls = i === LABEL.length - 1 ? 'o' : 'w'; }
           else { c = '-'; cls = 'g'; }
           if (Math.abs(x - 4 - pkt) < 1) { c = '>'; cls = 'o'; }
         }
       }
       line += cls ? `<span class="${cls}">${esc(c)}</span>` : esc(c);
     }
     out.push(line);
   }
   el.innerHTML = out.join('\\n');
   ripples = ripples.filter(r => t - r.t < 1800);
   if (!still && !document.hidden) requestAnimationFrame(draw);
 }
 el.addEventListener('pointermove', e => { mx = e.clientX / cw; my = e.clientY / ch; if (still) draw(performance.now()); });
 el.addEventListener('pointerleave', () => { mx = my = -99; if (still) draw(performance.now()); });
 el.addEventListener('pointerdown', e => ripples.push({x: e.clientX / cw, y: e.clientY / ch, t: performance.now()}));
 document.addEventListener('visibilitychange', () => { if (!document.hidden && !still) requestAnimationFrame(draw); });
 addEventListener('resize', size); size(); requestAnimationFrame(draw);
})();
</script></body></html>"""


def snapshot() -> dict:
    """Everything the page shows, as one JSON-able dict."""
    decisions = []
    for d in store.list_decisions():
        row = store.get_decision_row(d["request_id"]) or {}
        decisions.append({**{k: d.get(k) for k in ("request_id", "verdict", "state", "kind", "rule_ids")},
                          "decision": json.loads(row["decision"]) if row.get("decision") else None,
                          "approvals": store.approvals_for(d["request_id"])})
    return {"payments_mode": razorpayx.mode(), "ledger": ledger.verify(), "decisions": decisions,
            "payouts": store.list_payouts(),
            "outbox": [{k: v for k, v in o.items() if k != "body"} for o in store.list_outbox()],
            "credits": store.credits_summary()}


def render() -> None:
    st.html(CSS)
    components.html(ASCII, height=170)
    snap = snapshot()
    decisions = snap["decisions"]
    waiting = [d for d in decisions if d["state"] == store.ESCALATED]
    lv = snap["ledger"]

    st.header("summary", anchor="summary")
    counts = {v: sum(1 for d in decisions if d["verdict"] == v) for v in ("ALLOW", "BLOCK", "ESCALATE")}
    st.markdown(
        "<div class='ag-kv'>"
        f"<b>decisions</b> {len(decisions)} &nbsp;(ALLOW {counts['ALLOW']} · BLOCK {counts['BLOCK']} · "
        f"ESCALATE {counts['ESCALATE']})<br>"
        f"<b>waiting_for_person</b> <span class='ag-o'>{len(waiting)}</span>"
        + (" &nbsp;→ " + ", ".join(f"<a href='#d-{d['request_id'].lower()}'>{d['request_id']}</a>" for d in waiting)
           if waiting else "") + "<br>"
        f"<b>ledger</b> {'chain OK' if lv['ok'] else 'BROKEN at row ' + str(lv['first_bad_row'])} · {lv['rows']} rows<br>"
        f"<b>payouts</b> {len(snap['payouts'])}<br>"
        f"<b>payments_mode</b> {snap['payments_mode']}<br>"
        "<b>read_only</b> this view never approves or pays; a person approves in the Humans view"
        "</div>", unsafe_allow_html=True)
    st.code(json.dumps({"decisions": len(decisions), **counts, "waiting_for_person": [d["request_id"] for d in waiting],
                        "ledger_ok": lv["ok"], "ledger_rows": lv["rows"], "payouts": len(snap["payouts"]),
                        "payments_mode": snap["payments_mode"]}, indent=2), language="json")

    st.header("index", anchor="index")
    links = ["<a href='#summary'>#summary</a>", "<a href='#decisions'>#decisions</a>"]
    links += [f"&nbsp;&nbsp;<a href='#d-{d['request_id'].lower()}'>#{d['request_id']}</a> "
              f"<span class='{'ag-o' if d['state'] == store.ESCALATED else ''}'>{d['verdict']}</span>"
              for d in decisions]
    links += ["<a href='#ledger'>#ledger</a>", "<a href='#payouts'>#payouts</a>", "<a href='#export'>#export</a>"]
    st.markdown("<div class='ag-toc'>" + "<br>".join(links) + "</div>", unsafe_allow_html=True)

    st.header("decisions", anchor="decisions")
    if not decisions:
        st.caption("No decisions yet. Seed or run one from the Humans view.")
    for d in decisions:
        st.subheader(f"{d['request_id']} · {d['verdict']} · {d['state']}", anchor=f"d-{d['request_id'].lower()}")
        st.caption(f"kind {d.get('kind') or '?'} · rules {', '.join(d['rule_ids'] or []) or '—'}")
        st.code(report.decision_report_md(d["request_id"]), language="markdown", wrap_lines=True)
        with st.expander(f"stored JSON · {d['request_id']}"):
            st.code(json.dumps(d, indent=2, ensure_ascii=False, default=str), language="json", wrap_lines=True)

    st.header("ledger", anchor="ledger")
    st.code(json.dumps(lv, indent=2, default=str), language="json")
    st.code("\n".join(f"{e['id']:>4}  {e['at']}  {e['event_type']:<16} {e['hash'][:16]}  prev {e['prev_hash'][:16]}"
                      for e in ledger.events(limit=300)) or "(empty)", language="text")

    st.header("payouts", anchor="payouts")
    st.code(json.dumps({"payouts": snap["payouts"], "outbox": snap["outbox"]}, indent=2, default=str),
            language="json", wrap_lines=True)

    st.header("export", anchor="export")
    st.download_button("Download full state (JSON)", data=json.dumps(snap, indent=2, ensure_ascii=False, default=str),
                       file_name="signoff-gate-state.json", mime="application/json", key="agent-export",
                       icon=":material/download:")
