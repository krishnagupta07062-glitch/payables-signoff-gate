"""One test per policy rule, plus tone invariance."""
from datetime import date

import pytest

from gate.contracts import (BankAccount, Check, CheckStatus, Claims, Contact, Request, RequestKind, Vendor,
                            Verdict)
from gate.keys import account_hash
from gate.policy import decide

V, C, U = CheckStatus.VERIFIED, CheckStatus.CONTRADICTED, CheckStatus.UNVERIFIABLE
TODAY = date(2026, 11, 23)  # a Monday
ACCT = "123456789012"


def vendor(**kw):
    base = dict(vendor_id="V1", legal_name="Acme Leather Exports Pvt Ltd", gstin="09AAACA1234A1Z5", pan="AAACA1234A",
                state_code="09", domains=["acmeleather.in"],
                bank_accounts=[BankAccount("HDFC0001234", ACCT[-4:], account_hash(ACCT), "ACME LEATHER EXPORTS",
                                           verified_at="2026-01-10", added_at="2026-01-10")],
                contacts=[Contact("Asha Rao", "Accounts Manager", "asha@acmeleather.in", "+91-90000-00000", "2026-01-10")])
    base.update(kw)
    return Vendor(**base)


def invoice_claims(**kw):
    base = dict(vendor_name="Acme Leather Exports", vendor_gstin="09AAACA1234A1Z5", invoice_number="INV-0042",
                invoice_date="2026-11-20", amount_inr=118000.0, po_number="PO-77", requested_change="payment")
    base.update(kw)
    return Claims(**base)


def clean_invoice_checks(**override):
    names = ["duplicate_invoice", "near_duplicate_invoice", "account_on_vendor_master", "account_shared_across_vendors",
             "gstin_checksum", "gstin_matches_vendor", "po_match"]
    st = {n: V for n in names}
    st.update(override)
    return [Check(n, s, note=f"{n} note") for n, s in st.items()]


def inv_request(text="Please pay INV-0042"):
    return Request("R1", RequestKind.INVOICE, text, sender_email="asha@acmeleather.in")


def bank_request(text="Please update our bank account"):
    return Request("R2", RequestKind.BANK_CHANGE, text, sender_email="cfo@acmeleather.in")


def run(req, claims, checks, v=None):
    return decide(req, claims, v or vendor(), checks, today=TODAY)


def test_a1_clean_invoice_allowed_with_action():
    d = run(inv_request(), invoice_claims(), clean_invoice_checks())
    assert d.verdict == Verdict.ALLOW and d.rule_ids == ["A1"]
    assert d.action and d.action.amount_paise == 11800000 and d.action.account_last4 == "9012"
    assert d.action.invoice_key == "09AAACA1234A1Z5|42|2026-2027" and d.action_hash


@pytest.mark.parametrize("check,rule", [
    ("duplicate_invoice", "B1"), ("sender_domain_lookalike", "B2"), ("domain_age_days", "B2"),
    ("requester_departed", "B3"), ("account_shared_across_vendors", "B4"), ("gstin_checksum", "B5"),
    ("gstin_matches_vendor", "B5"), ("ifsc_valid", "B6"), ("penny_drop_name_match", "B6"),
])
def test_block_rules(check, rule):
    d = run(inv_request(), invoice_claims(), clean_invoice_checks(**{check: C}))
    assert d.verdict == Verdict.BLOCK and rule in d.rule_ids and d.action is None


def test_b6_invoice_names_unknown_account():
    d = run(inv_request(), invoice_claims(pay_to_account="999988887777"), clean_invoice_checks())
    assert d.verdict == Verdict.BLOCK and "B6" in d.rule_ids


def test_invoice_naming_master_account_is_fine():
    d = run(inv_request(), invoice_claims(pay_to_account="1234-5678-9012"), clean_invoice_checks())
    assert d.verdict == Verdict.ALLOW


def test_e1_bank_change_always_escalates_even_when_everything_verifies():
    checks = [Check("sender_domain_matches_vendor", V), Check("requester_current_role", V),
              Check("penny_drop_name_match", V)]
    d = run(bank_request(), Claims(requested_change="bank_change", requester_name="Asha Rao",
                                   pay_to_account="555566667777", pay_to_ifsc="ICIC0000001"), checks)
    assert d.verdict == Verdict.ESCALATE and d.rule_ids == ["E1"] and d.action is None


def test_e1_bank_change_from_departed_person_blocks():
    checks = [Check("sender_domain_matches_vendor", V), Check("requester_departed", C, note="left 2026-10")]
    d = run(bank_request(), Claims(requested_change="bank_change", requester_name="X"), checks)
    assert d.verdict == Verdict.BLOCK and "B3" in d.rule_ids and "E1" in d.rule_ids


