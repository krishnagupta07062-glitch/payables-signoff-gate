"""Run every demo case and compare against the expected verdict. OWNER: Krishna.

    python scripts/run_demo.py                 # all cases (MOCK=1 by default: offline, no credits)
    python scripts/run_demo.py --live          # MOCK=0: real Claude extraction and live checks
    python scripts/run_demo.py --case 3        # one case number
    python scripts/run_demo.py --trace         # print each case's pipeline trace and reasons
    python scripts/run_demo.py --contrast      # also ask a plain model guard (raw email) for each case

Exit code is non-zero if any case's verdict differs or an expected rule is missing.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="MOCK=0: call Claude and live verifiers")
    ap.add_argument("--case", type=int, help="only this case number")
    ap.add_argument("--trace", action="store_true")
    ap.add_argument("--credits", type=float, default=40.0, help="credit ceiling for the whole demo run")
    ap.add_argument("--contrast", action="store_true", help="compare with a plain model guard reading the raw email")
    a = ap.parse_args()
    os.environ["MOCK"] = "0" if a.live else os.environ.get("MOCK", "1")
    if not os.environ.get("GATE_DB"):  # a fresh database per demo run, so earlier runs never count as history
        import time
        Path("runs").mkdir(exist_ok=True)
        os.environ["GATE_DB"] = str(Path("runs") / f"demo-{time.strftime('%H%M%S')}.sqlite")

    from gate.pipeline import all_case_files, load_vendors, request_from_dict, run_case  # after MOCK is set
    from gate import baseline_guard
    vendors = load_vendors()
    from gate.runbudget import RunBudget

    budget = RunBudget(max_credits=a.credits, max_seconds=1800)
    rows, failures = [], 0
    for path in all_case_files():
        case_no = int(path.name[:2]) if path.name[:2].isdigit() else 0
        if a.case and case_no != a.case:
            continue
        case, res = run_case(path, budget, today=date(2026, 11, 23))
        d = res.decision
        missing = [r for r in case["expected_rules"] if r not in d.rule_ids]
        ok = d.verdict.value == case["expected_verdict"] and not missing
        failures += not ok
        row = [path.stem, case["title"][:58], case["expected_verdict"], d.verdict.value, ",".join(d.rule_ids),
               "ok" if ok else f"FAIL{' missing ' + ','.join(missing) if missing else ''}"]
        if a.contrast:
            req = request_from_dict(case["request"])
            b = baseline_guard.judge(req, vendors.get(req.vendor_id or ""), budget)
            mark = "" if b["verdict"] is None else (" ✓" if b["verdict"] == case["expected_verdict"] else " ✗")
            row.append((b["verdict"] or "n/a") + mark)
            if b["verdict"] and b["verdict"] != case["expected_verdict"]:
                print(f"\n--- baseline wrong on {path.stem}: {b['verdict']} ({b['reason'][:200]})")
            elif b["verdict"] is None:
                row[-1] = "n/a"
        rows.append(tuple(row))
        if a.trace or not ok:
            print(f"\n=== {path.stem}: {case['title']}")
            for t in res.trace:
                print("   trace:", t)
            for r in d.reasons:
                print(f"   {r.rule_id}: {r.text}")

    header = ("case", "title", "expected", "gate", "rules", "result") + (("baseline",) if a.contrast else ())
    n = len(header)
    w = [max(len(str(r[i])) for r in rows + [header]) for i in range(n)]
    print()
    print("  ".join(h.ljust(w[i]) for i, h in enumerate(header)))
    print("  ".join("-" * w[i] for i in range(n)))
    for r in rows:
        print("  ".join(str(v).ljust(w[i]) for i, v in enumerate(r)))
    if a.contrast:
        judged = [r for r in rows if r[-1] != "n/a"]
        right = sum(r[-1].endswith("✓") for r in judged)
        print(f"\nbaseline guard: {right}/{len(judged)} right" if judged
              else "\nbaseline guard unavailable (no ANTHROPIC_API_KEY?)")
    s = budget.summary()
    print(f"\n{len(rows) - failures}/{len(rows)} cases as expected | credits {s['credits']} | "
          f"calls {s['calls']} ({s['cached_calls']} cached) | {s['seconds']}s | MOCK={os.environ['MOCK']}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
