"""Visual layer for the approval UI: palette, verdict badges, status marks and component CSS.

Look: warm cream canvas, near-black ink, a single lime accent for the one action that matters, pill buttons,
large tight headlines, white cards with hairline borders. Colours and fonts the Streamlit theme can express
live in .streamlit/config.toml; this module styles the rest. Nothing here changes what the app says or does.
"""
from __future__ import annotations

import html

import streamlit as st

CANVAS = "#F4F2EE"     # warm cream
CARD = "#FFFFFF"
SUNK = "#EDEAE4"
LINE = "#E2DED6"
INK = "#141414"
MUTED = "#6B6760"
DIM = "#9A958C"
LIME = "#E4F222"       # the accent: primary actions and highlights only, never text
OK = "#2F7D3B"         # verified / ALLOW
WARN = "#C77800"       # unverifiable / ESCALATE text
WARN_FILL = "#F5A524"  # ESCALATE badge fill: the one a person must act on
BAD = "#D13B2A"        # BLOCK, contradicted, broken

# verdict -> (colour, fill or None)
VERDICT = {"ALLOW": (OK, None), "BLOCK": (BAD, None), "ESCALATE": (INK, WARN_FILL)}
STATUS = {"VERIFIED": OK, "CONTRADICTED": BAD, "UNVERIFIABLE": WARN}

CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=Geist:wght@300..700&family=Geist+Mono:wght@400..600&display=swap');

:root {{
  --canvas:{CANVAS}; --card:{CARD}; --sunk:{SUNK}; --line:{LINE};
  --ink:{INK}; --muted:{MUTED}; --dim:{DIM};
  --lime:{LIME}; --ok:{OK}; --warn:{WARN}; --warn-fill:{WARN_FILL}; --bad:{BAD};
  --ease: cubic-bezier(.2,.7,.2,1);
  --mono: 'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  --shadow: 0 1px 2px rgba(20,20,20,.04), 0 8px 24px -12px rgba(20,20,20,.10);
}}

