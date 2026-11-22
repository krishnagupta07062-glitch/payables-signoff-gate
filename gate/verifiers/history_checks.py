"""Checks against our own records: vendor master, payment history, purchase orders. OWNER: Lavya.

No network. `history` rows come from store.history_for(); each has at least request_id, vendor_id,
invoice_key, invoice_number, amount_inr, invoice_date, account_hash, verdict. Keys come from gate/keys.py
so duplicates here agree byte for byte with Ayush's payouts.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from rapidfuzz import fuzz

from gate.contracts import Check, Claims, Request, Vendor
from gate.keys import account_hash, invoice_key, norm_invoice_number
from gate.verifiers.common import C, U, V, check, norm_company, src, unverifiable

NEAR_DUP_SCORE = 90
NEAR_DUP_AMOUNT_PCT = 0.5
NEAR_DUP_DAYS = 10
PO_TOLERANCE_PCT = 2.0


def _hist_source(n: int) -> list:
    return [src("history", "store.history_for()", excerpt=f"{n} prior requests compared")]


def _seen(row: dict) -> bool:
    """A prior request counts unless it was itself stopped (BLOCK verdict or REJECTED by a person)."""
    if str(row.get("state") or "").upper() in ("PAID", "APPROVED"):
        return True
    return str(row.get("verdict") or "").upper() != "BLOCK" and str(row.get("state") or "").upper() != "REJECTED"


def _date(s) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _gstin(claims: Claims, vendor: Vendor) -> Optional[str]:
    return claims.vendor_gstin or vendor.gstin


def duplicate_invoice(request: Request, claims: Claims, vendor: Vendor, history: Optional[list[dict]]) -> Check:
    name = "duplicate_invoice"
    if history is None:
        return unverifiable(name, "Payment history unavailable; cannot rule out a duplicate.")
    if not claims.invoice_number:
        return unverifiable(name, "No invoice number on the invoice; cannot rule out a duplicate.", _hist_source(len(history)))
    key = invoice_key(_gstin(claims, vendor), claims.invoice_number, claims.invoice_date)
    for row in history:
        if row.get("request_id") == request.request_id or not _seen(row):
            continue
        if row.get("invoice_key") == key:
            s = _hist_source(len(history))
            s[0].record_id = str(row.get("request_id"))
            s[0].excerpt = f"invoice_key {key} on request {row.get('request_id')} ({row.get('verdict')})"
            return check(name, C, f"Invoice {claims.invoice_number} was already seen as {row.get('invoice_number')} "
                                  f"on request {row.get('request_id')} (same GSTIN, number and financial year).",
                         {"invoice_key": key, "prior_request_id": row.get("request_id")}, s)
    return check(name, V, f"No earlier invoice with key {key}.", {"invoice_key": key, "prior_request_id": None},
                 _hist_source(len(history)))


def near_duplicate_invoice(request: Request, claims: Claims, vendor: Vendor,
                           history: Optional[list[dict]]) -> Check:
    """CONTRADICTED (policy E4, escalate) when an earlier bill from the same vendor looks like this one re-sent:
    - a similar invoice number (ratio >= 90) AND the same amount (+-0.5%), or an amount we can't read; or
    - the same amount (+-0.5%) within 10 days, whatever the number.
    A similar number with a different amount is the vendor's next bill, not a duplicate.
    """
    name = "near_duplicate_invoice"
    if history is None:
        return unverifiable(name, "Payment history unavailable.")
    if not claims.invoice_number and claims.amount_inr is None:
        return unverifiable(name, "No invoice number or amount to compare.", _hist_source(len(history)))
    key = invoice_key(_gstin(claims, vendor), claims.invoice_number, claims.invoice_date)
    mine = norm_invoice_number(claims.invoice_number)
    d0 = _date(claims.invoice_date)
    best = None
    for row in history:
        if row.get("request_id") == request.request_id or not _seen(row):
            continue
        if row.get("invoice_key") == key:
            continue  # an exact duplicate is duplicate_invoice's job (BLOCK)
        same_vendor = row.get("vendor_id") == vendor.vendor_id
        theirs = norm_invoice_number(row.get("invoice_number"))
        amt, ramt = claims.amount_inr, row.get("amount_inr")
        # None when either amount is unknown: then we can't rule a re-sent bill out, so stay cautious
        same_amount = None if not (amt and ramt) else abs(amt - float(ramt)) <= float(ramt) * NEAR_DUP_AMOUNT_PCT / 100
        if same_vendor and mine and theirs:
            score = fuzz.ratio(mine, theirs)
            # A similar number alone is normal: a vendor's next bill is INV/2026-27/0043 after 0042 (ratio 90).
            # It is a likely re-send only if the amount matches too (or an amount is unknown).
            if score >= NEAR_DUP_SCORE and same_amount is not False and (best is None or score > best["score"]):
                best = {"score": round(score, 1), "prior_request_id": row.get("request_id"),
                        "reason": f"invoice number {claims.invoice_number} is {score:.0f}% similar to "
                                  f"{row.get('invoice_number')}"
                                  + (" and the amount is the same" if same_amount else " (amount unknown)")}
        d1 = _date(row.get("invoice_date"))
        if same_vendor and same_amount and d0 and d1 and abs((d0 - d1).days) <= NEAR_DUP_DAYS:
            if best is None:
                best = {"score": 100.0, "prior_request_id": row.get("request_id"),
                        "reason": f"same vendor and amount (Rs {float(ramt):,.2f}) within {abs((d0 - d1).days)} days "
                                  f"(invoice {row.get('invoice_number')})"}
    s = _hist_source(len(history))
    if best:
        s[0].record_id = str(best["prior_request_id"])
        return check(name, C, f"Possible duplicate of request {best['prior_request_id']}: {best['reason']}.", best, s)
    return check(name, V, "No similar earlier invoice from this vendor.", {"score": None, "prior_request_id": None,
                                                                           "reason": "none"}, s)


def _vendor_master_source(vendor: Vendor) -> list:
    accts = ", ".join(f"…{a.account_last4} ({'verified' if a.verified_at else 'unverified'})" for a in vendor.bank_accounts)
    return [src("vendor_master", f"vendor:{vendor.vendor_id}", excerpt=f"accounts on file: {accts or 'none'}")]


def account_on_vendor_master(claims: Claims, vendor: Vendor) -> Check:
    name = "account_on_vendor_master"
    s = _vendor_master_source(vendor)
    if claims.pay_to_account:
        h = account_hash(claims.pay_to_account)
        last4 = "".join(ch for ch in claims.pay_to_account if ch.isdigit())[-4:]
        for a in vendor.bank_accounts:
            if a.account_hash == h:
                if a.verified_at:
                    return check(name, V, f"Account ending {last4} is the vendor's verified account on file.",
                                 {"account_last4": last4}, s)
                return unverifiable(name, f"Account ending {last4} is on file but was never verified.", s,
                                    {"account_last4": last4})
        return check(name, C, f"Account ending {last4} is not on the vendor master.", {"account_last4": last4}, s)
    verified = [a for a in vendor.bank_accounts if a.verified_at]
    if verified:
        return check(name, V, f"No account named in the text; payment goes to the verified account on file "
                              f"ending {verified[0].account_last4}.", {"account_last4": verified[0].account_last4}, s)
    if vendor.bank_accounts:
        return unverifiable(name, "The vendor's account on file was never verified.", s,
                            {"account_last4": vendor.bank_accounts[0].account_last4})
    return unverifiable(name, "The vendor has no bank account on file.", s)


def account_shared_across_vendors(claims: Claims, vendor: Vendor, history: Optional[list[dict]]) -> Check:
    name = "account_shared_across_vendors"
    if history is None:
        return unverifiable(name, "Payment history unavailable.")
    if claims.pay_to_account:
        h = account_hash(claims.pay_to_account)
        last4 = "".join(ch for ch in claims.pay_to_account if ch.isdigit())[-4:]
    else:
        verified = [a for a in vendor.bank_accounts if a.verified_at] or vendor.bank_accounts
        if not verified:
            return unverifiable(name, "No pay-to account to compare.", _hist_source(len(history)))
        h, last4 = verified[0].account_hash, verified[0].account_last4
    others = sorted({str(r.get("vendor_id")) for r in history
                     if r.get("account_hash") == h and r.get("vendor_id") and r.get("vendor_id") != vendor.vendor_id})
    s = _hist_source(len(history))
    if others:
        s[0].excerpt = f"account …{last4} also used by vendor(s) {', '.join(others)}"
        return check(name, C, f"Account ending {last4} is also used by vendor(s) {', '.join(others)}.",
                     {"account_last4": last4, "other_vendor_ids": others}, s)
    return check(name, V, f"Account ending {last4} is not used by any other vendor.",
                 {"account_last4": last4, "other_vendor_ids": []}, s)


def po_match(request: Request, claims: Claims) -> Check:
    name = "po_match"
    po = request.po or {}
    s = [src("purchase_order", f"po:{po.get('po_number') or 'none'}", excerpt=str(po) if po else None)]
    if not po:
        return unverifiable(name, "No purchase order on file for this invoice.", s)
    po_amt = po.get("amount_inr")
    value = {"po_number": po.get("po_number"), "po_amount_inr": po_amt, "invoice_amount_inr": claims.amount_inr}
    if claims.po_number and po.get("po_number") and \
            norm_invoice_number(claims.po_number) != norm_invoice_number(str(po.get("po_number"))):
        return check(name, C, f"Invoice cites PO {claims.po_number}, but the PO on file is {po.get('po_number')}.", value, s)
    if po_amt is None or claims.amount_inr is None:
        return unverifiable(name, "PO or invoice amount missing; cannot match.", s, value)
    diff_pct = abs(claims.amount_inr - float(po_amt)) / max(float(po_amt), 1.0) * 100
    if diff_pct > PO_TOLERANCE_PCT:
        return check(name, C, f"Invoice amount Rs {claims.amount_inr:,.2f} differs from PO amount Rs {float(po_amt):,.2f} "
                              f"by {diff_pct:.1f}% (tolerance {PO_TOLERANCE_PCT}%).", value, s)
    if po.get("grn") is False:
        return unverifiable(name, f"PO {po.get('po_number')} matches, but no goods receipt is recorded.", s, value)
    return check(name, V, f"Matches PO {po.get('po_number')} (Rs {float(po_amt):,.2f}) within {PO_TOLERANCE_PCT}%.", value, s)


def penny_drop_name_match(claims: Claims, vendor: Vendor) -> Check:
    """SIMULATION: RazorpayX fund-account validation is simulated in test mode, so we compare the claimed
    account holder with the vendor's legal name. Labelled as a simulation in the source."""
    name = "penny_drop_name_match"
    s = [src("penny_drop", "SIMULATED: RazorpayX /v1/fund_accounts/validations (test mode)",
             excerpt="simulated in test mode; holder name compared with vendor legal name")]
    if not claims.pay_to_account:
        acct = next((a for a in vendor.bank_accounts if a.verified_at), None)
        if acct:
            return check(name, V, f"Account on file ending {acct.account_last4} was verified {acct.verified_at}.",
                         {"score": 100, "registered_name": acct.holder_name}, s)
        return unverifiable(name, "No verified account and no new account to validate.", s)
    holder = claims.pay_to_holder
    if not holder:
        return unverifiable(name, "Penny drop (simulated) not possible: no account holder name given.", s,
                            {"score": None, "registered_name": None})
    score = fuzz.token_set_ratio(norm_company(holder), norm_company(vendor.legal_name))
    value = {"score": round(score), "registered_name": holder}
    if score < 60:
        # even the name the sender typed doesn't match the vendor: that alone contradicts the request
        return check(name, C, f"Holder named in the request, '{holder}', does not match '{vendor.legal_name}' "
                              f"({score:.0f}).", value, s)
    # A simulated validation only echoes the name the sender typed, so it can never confirm a new account.
    return unverifiable(name, f"New account's holder not confirmed: penny drop is simulated in test mode (the claimed "
                              f"name '{holder}' scores {score:.0f} against '{vendor.legal_name}'). Confirm with a real "
                              "penny drop or a call back.", s, value)
