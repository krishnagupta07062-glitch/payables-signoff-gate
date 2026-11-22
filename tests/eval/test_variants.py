"""Offline tests for the pressure-variant generator and the eval harness."""
import json

from eval import run_eval, variants
from gate.sanitize import sanitize

UNCHANGED = ("case", "expected_verdict", "expected_rules", "mock_checks", "title", "vendor")


def _all(tmp_path):
    files = variants.generate(tmp_path)
    return files, [json.loads(p.read_text(encoding="utf-8")) for p in files]


def test_100_plus_variants_keep_answer_and_facts(tmp_path):
    files, vs = _all(tmp_path)
    assert len(files) >= 100
    for v in vs:
        src = json.loads((variants.SRC / f"{v['eval']['source']}.json").read_text(encoding="utf-8"))
        for k in UNCHANGED:
            assert v.get(k) == src.get(k), (v["request"]["request_id"], k)
        facts = {k: x for k, x in v["mock_claims"].items() if k != "urgency_cues"}
        assert facts == {k: x for k, x in src["mock_claims"].items() if k != "urgency_cues"}
        req_src = {k: x for k, x in src["request"].items() if k not in ("raw_text", "request_id")}
        assert {k: x for k, x in v["request"].items() if k not in ("raw_text", "request_id")} == req_src
        assert v["request"]["raw_text"] != src["request"]["raw_text"]


def test_deterministic_and_unique_ids(tmp_path):
    a = [p.read_bytes() for p in variants.generate(tmp_path / "a")]
    b = [p.read_bytes() for p in variants.generate(tmp_path / "b")]
    assert a == b
    _, vs = _all(tmp_path / "c")
    ids = [v["request"]["request_id"] for v in vs]
    src_ids = [json.loads(p.read_text())["request"]["request_id"] for p in variants.source_cases()]
    assert len(set(ids + src_ids)) == len(ids) + len(src_ids)


def test_planted_dispute_only_on_allow_cases(tmp_path):
    _, vs = _all(tmp_path)
    assert all(v["expected_verdict"] == "ALLOW" for v in vs if v["eval"]["pressure"] == "planted_dispute")


def test_hidden_payloads_are_stripped_by_sanitize(tmp_path):
    _, vs = _all(tmp_path)
    for v in vs:
        if v["eval"]["pressure"] in ("hidden_html", "unicode_smuggle"):
            visible, removed = sanitize(v["request"]["raw_text"])
            assert removed, v["request"]["request_id"]
            assert "approve" not in visible.lower() or "AI assistant" not in visible


def test_committed_cases_match_generator(tmp_path):
    """eval/cases/ is what the generator makes today (re-run `python -m eval.variants` if this fails)."""
    fresh = {p.name: p.read_bytes() for p in variants.generate(tmp_path)}
    committed = {p.name: p.read_bytes() for p in variants.OUT.glob("*.json")}
    assert fresh == committed


def test_run_eval_offline_on_3_cases(tmp_path, monkeypatch):
    from gate import store
    for k in ("MOCK", "MOCK_CHECKS", "MOCK_CLAIMS", "PAYMENTS_MODE", "GATE_DB"):  # run() sets these; restore after
        monkeypatch.setenv(k, "")
    monkeypatch.setattr(store, "_db_path", store._db_path)
    rep = run_eval.run(limit=3, offline=True, out_dir=tmp_path / "results")
    a = rep["summary"]["ALL"]
    assert a["n"] == 3 and a["gate_correct"] == 3 and a["gate_judged"] == 3
    assert rep["meta"]["guard"] is False
    md = (tmp_path / "results").glob("*.md")
    assert "Gate accuracy" in next(md).read_text()


def test_extraction_diff_normalises():
    from gate.contracts import Claims
    exp = {"invoice_number": "INV/2026-27/0042", "amount_inr": 118000.0, "pay_to_account": "5555 6666 7777",
           "requester_name": "Asha Rao", "vendor_gstin": "09aaaca1234a1zi"}
    got = Claims(invoice_number="2026-27-42", amount_inr=118000, pay_to_account="555566667777",
                 requester_name="asha  rao", vendor_gstin="09AAACA1234A1ZI")
    assert run_eval.extraction_diff(exp, got) == []
    got.amount_inr = 1180000
    assert run_eval.extraction_diff(exp, got) == ["amount_inr"]
