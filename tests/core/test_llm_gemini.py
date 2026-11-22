"""Gemini provider: response parsing and failure handling, offline."""
from gate import extractor, llm_gemini
from gate.contracts import Request, RequestKind
from gate.runbudget import RunBudget


def test_parse_ok_and_fenced():
    j = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '```json\n{"amount_inr": 5}\n```'}]}}]}
    assert llm_gemini.parse_response(j) == ({"amount_inr": 5}, "")


def test_parse_blocked_and_bad_json():
    assert llm_gemini.parse_response({"promptFeedback": {"blockReason": "SAFETY"}})[0] is None
    bad = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "not json"}]}}]}
    assert llm_gemini.parse_response(bad) == (None, "invalid JSON")


def test_extractor_fails_closed_without_key(monkeypatch):
    monkeypatch.setenv("GATE_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("MOCK", "0")
    r = Request(request_id="t", kind=RequestKind.INVOICE, raw_text="Invoice 42, Rs 100")
    c = extractor.extract(r, RunBudget(max_credits=1))
    assert c.amount_inr is None and c.extraction_notes.startswith("extraction failed")


def test_baseline_guard_imports_and_fails_soft(monkeypatch):
    from gate import baseline_guard
    monkeypatch.setenv("GATE_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    r = Request(request_id="t", kind=RequestKind.INVOICE, raw_text="Invoice 42")
    assert baseline_guard.judge(r, None, RunBudget(max_credits=1))["verdict"] is None


def test_fallback_order(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    monkeypatch.delenv("GEMINI_FALLBACK_MODELS", raising=False)
    assert llm_gemini.models_to_try()[0] == "gemini-3.1-flash-lite" and len(set(llm_gemini.models_to_try())) == len(llm_gemini.models_to_try())
