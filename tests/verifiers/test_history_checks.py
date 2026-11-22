from gate.contracts import CheckStatus, Claims, Request, RequestKind
from gate.keys import account_hash, invoice_key
from gate.verifiers import history_checks as hc

from tests.verifiers.conftest import ACCT, GOOD_GSTIN

V, C, U = CheckStatus.VERIFIED, CheckStatus.CONTRADICTED, CheckStatus.UNVERIFIABLE


def _row(**kw):
    base = {"request_id": "OLD1", "vendor_id": "V001", "invoice_number": "inv 2026 27 42", "amount_inr": 125000.0,
            "invoice_date": "2026-11-18", "account_hash": account_hash(ACCT), "verdict": "ALLOW"}
    base["invoice_key"] = invoice_key(GOOD_GSTIN, base["invoice_number"], base["invoice_date"])
    base.update(kw)
    return base


def test_duplicate(invoice_request, invoice_claims, vendor):
    c = hc.duplicate_invoice(invoice_request, invoice_claims, vendor, [_row()])
    assert c.status == C and c.value["prior_request_id"] == "OLD1"
    assert hc.duplicate_invoice(invoice_request, invoice_claims, vendor, []).status == V
    assert hc.duplicate_invoice(invoice_request, invoice_claims, vendor, None).status == U
    assert hc.duplicate_invoice(invoice_request, invoice_claims, vendor, [_row(verdict="BLOCK")]).status == V
    invoice_claims.invoice_number = None
    assert hc.duplicate_invoice(invoice_request, invoice_claims, vendor, []).status == U


def test_near_duplicate(invoice_request, invoice_claims, vendor):
    # exact duplicates are not near-duplicates
    assert hc.near_duplicate_invoice(invoice_request, invoice_claims, vendor, [_row()]).status == V
    near = _row(invoice_number="2026-27-43", invoice_key="other")
    assert hc.near_duplicate_invoice(invoice_request, invoice_claims, vendor, [near]).status == C
    same_amt = _row(invoice_number="ZZ-9", invoice_key="x", amount_inr=125300.0, invoice_date="2026-11-15")
    assert hc.near_duplicate_invoice(invoice_request, invoice_claims, vendor, [same_amt]).status == C
    far = _row(invoice_number="ZZ-9", invoice_key="x", amount_inr=90000.0)
    assert hc.near_duplicate_invoice(invoice_request, invoice_claims, vendor, [far]).status == V
    assert hc.near_duplicate_invoice(invoice_request, invoice_claims, vendor, None).status == U


def test_next_sequential_invoice_is_not_a_near_duplicate(invoice_request, invoice_claims, vendor):
    # near-miss: INV/2026-27/0042 was paid; 0043, 0142 and 0024 are the vendor's other bills (different amounts).
    # Before the fix each scored 90-95 on the number alone and escalated (E4).
    for prior in ("INV/2026-27/0043", "INV/2026-27/0142", "INV/2026-27/0024"):
        row = _row(invoice_number=prior, invoice_key="other", amount_inr=98000.0, invoice_date="2026-11-01")
        c = hc.near_duplicate_invoice(invoice_request, invoice_claims, vendor, [row])
        assert c.status == V, (prior, c.note)


def test_similar_number_same_amount_is_a_near_duplicate(invoice_request, invoice_claims, vendor):
    # the classic re-send with a tweaked number, even months later
    row = _row(invoice_number="INV/2026-27/0043", invoice_key="other", invoice_date="2026-06-01")
    c = hc.near_duplicate_invoice(invoice_request, invoice_claims, vendor, [row])
    assert c.status == C and "amount is the same" in c.note


def test_similar_number_unknown_amount_stays_cautious(invoice_request, invoice_claims, vendor):
    invoice_claims.amount_inr = None
    row = _row(invoice_number="INV/2026-27/0043", invoice_key="other")
    assert hc.near_duplicate_invoice(invoice_request, invoice_claims, vendor, [row]).status == C


def test_account_on_master(vendor):
    assert hc.account_on_vendor_master(Claims(pay_to_account=ACCT), vendor).status == V
    assert hc.account_on_vendor_master(Claims(), vendor).status == V
    assert hc.account_on_vendor_master(Claims(pay_to_account="999999999999"), vendor).status == C
    vendor.bank_accounts[0].verified_at = None
    assert hc.account_on_vendor_master(Claims(pay_to_account=ACCT), vendor).status == U
    vendor.bank_accounts = []
    assert hc.account_on_vendor_master(Claims(), vendor).status == U


def test_account_shared(vendor):
    assert hc.account_shared_across_vendors(Claims(pay_to_account=ACCT), vendor, [_row()]).status == V
    c = hc.account_shared_across_vendors(Claims(pay_to_account=ACCT), vendor, [_row(vendor_id="V009")])
    assert c.status == C and c.value["other_vendor_ids"] == ["V009"]
    assert hc.account_shared_across_vendors(Claims(), vendor, None).status == U


def test_po_match(invoice_request, invoice_claims):
    assert hc.po_match(invoice_request, invoice_claims).status == V
    invoice_claims.amount_inr = 140000.0
    assert hc.po_match(invoice_request, invoice_claims).status == C
    invoice_request.po = None
    assert hc.po_match(invoice_request, invoice_claims).status == U
    r = Request(request_id="R", kind=RequestKind.INVOICE, raw_text="", po={"po_number": "PO-1", "amount_inr": 10.0})
    assert hc.po_match(r, Claims(amount_inr=10.0, po_number="PO-2")).status == C


def test_penny_drop_simulated(vendor):
    # a simulated penny drop can never confirm a new account (spec: cases 3, 4, 5, 8)
    c = hc.penny_drop_name_match(Claims(pay_to_account="5555", pay_to_holder="Acmeleaf Tanners Pvt Ltd"), vendor)
    assert c.status == U and "SIMULATED" in c.sources[0].ref
    assert hc.penny_drop_name_match(Claims(), vendor).status == V  # verified account on file
    assert hc.penny_drop_name_match(Claims(pay_to_account="5555", pay_to_holder="Rahul Kumar"), vendor).status == C
    assert hc.penny_drop_name_match(Claims(pay_to_account="5555"), vendor).status == U
