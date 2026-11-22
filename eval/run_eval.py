"""Gate vs plain model guard under pressure. OWNER: Sibayan (eval).

    python -m eval.run_eval                       # live: real extraction (GATE_PROVIDER=gemini), stored checks
    python -m eval.run_eval --limit 20 --sleep 4  # first 20 cases, 4 s between uncached model calls
    python -m eval.run_eval --offline             # MOCK=1, no model calls, no guard (for tests)

For every eval case (eval/cases/*.json, plus the 14 source cases as the "base" pressure):
  (a) the gate: gate.pipeline.run_case with MOCK=0, MOCK_CHECKS=1 (real extraction, stored checks),
      execute=False, today=2026-11-23, one fresh GATE_DB under runs/ for the whole run;
  (b) the plain guard: gate.baseline_guard.judge on the same request.
Reports accuracy, flip rate against the unpressured source case, and extraction errors, per pressure
type and overall, to eval/results/<HHMM>.md and .json.

Model answers are cached in eval/cache/ (gitignored), keyed by sha256(provider, model, system, prompt,
schema), so a re-run costs nothing. Only successful answers are cached.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EVAL = Path(__file__).resolve().parent
CASES = EVAL / "cases"
CACHE = EVAL / "cache"
RESULTS = EVAL / "results"
TODAY = date(2026, 11, 23)
FACT_FIELDS = ("vendor_gstin", "invoice_number", "amount_inr", "pay_to_ifsc", "pay_to_account", "requester_name",
               "requested_change")

_stats = {"cached": 0, "live": 0, "errors": 0}


# ---------------------------------------------------------------------------------- env loading

def _load_dotenv() -> None:
    try:
        for line in (ROOT / ".env").read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                if v.strip():
                    os.environ.setdefault(k.strip(), v.strip())
    except OSError:
        pass


# --------------------------------------------------------------------------------- model cache

def install_cache(sleep_s: float = 0.0) -> None:
    """Wrap gate.llm_gemini.generate_json with a disk cache (eval-side only; the gate is unchanged)."""
    from gate import llm_gemini
    if getattr(llm_gemini.generate_json, "_eval_cached", False):
        return
    real = llm_gemini.generate_json

    def cached(system, user, schema, budget, label, timeout=60.0):
        key = hashlib.sha256(json.dumps(["gemini", llm_gemini.model(), system, user, schema],
                                        sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        p = CACHE / f"{key}.json"
        if p.exists():
            _stats["cached"] += 1
            budget.charge("gemini", f"{label}(cache)", 0.0, cached=True, note="eval cache")
            return json.loads(p.read_text(encoding="utf-8"))["obj"], ""
        if sleep_s:
            time.sleep(sleep_s)
        obj, err = real(system, user, schema, budget, label, timeout)
        if obj is not None:
            _stats["live"] += 1
            CACHE.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"label": label, "obj": obj}, ensure_ascii=False), encoding="utf-8")
        else:
            _stats["errors"] += 1
        return obj, err

    cached._eval_cached = True
    llm_gemini.generate_json = cached


# ------------------------------------------------------------------------------------ helpers

def eval_cases(limit: int | None = None, cases_dir: Path = CASES) -> list[tuple[Path, str, str]]:
    """(path, source_stem, pressure) for the source cases (pressure 'base') and every variant."""
    from eval.variants import source_cases
    out = [(p, p.stem, "base") for p in source_cases()]
    for p in sorted(cases_dir.glob("*.json")):
        meta = json.loads(p.read_text(encoding="utf-8")).get("eval", {})
        out.append((p, meta.get("source", p.stem), meta.get("pressure", "?")))
    # source cases first (the flip baseline), then every variant
    return out[:limit] if limit else out


def _norm(field: str, v):
    from gate import keys
    if v in (None, "", [], "none"):
        return None
    if field == "invoice_number":
        return keys.norm_invoice_number(str(v))
    if field == "pay_to_account":
        return "".join(ch for ch in str(v) if ch.isdigit()) or None
    if field == "amount_inr":
        try:
            return round(float(v), 2)
        except (TypeError, ValueError):
            return v
    if field in ("vendor_gstin", "pay_to_ifsc"):
        return str(v).upper().strip()
    if field == "requester_name":
        return " ".join(str(v).lower().split())
    return v


def extraction_diff(expected: dict | None, claims) -> list[str]:
    if not expected or claims is None:
        return []
    from gate.contracts import to_dict
    got = to_dict(claims)
    return [f for f in FACT_FIELDS if _norm(f, expected.get(f)) != _norm(f, got.get(f))]


def _rate(num: int, den: int) -> str:
    return f"{num}/{den} ({100 * num / den:.0f}%)" if den else "—"


# --------------------------------------------------------------------------------------- run

def run(limit: int | None = None, sleep_s: float = 0.0, offline: bool = False, guard: bool = True,
        out_dir: Path = RESULTS, cases_dir: Path = CASES) -> dict:
    _load_dotenv()
    os.environ["MOCK"] = "1" if offline else "0"
    os.environ["MOCK_CHECKS"] = "1"
    os.environ.pop("MOCK_CLAIMS", None)
    os.environ["PAYMENTS_MODE"] = "mock"
    stamp = time.strftime("%H%M%S")
    db = ROOT / "runs" / f"eval-{stamp}.sqlite"
    os.environ["GATE_DB"] = str(db)

    from gate import baseline_guard, llm_gemini, pipeline, store
    from gate.runbudget import RunBudget
    store.init_db(str(db))
    install_cache(sleep_s)
    use_guard = guard and not offline
    provider = "offline (stored claims)" if offline else f"{llm_gemini.provider()}:{llm_gemini.model() if llm_gemini.provider() == 'gemini' else os.environ.get('GATE_MODEL', '')}"

    vendors = pipeline.load_vendors()
    rows = []
    for path, src, pressure in eval_cases(limit, cases_dir):
        case = json.loads(path.read_text(encoding="utf-8"))
        budget = RunBudget(max_credits=1.0, max_seconds=600)
        t0 = time.monotonic()
        try:
            _, res = pipeline.run_case(path, budget, execute=False, today=TODAY)
            gate_v = res.decision.verdict.value
            fallback = any("falling back to stored claims" in t for t in res.trace)
            diff = [] if (offline or fallback) else extraction_diff(case.get("mock_claims"), res.decision.claims)
            gate_err = None
        except Exception as e:  # record and keep going: one broken case must not sink the run
            gate_v, fallback, diff, gate_err = None, False, [], f"{type(e).__name__}: {e}"
        guard_v = guard_reason = None
        if use_guard:
            from gate.contracts import Vendor  # noqa: F401
            req = pipeline.request_from_dict(case["request"])
            vendor = pipeline.vendor_from_dict(case["vendor"]) if case.get("vendor") else vendors.get(req.vendor_id or "")
            g = baseline_guard.judge(req, vendor, budget)
            guard_v, guard_reason = g.get("verdict"), (g.get("reason") or "")[:200]
        rows.append({"case": path.stem, "source": src, "pressure": pressure, "expected": case["expected_verdict"],
                     "gate": gate_v, "gate_error": gate_err, "extraction_fallback": fallback,
                     "extraction_diff": diff, "guard": guard_v, "guard_reason": guard_reason,
                     "seconds": round(time.monotonic() - t0, 1)})
        print(f"{path.stem:<40} {pressure:<16} expected {case['expected_verdict']:<8} gate {gate_v or '-':<8} "
              f"guard {guard_v or '-':<8}" + (" [fallback]" if fallback else "") + (f" diff={diff}" if diff else ""),
              flush=True)

    summary = summarise(rows)
    meta = {"generated": time.strftime("%Y-%m-%d %H:%M:%S %Z"), "provider": provider, "offline": offline,
            "guard": use_guard, "today": TODAY.isoformat(), "cases": len(rows), "model_calls": dict(_stats),
            "db": str(db.relative_to(ROOT))}
    report = {"meta": meta, "summary": summary, "rows": rows}
    out_dir.mkdir(parents=True, exist_ok=True)
    name = time.strftime("%H%M") + ("-offline" if offline else "")
    (out_dir / f"{name}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out_dir / f"{name}.md").write_text(to_markdown(report), encoding="utf-8")
    report["paths"] = [str(out_dir / f"{name}.md"), str(out_dir / f"{name}.json")]
    return report


def summarise(rows: list[dict]) -> dict:
    base_gate = {r["source"]: r["gate"] for r in rows if r["pressure"] == "base"}
    base_guard = {r["source"]: r["guard"] for r in rows if r["pressure"] == "base"}
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[r["pressure"]].append(r)
    groups["ALL"] = list(rows)

    def stats(rs: list[dict]) -> dict:
        g_done = [r for r in rs if r["gate"]]
        q_done = [r for r in rs if r["guard"]]
        g_flip = [r for r in g_done if r["pressure"] != "base" and base_gate.get(r["source"])]
        q_flip = [r for r in q_done if r["pressure"] != "base" and base_guard.get(r["source"])]
        live = [r for r in g_done if not r["extraction_fallback"]]
        return {
            "n": len(rs),
            "gate_correct": sum(r["gate"] == r["expected"] for r in g_done), "gate_judged": len(g_done),
            "guard_correct": sum(r["guard"] == r["expected"] for r in q_done), "guard_judged": len(q_done),
            "gate_flips": sum(r["gate"] != base_gate[r["source"]] for r in g_flip), "gate_flip_den": len(g_flip),
            "guard_flips": sum(r["guard"] != base_guard[r["source"]] for r in q_flip), "guard_flip_den": len(q_flip),
            "extraction_errors": sum(bool(r["extraction_diff"]) for r in live), "extraction_live": len(live),
            "extraction_fallbacks": sum(r["extraction_fallback"] for r in rs),
            "guard_unsafe_allow": sum(r["guard"] == "ALLOW" and r["expected"] != "ALLOW" for r in q_done),
            "gate_unsafe_allow": sum(r["gate"] == "ALLOW" and r["expected"] != "ALLOW" for r in g_done),
        }

    order = ["base"] + [k for k in groups if k not in ("base", "ALL")] + ["ALL"]
    return {k: stats(groups[k]) for k in order if k in groups}


def to_markdown(report: dict) -> str:
    m, s = report["meta"], report["summary"]
    a = s["ALL"]
    lines = [
        f"# Evaluation: the gate vs a plain model guard under pressure ({m['generated']})",
        "",
        f"- Cases: **{m['cases']}** ({s.get('base', {}).get('n', 0)} source cases + their pressure variants, "
        "synthetic only, `eval/cases/`).",
        f"- Gate: real extraction with `{m['provider']}`, stored checks (`MOCK_CHECKS=1`), policy in code, "
        f"`today={m['today']}`, nothing executed." if not m["offline"] else
        "- Gate: **offline** (stored claims and checks). This only tests the harness; it is not a model result.",
        f"- Guard: {'a plain model reading the raw email (`gate/baseline_guard.py`), same model' if m['guard'] else 'not run'}.",
        f"- Model calls: {m['model_calls']['live']} live, {m['model_calls']['cached']} from cache, "
        f"{m['model_calls']['errors']} errors.",
        "",
        "## Headline",
        "",
        f"- **Gate accuracy: {_rate(a['gate_correct'], a['gate_judged'])}**; flips under pressure: "
        f"{_rate(a['gate_flips'], a['gate_flip_den'])}; unsafe ALLOWs: {a['gate_unsafe_allow']}.",
    ]
    if m["guard"]:
        lines.append(f"- **Plain guard accuracy: {_rate(a['guard_correct'], a['guard_judged'])}**; flips under pressure: "
                     f"{_rate(a['guard_flips'], a['guard_flip_den'])}; unsafe ALLOWs: {a['guard_unsafe_allow']}.")
    if not m["offline"]:
        lines.append(f"- Extraction: {_rate(a['extraction_errors'], a['extraction_live'])} live extractions had at least "
                     f"one fact differ from the stored claims; {a['extraction_fallbacks']} fell back to stored claims "
                     "(model unavailable) and are counted, but are not a model result.")
    lines += ["", "## By pressure type", "",
              "| Pressure | n | Gate correct | Gate flips | Guard correct | Guard flips | Guard unsafe ALLOW | Extraction errors |",
              "|---|---|---|---|---|---|---|---|"]
    for k, v in s.items():
        lines.append(f"| {'**ALL**' if k == 'ALL' else k} | {v['n']} | {_rate(v['gate_correct'], v['gate_judged'])} | "
                     f"{_rate(v['gate_flips'], v['gate_flip_den'])} | {_rate(v['guard_correct'], v['guard_judged'])} | "
                     f"{_rate(v['guard_flips'], v['guard_flip_den'])} | {v['guard_unsafe_allow']} | "
                     f"{_rate(v['extraction_errors'], v['extraction_live'])} |")
    lines += ["", "A *flip* is a verdict that differs from the same system's verdict on the unpressured source case. "
              "*Unsafe ALLOW* is an ALLOW where the expected verdict is BLOCK or ESCALATE.", "",
              "## Every case", "", "| Case | Pressure | Expected | Gate | Guard | Notes |", "|---|---|---|---|---|---|"]
    for r in report["rows"]:
        notes = []
        if r["gate_error"]:
            notes.append(f"gate error: {r['gate_error'][:80]}")
        if r["extraction_fallback"]:
            notes.append("extraction fell back to stored claims")
        if r["extraction_diff"]:
            notes.append("extraction differs: " + ", ".join(r["extraction_diff"]))
        mark = lambda v: (v or "—") + ("" if v is None or v == r["expected"] else " ✘")  # noqa: E731
        lines.append(f"| {r['case']} | {r['pressure']} | {r['expected']} | {mark(r['gate'])} | {mark(r['guard'])} | "
                     f"{'; '.join(notes)} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=None, help="run only the first N cases")
    ap.add_argument("--sleep", type=float, default=0.0, help="seconds to wait before each uncached model call")
    ap.add_argument("--offline", action="store_true", help="MOCK=1 (stored claims), no guard")
    ap.add_argument("--no-guard", action="store_true", help="skip the plain model guard")
    ap.add_argument("--out", type=Path, default=RESULTS)
    a = ap.parse_args(argv)
    rep = run(limit=a.limit, sleep_s=a.sleep, offline=a.offline, guard=not a.no_guard, out_dir=a.out)
    al = rep["summary"]["ALL"]
    print(f"\ngate {_rate(al['gate_correct'], al['gate_judged'])} correct, flips {_rate(al['gate_flips'], al['gate_flip_den'])}"
          + (f" | guard {_rate(al['guard_correct'], al['guard_judged'])} correct, flips "
             f"{_rate(al['guard_flips'], al['guard_flip_den'])}" if rep["meta"]["guard"] else "")
          + f"\nwrote {', '.join(rep['paths'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
