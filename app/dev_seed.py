"""Development seed: synthetic vendors and decisions, so the UI works before the pipeline is wired.
Made-up companies and people only.

    python -m app.dev_seed          # seeds runs/gate.sqlite (or $GATE_DB)
"""
from __future__ import annotations

from gate import executor, keys, store
from gate.contracts import (BankAccount, Check, CheckStatus, Claims, Contact, Decision, PaymentAction, Reason,
                            Request, RequestKind, Source, Vendor, Verdict, action_hash)

OLD_ACCT, NEW_ACCT = "50100012345678", "91827364554321"


def _vendor() -> Vendor:
    return Vendor(
        vendor_id="V-DEMO-ACME", legal_name="Acme Demo Components Pvt Ltd", gstin="29ABCDE1234F1Z5",
        pan="ABCDE1234F", state_code="29", domains=["acme-demo.example"],
        bank_accounts=[BankAccount(ifsc="HDFC0000001", account_last4=OLD_ACCT[-4:],
                                   account_hash=store.hash_account(OLD_ACCT), holder_name="Acme Demo Components",
                                   verified_at="2026-02-01T10:00:00+00:00", added_at="2026-01-15T10:00:00+00:00")],
        contacts=[Contact("Priya Synthetic", "Finance Head", "priya@acme-demo.example", "+91-80-0000-0000",
                          "2026-01-15T10:00:00+00:00")])


def _action(invoice: str, amount_paise: int, acct: str = OLD_ACCT) -> PaymentAction:
    inv_key = keys.invoice_key("29ABCDE1234F1Z5", invoice, "2026-11-20")
    ah = keys.account_hash(acct)
    return PaymentAction(vendor_id="V-DEMO-ACME", invoice_key=inv_key, amount_paise=amount_paise, account_hash=ah,
                         account_last4=acct[-4:], ifsc="HDFC0000001",
                         idempotency_key=keys.idempotency_key(keys.payment_fingerprint(inv_key, amount_paise, ah)))


def _src(kind: str, ref: str, excerpt: str = "", record_id: str | None = None) -> Source:
    return Source(kind=kind, ref=ref, excerpt=excerpt or None, record_id=record_id, request_id="demo-seed")


