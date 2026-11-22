import time

from gate.contracts import CHECK_NAMES, Check, CheckStatus, Claims, Request, RequestKind
from gate import verifiers
from gate.verifiers import crustdata_checks as cdc

U = CheckStatus.UNVERIFIABLE


def test_run_all_invoice_offline_never_raises(invoice_request, invoice_claims, vendor, budget):
    checks = verifiers.run_all(invoice_request, invoice_claims, vendor, [], budget)
    names = {c.name for c in checks}
    assert {"duplicate_invoice", "gstin_checksum", "po_match", "account_on_vendor_master"} <= names
    assert names <= set(CHECK_NAMES)
    by = {c.name: c for c in checks}
    assert by["gstin_checksum"].status == CheckStatus.VERIFIED
    # MOCK=1 with no fixtures: every networked check fails closed
    for n in ("domain_age_days", "ifsc_valid", "gstin_exists", "vendor_active"):
        assert by[n].status == U, n


def test_run_all_bank_change_has_requester_checks(vendor, budget):
    r = Request(request_id="R2", kind=RequestKind.BANK_CHANGE, raw_text="", sender_email="riya@acmeleaf.in")
    cl = Claims(requester_name="Riya Synthetic", requester_role="CFO", requested_change="bank_change",
                pay_to_account="999988887777", pay_to_ifsc="HDFC0CAGSBK")
    names = {c.name for c in verifiers.run_all(r, cl, vendor, [], budget)}
    assert {"requester_current_role", "requester_departed", "sender_domain_lookalike", "penny_drop_name_match"} <= names
    assert "duplicate_invoice" not in names and "account_on_vendor_master" not in names


def test_run_all_survives_exceptions(invoice_request, invoice_claims, vendor, budget, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(cdc, "vendor_active", boom)
    checks = verifiers.run_all(invoice_request, invoice_claims, vendor, [], budget)
    va = [c for c in checks if c.name == "vendor_active"][0]
    assert va.status == U and "kaboom" in va.note


def test_run_all_timeout_is_unverifiable(invoice_request, invoice_claims, vendor, budget, monkeypatch):
    monkeypatch.setattr(verifiers, "PER_CHECK_TIMEOUT_S", 0.3)
    monkeypatch.setattr(cdc, "vendor_active", lambda *a, **k: time.sleep(2) or Check("vendor_active", CheckStatus.VERIFIED))
    t0 = time.monotonic()
    checks = verifiers.run_all(invoice_request, invoice_claims, vendor, [], budget)
    assert time.monotonic() - t0 < 1.5
    va = [c for c in checks if c.name == "vendor_active"][0]
    assert va.status == U and "timed out" in va.note


def test_run_all_429_and_timeout_mid_run(vendor, budget, live, http, monkeypatch):
    """Crustdata rate-limits identify and times out on person search while the free sources answer:
    the Crustdata checks fail closed, everything else still gets a real answer, nothing raises."""
    monkeypatch.setattr(time, "sleep", lambda s: None)  # skip the 429 backoff

    def timeout():
        raise TimeoutError("read timed out")
    t, _ = live({"/company/identify": (429, {}, {}), "/person/search": timeout})
    http({"rdap": (200, {"events": [{"eventAction": "registration", "eventDate": "2015-01-01T00:00:00Z"}]}),
          "ifsc.razorpay.com": (200, {"BANK": "HDFC Bank", "BRANCH": "X", "CITY": "Pune"})})
    r = Request(request_id="R4", kind=RequestKind.BANK_CHANGE, raw_text="", sender_email="riya@acmeleaf.in")
    cl = Claims(requester_name="Riya Synthetic", requester_role="CFO", requested_change="bank_change",
                pay_to_account="999988887777", pay_to_ifsc="HDFC0CAGSBK", pay_to_holder="Acmeleaf Tanners Pvt Ltd")
    by = {c.name: c for c in verifiers.run_all(r, cl, vendor, [], budget)}
    for n in ("sender_domain_matches_vendor", "requester_current_role", "requester_departed"):
        assert by[n].status == U, n
    assert "429" in by["sender_domain_matches_vendor"].note or "rate" in by["sender_domain_matches_vendor"].note.lower()
    assert "timed out" in by["requester_current_role"].note.lower() or "Timeout" in by["requester_current_role"].note
    assert by["domain_age_days"].status == CheckStatus.VERIFIED
    assert by["ifsc_valid"].status == CheckStatus.VERIFIED
    assert by["sender_domain_lookalike"].status == CheckStatus.VERIFIED
    assert len([p for p, _ in t.calls if p == "/company/identify"]) == 4  # 1 try + 3 retries, then gave up


def test_run_all_garbage_input_never_raises(vendor, budget):
    r = Request(request_id="R3", kind="email", raw_text="", sender_email="not-an-email")
    out = verifiers.run_all(r, Claims(invoice_number="???", amount_inr=-1), vendor, None, budget)
    assert isinstance(out, list)


def test_every_check_has_a_source(invoice_request, invoice_claims, vendor, budget, monkeypatch):
    # including the paths where nothing outside was consulted: vendor not linked, crashed check, missing input
    vendor.crustdata_company_id = None
    monkeypatch.setattr(cdc, "vendor_active", lambda *a, **k: 1 / 0)
    invoice_claims.requester_name = "Riya Synthetic"
    invoice_request.sender_email = None
    checks = verifiers.run_all(invoice_request, invoice_claims, vendor, None, budget)
    assert checks and all(c.sources and c.sources[0].ref for c in checks), [c.name for c in checks if not c.sources]
    req_role = [c for c in checks if c.name == "requester_current_role"][0]
    assert req_role.sources[0].kind == "vendor_master"
