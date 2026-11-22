"""Run every demo case and compare against the expected verdict. OWNER: Krishna.

    python scripts/run_demo.py                 # all cases (MOCK=1 by default: offline, no credits)
    python scripts/run_demo.py --live          # MOCK=0: real Claude extraction and live checks
    python scripts/run_demo.py --case 3        # one case number
    python scripts/run_demo.py --trace         # print each case's pipeline trace and reasons

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
    a = ap.parse_args()
    os.environ["MOCK"] = "0" if a.live else os.environ.get("MOCK", "1")

    from gate.pipeline import all_case_files, run_case  # after MOCK is set
    from gate.runbudget import RunBudget

    budget = RunBudget(max_credits=a.credits, max_seconds=1800)
    rows, failures = [], 0
    for path in all_case_files():
        case_no = int(path.name.split("_")[0]) if path.name[:2].isdigit() else 0
        if a.case and case_no != a.case:
            continue
        case, res = run_case(path, budget, today=date(2026, 11, 23))
        d = res.decision
        missing = [r for r in case["expected_rules"] if r not in d.rule_ids]
        ok = d.verdict.value == case["expected_verdict"] and not missing
        failures += not ok
        rows.append((path.stem, case["title"][:58], case["expected_verdict"], d.verdict.value, ",".join(d.rule_ids),
                     "ok" if ok else f"FAIL{' missing ' + ','.join(missing) if missing else ''}"))
        if a.trace or not ok:
            print(f"\n=== {path.stem}: {case['title']}")
            for t in res.trace:
                print("   trace:", t)
            for r in d.reasons:
                print(f"   {r.rule_id}: {r.text}")

    w = [max(len(str(r[i])) for r in rows + [("case", "title", "expected", "actual", "rules", "result")]) for i in range(6)]
    header = ("case", "title", "expected", "actual", "rules", "result")
    print()
    print("  ".join(h.ljust(w[i]) for i, h in enumerate(header)))
    print("  ".join("-" * w[i] for i in range(6)))
    for r in rows:
        print("  ".join(str(v).ljust(w[i]) for i, v in enumerate(r)))
    s = budget.summary()
    print(f"\n{len(rows) - failures}/{len(rows)} cases as expected | credits {s['credits']} | "
          f"calls {s['calls']} ({s['cached_calls']} cached) | {s['seconds']}s | MOCK={os.environ['MOCK']}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