.stApp {{ background: var(--canvas); font-feature-settings: "ss01", "cv11"; -webkit-font-smoothing: antialiased; }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stMainBlockContainer"] {{ max-width: 1280px; padding-top: 2.4rem; }}

/* type: large, tight, quiet */
h1, h2, h3 {{ letter-spacing: -0.035em; color: var(--ink); font-weight: 500 !important; }}
h4 {{ text-transform: uppercase; letter-spacing: .1em; color: var(--muted) !important;
      font-size: .72rem !important; font-weight: 600 !important; margin-top: 1.8rem !important; }}
[data-testid="stCaptionContainer"] {{ color: var(--muted) !important; }}
code {{ font-family: var(--mono) !important; font-variant-numeric: tabular-nums; border-radius: 5px; }}
b, strong {{ font-weight: 600; }}
hr {{ border-color: var(--line) !important; opacity: 1; }}
::selection {{ background: var(--lime); color: var(--ink); }}
a {{ text-underline-offset: 3px; text-decoration-thickness: 1px; }}

/* sidebar */
[data-testid="stSidebar"] {{ border-right: 1px solid var(--line); }}
[data-testid="stSidebar"] h2 {{ font-size: 1.15rem !important; letter-spacing: -0.02em; }}
[data-testid="stSidebar"] h3 {{ font-size: .72rem !important; text-transform: uppercase;
      letter-spacing: .1em; color: var(--muted) !important; font-weight: 600 !important; }}
[data-testid="stSidebar"] [data-testid="stMetricValue"] {{ font-size: 1.6rem; }}

/* tabs */
[data-testid="stTabs"] [role="tablist"] {{ gap: 1.9rem; border-bottom: 1px solid var(--line); }}
[data-testid="stTab"] {{ color: var(--muted); padding-left: 0 !important; padding-right: 0 !important;
      transition: color .2s var(--ease); }}
[data-testid="stTab"] p {{ font-size: .92rem; font-weight: 500; }}
[data-testid="stTab"]:hover, [data-testid="stTab"][aria-selected="true"] {{ color: var(--ink); }}
[data-testid="stTabs"] [role="tabpanel"] {{ animation: sg-rise .32s var(--ease) both; }}

/* buttons: white pills with a hairline; the primary action is a lime pill */
.stButton button, .stDownloadButton button {{
  border-radius: 999px !important; font-weight: 500; border: 1px solid var(--line) !important;
  background: var(--card) !important; color: var(--ink) !important; padding-left: 1.1rem; padding-right: 1.1rem;
  transition: border-color .18s var(--ease), background .18s var(--ease), transform .18s var(--ease),
              box-shadow .18s var(--ease);
}}
.stButton button:hover, .stDownloadButton button:hover {{
  border-color: var(--ink) !important; transform: translateY(-1px); box-shadow: var(--shadow);
}}
.stButton button:active, .stDownloadButton button:active {{ transform: translateY(0) scale(.985); }}
.stButton button:focus-visible, .stDownloadButton button:focus-visible {{
  outline: none; box-shadow: 0 0 0 3px rgba(20,20,20,.18) !important;
}}
.stButton button[kind="primary"], [data-testid="stBaseButton-primary"] {{
  background: var(--lime) !important; color: var(--ink) !important; border-color: var(--lime) !important;
  font-weight: 600;
}}
.stButton button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover {{
  background: #D6E412 !important; border-color: #D6E412 !important;
}}
.stDownloadButton button {{ background: transparent !important; color: var(--muted) !important; font-size: .85rem; }}
.stDownloadButton button:hover {{ color: var(--ink) !important; }}

/* inbox list: rows, not buttons; the selected row gets an ink edge and a white card */
.st-key-queue .stButton button {{
  justify-content: flex-start; text-align: left; font-family: var(--mono); font-size: .8rem; font-weight: 500;
  background: transparent !important; border-color: transparent !important; color: var(--ink) !important;
  border-radius: 10px !important; padding: .5rem .8rem; box-shadow: none !important;
}}
.st-key-queue .stButton button:hover {{ background: var(--card) !important; border-color: var(--line) !important;
  transform: none; }}
.st-key-queue .stButton button[kind="primary"], .st-key-queue [data-testid="stBaseButton-primary"] {{
  background: var(--card) !important; border-color: var(--line) !important;
  box-shadow: inset 3px 0 0 var(--ink), var(--shadow) !important;
}}
.st-key-queue .stButton button > div, .st-key-queue .stButton button [data-testid="stMarkdownContainer"] {{
  justify-content: flex-start; width: 100%; text-align: left; }}
.st-key-queue .stButton button p {{ text-align: left; }}

/* inputs, expanders, alerts, tables */
[data-testid="stTextInput"] input, [data-testid="stNumberInput"] input {{ font-family: var(--mono); font-size: .85rem; }}
[data-testid="stExpander"] details {{ border-color: var(--line) !important; background: var(--card);
  border-radius: 12px !important; }}
[data-testid="stAlertContainer"] {{ border-radius: 12px; animation: sg-rise .28s var(--ease) both; }}
[data-testid="stMetricValue"] {{ font-family: var(--mono); font-variant-numeric: tabular-nums; }}
[data-testid="stDataFrame"] {{ border-radius: 12px; overflow: hidden; background: var(--card); }}
[data-testid="stRadio"] label p {{ font-size: .9rem; }}

/* components rendered by the app */
.sg-badge {{ display: inline-flex; align-items: center; font-family: var(--mono); font-weight: 600;
  letter-spacing: .08em; text-transform: uppercase; border-radius: 999px; border: 1px solid; line-height: 1;
  white-space: nowrap; vertical-align: middle; }}
.sg-badge.sm {{ font-size: .64rem; padding: .34em .75em; }}
.sg-badge.md {{ font-size: .78rem; padding: .5em 1.05em; }}
.sg-badge.xl {{ font-size: 2.1rem; padding: .3em .85em; letter-spacing: .06em;
  animation: sg-stamp .45s var(--ease) both; }}
.sg-dot {{ display: inline-block; width: .5em; height: .5em; border-radius: 50%; background: currentColor;
  flex: none; vertical-align: middle; }}
.sg-live {{ animation: sg-breathe 2.4s ease-in-out infinite; }}
.sg-muted {{ color: var(--muted); }}
.sg-mono {{ font-family: var(--mono); font-variant-numeric: tabular-nums; }}
.sg-state {{ color: var(--muted); font-size: .9rem; display: inline-flex; align-items: center; gap: .45em; }}
.sg-state.wait {{ color: var(--warn); font-weight: 500; }}
.sg-head {{ display: flex; align-items: center; flex-wrap: wrap; gap: .9rem; margin: .2rem 0 .6rem;
  animation: sg-rise .3s var(--ease) both; }}
.sg-head .sg-id {{ font-family: var(--mono); font-size: 1.05rem; font-weight: 500; }}
.sg-reason {{ display: flex; gap: .8rem; align-items: baseline; padding: .6rem 0; border-bottom: 1px solid var(--line); }}
.sg-reason:last-child {{ border-bottom: 0; }}
.sg-rule {{ font-family: var(--mono); font-size: .72rem; font-weight: 600; color: var(--ink); background: var(--lime);
  border-radius: 6px; padding: .16em .5em; white-space: nowrap; }}
.sg-check {{ border: 1px solid var(--line); border-radius: 12px; background: var(--card); padding: .8rem 1rem;
  margin: .5rem 0; box-shadow: inset 3px 0 0 var(--c, var(--line));
  transition: box-shadow .2s var(--ease), transform .2s var(--ease); }}
.sg-check:hover {{ box-shadow: inset 3px 0 0 var(--c, var(--line)), var(--shadow); }}
.sg-check .sg-status {{ font-family: var(--mono); font-size: .66rem; font-weight: 600; letter-spacing: .08em;
  color: var(--c); margin-left: .45rem; }}
.sg-check .sg-src {{ font-size: .8rem; color: var(--muted); margin-top: .4rem; line-height: 1.6; }}
.sg-check .sg-src a {{ color: var(--ink); }}
.sg-check.lg {{ font-size: 1.02rem; }}
.sg-acct {{ border: 1px solid var(--line); border-radius: 14px; padding: .9rem 1.1rem; background: var(--card); }}
.sg-acct.claimed {{ border-color: var(--warn-fill); box-shadow: 0 0 0 3px rgba(245,165,36,.14); }}
.sg-acct .sg-label {{ font-size: .68rem; letter-spacing: .1em; text-transform: uppercase; font-weight: 600;
  margin-bottom: .5rem; color: var(--muted); }}
.sg-acct.trusted .sg-label {{ color: var(--ok); }}
.sg-acct.claimed .sg-label {{ color: var(--warn); }}
.sg-new {{ color: var(--ink); background: var(--warn-fill); font-family: var(--mono); font-size: .68rem; font-weight: 600;
  letter-spacing: .08em; border-radius: 999px; padding: .16em .55em; }}
.sg-onfile {{ color: var(--ok); font-family: var(--mono); font-size: .72rem; }}
.sg-amount {{ font-family: var(--mono); font-variant-numeric: tabular-nums; font-size: 2rem; font-weight: 500;
  letter-spacing: -0.02em; }}
.sg-big {{ display: flex; align-items: center; flex-wrap: wrap; gap: 1.1rem; margin: .7rem 0 .4rem; }}
.sg-big .sg-rules {{ font-family: var(--mono); font-size: 1.05rem; color: var(--muted); }}
.sg-count {{ font-size: 1.25rem; }}
.sg-count b {{ font-family: var(--mono); font-size: 1.6rem; background: var(--lime); border-radius: 6px; padding: 0 .3em; }}
.sg-step {{ font-family: var(--mono); color: var(--dim); margin-right: .55rem; font-weight: 400; }}
.sg-hero {{ font-size: 2.6rem; font-weight: 500; letter-spacing: -0.04em; line-height: 1.08; max-width: 22ch; }}
.sg-hero mark {{ background: linear-gradient(transparent 64%, var(--lime) 64%); color: inherit; padding: 0 .05em; }}

@keyframes sg-rise {{ from {{ opacity: 0; transform: translateY(6px); }} to {{ opacity: 1; transform: none; }} }}
@keyframes sg-stamp {{ 0% {{ opacity: 0; transform: scale(1.06); }} 100% {{ opacity: 1; transform: none; }} }}
@keyframes sg-breathe {{ 0%, 100% {{ opacity: 1; box-shadow: 0 0 0 0 rgba(199,120,0,.45); }}
  50% {{ opacity: .6; box-shadow: 0 0 0 5px rgba(199,120,0,0); }} }}
@media (prefers-reduced-motion: reduce) {{ *, *::before, *::after {{ animation: none !important;
  transition: none !important; }} }}
"""


def inject() -> None:
    """Add the component CSS to the page (call once, right after set_page_config)."""
    st.html(f"<style>{CSS}</style>")


def badge(verdict: str, size: str = "sm") -> str:
    color, fill = VERDICT.get(verdict, (MUTED, None))
    style = (f"background:{fill};color:{color};border-color:{fill}" if fill
             else f"color:{color};border-color:{color}40;background:{color}0F")
    return f"<span class='sg-badge {size}' style='{style}'>{html.escape(verdict)}</span>"


def status_dot(status: str, live: bool = False) -> str:
    return (f"<span class='sg-dot{' sg-live' if live else ''}' "
            f"style='color:{STATUS.get(status, MUTED)}'></span>")


def state_note(text: str, waiting: bool) -> str:
    if not text:
        return ""
    dot = "<span class='sg-dot sg-live' style='color:var(--warn)'></span>" if waiting else ""
    return f"<span class='sg-state{' wait' if waiting else ''}'>{dot}{html.escape(text)}</span>"