def seed() -> list[str]:
    store.init_db()
    store.upsert_vendor(_vendor())
    made = []

    # 1. clean invoice -> ALLOW -> paid
    r1 = Request("DEMO-1-clean", RequestKind.INVOICE, "Invoice INV-0042 for Rs 12,500", vendor_id="V-DEMO-ACME",
                 sender_email="billing@acme-demo.example", po={"po_number": "PO-7", "amount_inr": 12500, "grn": True})
    a1 = _action("42", 1250000)
    d1 = Decision(r1.request_id, Verdict.ALLOW, ["A1"], [Reason("A1", "All checks passed.", [])], [
        Check("sender_domain_matches_vendor", CheckStatus.VERIFIED, {"domain": "acme-demo.example"},
              [_src("crustdata", "https://api.crustdata.com/company/identify", "all_domains contains acme-demo.example")]),
        Check("gstin_checksum", CheckStatus.VERIFIED, {"gstin": "29ABCDE1234F1Z5"}, [_src("vendor_master", "local:gstin_checksum")]),
        Check("ifsc_valid", CheckStatus.VERIFIED, {"ifsc": "HDFC0000001", "bank": "HDFC Bank"},
              [_src("ifsc", "https://ifsc.razorpay.com/HDFC0000001")]),
        Check("po_match", CheckStatus.VERIFIED, {"po_number": "PO-7", "po_amount_inr": 12500, "invoice_amount_inr": 12500},
              [_src("history", "local:po/PO-7")]),
        Check("duplicate_invoice", CheckStatus.VERIFIED, {"invoice_key": a1.invoice_key}, [_src("history", "local:history")]),
    ], action=a1, action_hash=action_hash(a1),
        claims=Claims(vendor_name="Acme Demo Components", invoice_number="INV-0042", amount_inr=12500.0,
                      invoice_date="2026-11-20", po_number="PO-7"))

    # 3. lookalike domain bank change -> BLOCK
    r3 = Request("DEMO-3-lookalike", RequestKind.BANK_CHANGE, "Please update our bank account urgently",
                 sender_email="priya@acme-dem0.example", vendor_id="V-DEMO-ACME")
    d3 = Decision(r3.request_id, Verdict.BLOCK, ["B2", "E1"], [
        Reason("B2", "Sender domain acme-dem0.example imitates acme-demo.example (edit distance 1).",
               ["sender_domain_lookalike", "domain_age_days"]),
        Reason("E1", "Bank-change request; the vendor's payments are on hold.", [])], [
        Check("sender_domain_lookalike", CheckStatus.CONTRADICTED,
              {"domain": "acme-dem0.example", "closest": "acme-demo.example", "distance": 1, "reason": "0 -> o"},
              [_src("vendor_master", "local:lookalike", "vendor domains: acme-demo.example")]),
        Check("domain_age_days", CheckStatus.CONTRADICTED, {"domain": "acme-dem0.example", "age_days": 6},
              [_src("rdap", "https://rdap.org/domain/acme-dem0.example", "registration 2026-11-16")]),
        Check("requester_current_role", CheckStatus.VERIFIED, {"name": "Priya Synthetic", "title": "Finance Head"},
              [_src("crustdata", "https://api.crustdata.com/person/search", record_id="p-demo-1")]),
    ], claims=Claims(requested_change="bank_change", requester_name="Priya Synthetic", requester_role="Finance Head",
                     pay_to_ifsc="ICIC0000999", pay_to_account=NEW_ACCT, urgency_cues=["urgently", "today"]))

    # 5. genuine bank change -> ESCALATE (waits for a person)
    r5 = Request("DEMO-5-bankchange", RequestKind.BANK_CHANGE, "New bank details attached, letter on letterhead",
                 sender_email="priya@acme-demo.example", vendor_id="V-DEMO-ACME")
    a5 = _action("57", 4800000, NEW_ACCT)
    d5 = Decision(r5.request_id, Verdict.ESCALATE, ["E1", "E2"], [
        Reason("E1", "Bank-change request: a person must approve after a call-back on the number on file.", []),
        Reason("E2", "First payment to an account added today.", ["account_on_vendor_master"])], [
        Check("sender_domain_matches_vendor", CheckStatus.VERIFIED, {"domain": "acme-demo.example"},
              [_src("crustdata", "https://api.crustdata.com/company/identify")]),
        Check("requester_current_role", CheckStatus.VERIFIED, {"name": "Priya Synthetic", "title": "Finance Head",
                                                                "updated_at": "2026-11-10"},
              [_src("crustdata", "https://api.crustdata.com/person/search", record_id="p-demo-1")]),
        Check("ifsc_valid", CheckStatus.VERIFIED, {"ifsc": "ICIC0000999"}, [_src("ifsc", "https://ifsc.razorpay.com/ICIC0000999")]),
        Check("penny_drop_name_match", CheckStatus.UNVERIFIABLE, {}, [_src("penny_drop", "simulated")],
              note="Penny drop not run (simulated in test mode)."),
    ], action=a5, action_hash=action_hash(a5),
        claims=Claims(requested_change="bank_change", pay_to_ifsc="ICIC0000999", pay_to_account=NEW_ACCT,
                      pay_to_holder="Acme Demo Components", invoice_number="INV-57", amount_inr=48000.0))

    # 6. small vendor, cannot verify -> ESCALATE
    r6 = Request("DEMO-6-unknown-requester", RequestKind.INVOICE, "Invoice 91", vendor_id="V-DEMO-ACME",
                 sender_email="accounts@acme-demo.example")
    a6 = _action("91", 310000)
    d6 = Decision(r6.request_id, Verdict.ESCALATE, ["E6"], [
        Reason("E6", "Cannot verify the requester; call back on the number on file.", ["requester_current_role"])], [
        Check("requester_current_role", CheckStatus.UNVERIFIABLE, {}, [_src("crustdata", "https://api.crustdata.com/person/search")],
              note="No indexed people for this vendor. Call back on the number on file."),
    ], action=a6, action_hash=action_hash(a6), claims=Claims(invoice_number="91", amount_inr=3100.0))

    for r, d in ((r1, d1), (r3, d3), (r5, d5), (r6, d6)):
        if store.get_decision_row(r.request_id):
            continue
        store.save_request(r, d.claims)
        store.save_decision(d)
        made.append(r.request_id)
    if "DEMO-1-clean" in made:
        executor.pay(d1)
    return made


if __name__ == "__main__":
    print("seeded:", seed())
