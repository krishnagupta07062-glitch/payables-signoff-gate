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


def test_run_all_garbage_input_never_raises(vendor, budget):
    r = Request(request_id="R3", kind="email", raw_text="", sender_email="not-an-email")
    out = verifiers.run_all(r, Claims(invoice_number="???", amount_inr=-1), vendor, None, budget)
    assert isinstance(out, list)
