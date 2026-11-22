from gate.keys import (account_hash, financial_year, idempotency_key, invoice_key, norm_invoice_number,
                       payment_fingerprint)


def test_invoice_number_variants_collapse():
    forms = ["INV/2026-27/0042", "inv 2026 27 42", "INV-2O26-27-042", "Invoice No. 2026/27/42", "2026-27-0042"]
    assert {norm_invoice_number(f) for f in forms} == {"2026-27-42"}
    assert norm_invoice_number("INV-0042") == norm_invoice_number("42") == "42"
    assert norm_invoice_number("INV-43") != norm_invoice_number("INV-42")


def test_financial_year():
    assert financial_year("2026-11-22") == "2026-2027"
    assert financial_year("2027-03-31") == "2026-2027"
    assert financial_year("2027-04-01") == "2027-2028"


def test_keys_are_stable():
    k = invoice_key("27aaacr5055k1z7", "INV-0042", "2026-11-20")
    assert k == "27AAACR5055K1Z7|42|2026-2027"
    h = account_hash("1234 5678 9012")
    assert h == account_hash("123456789012") and len(h) == 64
    fp = payment_fingerprint(k, 1250000, h)
    assert idempotency_key(fp) == idempotency_key(fp) and len(idempotency_key(fp)) == 36
    assert idempotency_key(fp) != idempotency_key(payment_fingerprint(k, 1250001, h))
