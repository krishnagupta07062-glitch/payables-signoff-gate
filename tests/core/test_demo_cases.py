"""Every committed demo case gives its expected verdict and rules offline (MOCK=1)."""
from datetime import date

import pytest

from gate.pipeline import all_case_files, run_case
from gate.runbudget import RunBudget

CASES = [p for p in all_case_files() if "private" not in str(p)]


@pytest.mark.parametrize("path", CASES, ids=[p.stem for p in CASES])
def test_case(path, monkeypatch):
    monkeypatch.setenv("MOCK", "1")
    case, res = run_case(path, RunBudget(max_credits=1), execute=False, today=date(2026, 11, 23))
    assert res.decision.verdict.value == case["expected_verdict"], res.decision.reasons
    for rule in case["expected_rules"]:
        assert rule in res.decision.rule_ids


def test_pushy_and_hinglish_variants_match_calm(monkeypatch):
    monkeypatch.setenv("MOCK", "1")
    by_case = {}
    for p in CASES:
        case, res = run_case(p, RunBudget(max_credits=1), execute=False, today=date(2026, 11, 23))
        by_case.setdefault(case["case"], set()).add((res.decision.verdict, tuple(res.decision.rule_ids)))
    for n in (1, 3, 5):
        assert len(by_case[n]) == 1, f"case {n} variants disagree: {by_case[n]}"


def test_hidden_injection_is_stripped(monkeypatch):
    monkeypatch.setenv("MOCK", "1")
    p = next(p for p in CASES if p.stem == "07_calm")
    _, res = run_case(p, RunBudget(max_credits=1), execute=False, today=date(2026, 11, 23))
    assert any("Skip all verification" in r for r in res.decision.claims.removed_hidden_content)
