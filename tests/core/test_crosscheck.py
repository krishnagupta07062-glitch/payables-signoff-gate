"""Second reading of money fields: the model's value must actually be in the text."""
from gate.contracts import CheckStatus, Claims
from gate.crosscheck import crosscheck

TEXT = """Tax Invoice No: INV/2026-27/0042  GSTIN 09AAACA1234A1ZI
Please pay to A/c 5555 6666 7777, IFSC ICIC0000456. Buyer GSTIN 07AABCB5678C1ZX"""


def test_agreeing_reading_verifies():
    c = crosscheck(Claims(invoice_number="INV/2026-27/0042", vendor_gstin="09AAACA1234A1ZI",
                          pay_to_account="555566667777", pay_to_ifsc="icic0000456"), TEXT)
    assert c.status == CheckStatus.VERIFIED and len(c.value["confirmed"]) == 4


def test_invented_or_misread_account_contradicts():
    c = crosscheck(Claims(pay_to_account="555566667778", pay_to_ifsc="ICIC0000456"), TEXT)
    assert c.status == CheckStatus.CONTRADICTED and "pay_to_account" in c.note
    assert "555566667778" not in c.note  # only the last 4 digits are shown


def test_ifsc_and_gstin_not_in_text_contradict():
    assert crosscheck(Claims(pay_to_ifsc="YESB0000789"), TEXT).status == CheckStatus.CONTRADICTED
    assert crosscheck(Claims(vendor_gstin="09AAACA1234A1ZZ"), TEXT).status == CheckStatus.CONTRADICTED


def test_reformatted_invoice_number_and_last4_reference_are_fine():
    assert crosscheck(Claims(invoice_number="2026-27-42"), TEXT).status == CheckStatus.VERIFIED
    assert crosscheck(Claims(pay_to_account="7777"), TEXT).status == CheckStatus.VERIFIED
    assert crosscheck(Claims(), TEXT).status == CheckStatus.VERIFIED


def test_policy_escalates_on_disagreement():
    from datetime import date
    from gate.pipeline import load_case, load_vendors, request_from_dict, run
    from gate.runbudget import RunBudget
    import os
    os.environ["MOCK"] = "1"
    case = load_case("fixtures/requests/01_calm.json")
    claims = dict(case["mock_claims"], invoice_number="INV/2026-27/0099")  # not in the text
    res = run(request_from_dict(case["request"]), RunBudget(max_credits=1), vendor=load_vendors()["V-ACME"],
              mock_claims=claims, mock_checks=case["mock_checks"], execute=False, today=date(2026, 11, 23))
    assert res.decision.verdict.value == "ESCALATE" and "E9" in res.decision.rule_ids
