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