def test_e2_cooling_off_for_new_account():
    v = vendor(bank_accounts=[BankAccount("HDFC0001234", "9012", account_hash(ACCT), "ACME", verified_at="2026-11-20",
                                          added_at="2026-11-20")])
    d = run(inv_request(), invoice_claims(), clean_invoice_checks(), v)
    assert d.verdict == Verdict.ESCALATE and "E2" in d.rule_ids and d.action is not None


def test_e3_unverified_account():
    v = vendor(bank_accounts=[BankAccount("HDFC0001234", "9012", account_hash(ACCT), "ACME", verified_at=None,
                                          added_at="2026-01-01")])
    d = run(inv_request(), invoice_claims(), clean_invoice_checks(), v)
    assert "E3" in d.rule_ids


def test_e4_near_duplicate():
    d = run(inv_request(), invoice_claims(), clean_invoice_checks(near_duplicate_invoice=C))
    assert d.verdict == Verdict.ESCALATE and "E4" in d.rule_ids


@pytest.mark.parametrize("status", [C, U])
def test_e5_po(status):
    d = run(inv_request(), invoice_claims(), clean_invoice_checks(po_match=status))
    assert d.verdict == Verdict.ESCALATE and "E5" in d.rule_ids


def test_e6_unverifiable_duplicate_check_never_passes():
    d = run(inv_request(), invoice_claims(), clean_invoice_checks(duplicate_invoice=U))
    assert d.verdict == Verdict.ESCALATE and "E6" in d.rule_ids


def test_e6_missing_checks_escalate():
    d = run(inv_request(), invoice_claims(), [])
    assert d.verdict == Verdict.ESCALATE and "E6" in d.rule_ids


def test_e6_missing_amount():
    d = run(inv_request(), invoice_claims(amount_inr=None), clean_invoice_checks())
    assert d.verdict == Verdict.ESCALATE and d.action is None


def test_e7_country():
    d = run(inv_request(), invoice_claims(pay_to_country="Poland"), clean_invoice_checks())
    assert "E7" in d.rule_ids
    d2 = run(inv_request(), invoice_claims(pay_to_country="India"), clean_invoice_checks())
    assert d2.verdict == Verdict.ALLOW


def test_e8_limit():
    d = run(inv_request(), invoice_claims(amount_inr=900000.0), clean_invoice_checks())
    assert d.verdict == Verdict.ESCALATE and "E8" in d.rule_ids


def test_e9_other_contradiction():
    checks = clean_invoice_checks() + [Check("vendor_news", C, note="acquired last week")]
    d = run(inv_request(), invoice_claims(), checks)
    assert d.verdict == Verdict.ESCALATE and "E9" in d.rule_ids


def test_unrecognised_request_escalates():
    d = run(Request("R3", RequestKind.EMAIL, "hello"), Claims(), [])
    assert d.verdict == Verdict.ESCALATE


def test_tone_never_changes_the_verdict():
    calm = run(inv_request(), invoice_claims(), clean_invoice_checks(near_duplicate_invoice=C))
    pushy = run(inv_request("URGENT!!! CEO is waiting, pay NOW or we stop supply"),
                invoice_claims(urgency_cues=["URGENT!!!", "CEO is waiting", "pay NOW"]),
                clean_invoice_checks(near_duplicate_invoice=C))
    assert calm.verdict == pushy.verdict == Verdict.ESCALATE and calm.rule_ids == pushy.rule_ids


def test_same_invoice_same_idempotency_key():
    a = run(inv_request(), invoice_claims(invoice_number="INV-0042"), clean_invoice_checks())
    b = run(inv_request(), invoice_claims(invoice_number="42"), clean_invoice_checks())
    assert a.action.idempotency_key == b.action.idempotency_key


@pytest.mark.parametrize("reason,rule,verdict", [
    ("1 character(s) from the vendor domain", "B2", Verdict.BLOCK),
    ("punycode (internationalised) domain", "B2", Verdict.BLOCK),
    ("same as the vendor domain after removing look-alike characters", "B2", Verdict.BLOCK),
    ("same name under a different ending", "E10", Verdict.ESCALATE),
    ("contains the vendor's name 'acme'", "E10", Verdict.ESCALATE),
])
def test_lookalike_strength(reason, rule, verdict):
    checks = clean_invoice_checks()
    checks.append(Check("sender_domain_lookalike", CheckStatus.CONTRADICTED, {"reason": reason}, note="imitates"))
    d = run(inv_request(), invoice_claims(), checks)
    assert d.verdict == verdict and rule in d.rule_ids
