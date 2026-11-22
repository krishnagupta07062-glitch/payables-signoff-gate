"""Warm the Crustdata cache for every demo request before the demo. OWNER: Lavya.

    python scripts/warm_cache.py                # all cases in fixtures/requests/ and fixtures/private/requests/
    python scripts/warm_cache.py --case 3       # one case number
    python scripts/warm_cache.py --credits 40   # credit ceiling for the whole run (default 40)
    python scripts/warm_cache.py --extract      # use the live extractor instead of each case's stored claims

Runs with MOCK=0, so it calls the real sources (Crustdata, RDAP, IFSC, GST portal). Crustdata answers are
cached in cache/crustdata.sqlite, so a second run spends 0 credits. That is the check this script prints
at the end.

It runs the same checks as verifiers.run_all (verifiers.plan), but one at a time with no deadline,
so a cold cache under the 5-per-minute rate limit still fills completely, and each check's time is shown.
By default it uses each case's stored claims (fixtures' mock_claims), which match what the extractor
should produce, so warming spends no model tokens. Payment history is empty here; history checks need
no network, so they need no warming.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
NEEDS_HISTORY = {"duplicate_invoice", "near_duplicate_invoice", "account_shared_across_vendors"}


def _load_env() -> None:
    """Read .env into the environment without overriding anything already set. Prints no values."""
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if v.strip():
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _short(s: str | None, n: int) -> str:
    s = (s or "").replace("\n", " ")
    return s if len(s) <= n else s[: n - 3] + "..."


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--case", type=int, help="only this case number")
    ap.add_argument("--credits", type=float, default=40.0, help="credit ceiling for the whole run")
    ap.add_argument("--extract", action="store_true", help="use the live extractor instead of stored claims")
    ap.add_argument("--quiet", action="store_true", help="print only the per-case summary lines and the total")
    a = ap.parse_args()

    _load_env()
    os.environ["MOCK"] = "0"
    if not os.environ.get("CRUSTDATA_API_KEY"):
        print("CRUSTDATA_API_KEY is not set (put it in .env). Crustdata checks will come back UNVERIFIABLE.")

    from gate import verifiers
    from gate.contracts import Check, CheckStatus
    from gate.extractor import extract
    from gate.pipeline import all_case_files, load_case, load_vendors, request_from_dict
    from gate.runbudget import RunBudget
    from gate.contracts import Vendor

    vendors = load_vendors()
    files = [f for f in all_case_files() if a.case is None or load_case(f).get("case") == a.case]
    if not files:
        print("No case files found.")
        return 1
    budget = RunBudget(max_credits=a.credits, max_seconds=3600, run_id="warm-" + time.strftime("%H%M%S"))

    rows, unexpected = [], []
    t_all = time.monotonic()
    for f in files:
        case = load_case(f)
        req = request_from_dict(case["request"])
        vendor = vendors.get(req.vendor_id or "") or Vendor(vendor_id=req.vendor_id or "UNKNOWN",
                                                            legal_name="(unknown vendor)")
        claims = extract(req, budget, mock_claims=None if a.extract else case.get("mock_claims"))
        want = {m["name"]: m["status"] for m in case.get("mock_checks") or []}
        spent_before = budget.credits
        label = f"{case.get('case'):02d}_{case.get('variant', '')}" if isinstance(case.get("case"), int) else f.stem
        if not a.quiet:
            print(f"\n== {label}: {_short(case.get('title'), 70)}")
            print(f"   {'check':30} {'status':13} {'spec':13} {'credits':>7} {'secs':>5}  source")
        for names, job in verifiers.plan(req, claims, vendor, [], budget):
            t0 = time.monotonic()
            try:
                res = job()
                got = res if isinstance(res, list) else [res]
            except Exception as e:  # same fail-closed rule as run_all
                got = [Check(n, CheckStatus.UNVERIFIABLE, note=f"{type(e).__name__}: {e}") for n in names]
            secs = time.monotonic() - t0
            for c in got:
                status = CheckStatus(c.status).value
                spec = want.get(c.name, "-")
                ref = c.sources[0].ref if c.sources else "(no source)"
                rows.append((label, c.name, status, c.credits, secs, ref))
                if c.name in NEEDS_HISTORY:
                    spec = "-"  # warming runs with no payment history, so these can't match the spec here
                if spec != "-" and spec != status:
                    unexpected.append((label, c.name, status, spec, c.note))
                if not a.quiet:
                    flag = "" if spec in ("-", status) else "  <-- differs from spec"
                    print(f"   {c.name:30} {status:13} {spec:13} {c.credits:7.2f} {secs:5.1f}  {_short(ref, 60)}{flag}")
        print(f"   {label}: {budget.credits - spent_before:.2f} credits")

    summ = budget.summary()
    live_calls = [c for c in budget.calls if c["provider"] == "crustdata" and not c["cached"]]
    print("\n== Summary")
    print(f"   cases {len(files)} | checks {len(rows)} | Crustdata credits {summ['credits']:.2f} | "
          f"Crustdata calls {len(live_calls)} live, "
          f"{sum(1 for c in budget.calls if c['provider'] == 'crustdata' and c['cached'])} cached | "
          f"{time.monotonic() - t_all:.0f}s")
    if not os.environ.get("CRUSTDATA_API_KEY"):
        print("   No CRUSTDATA_API_KEY: nothing was cached. Add it to .env and run again.")
    elif not live_calls:
        print("   Cache is warm: a second run spends 0 Crustdata credits.")
    else:
        print("   Run again: the second run should spend 0 Crustdata credits.")
    slow = sorted(rows, key=lambda r: -r[4])[:5]
    print("   Slowest checks: " + ", ".join(f"{r[0]} {r[1]} {r[4]:.1f}s" for r in slow))
    if unexpected:
        print(f"\n== {len(unexpected)} check(s) differ from the case spec (mock_checks):")
        for label, name, status, spec, note in unexpected:
            print(f"   {label} {name}: got {status}, spec {spec}. {_short(note, 110)}")
    print(f"   Call log: {budget.dir / 'calls.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
