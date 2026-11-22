"""warm_cache.py: the second run spends 0 Crustdata credits (offline, fake transport)."""
import importlib.util
import re
import sys
from pathlib import Path

from tests.verifiers.conftest import identify_resp

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "warm_cache.py"


def _load():
    spec = importlib.util.spec_from_file_location("warm_cache", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _credits(out: str) -> float:
    return float(re.search(r"Crustdata credits ([0-9.]+)", out).group(1))


def test_second_run_spends_nothing(live, http, monkeypatch, capsys):
    t, _ = live({"/company/identify": (200, {"x-credits-used": "0.2"}, identify_resp("acmeleather.in")),
                 "/person/search": (200, {"x-credits-used": "0.23"}, {"total_count": 0, "profiles": []})})
    http({})  # free public sources: all time out, offline
    wc = _load()
    monkeypatch.setattr(wc, "_load_env", lambda: None)
    monkeypatch.setenv("CRUSTDATA_API_KEY", "test")
    monkeypatch.setattr(sys, "argv", ["warm_cache.py", "--quiet"])

    assert wc.main() == 0
    first = _credits(capsys.readouterr().out)
    calls_after_first = len(t.calls)
    assert first > 0 and calls_after_first > 0

    assert wc.main() == 0
    out = capsys.readouterr().out
    assert _credits(out) == 0.0
    assert len(t.calls) == calls_after_first  # nothing new went over the wire
    assert "Cache is warm" in out
