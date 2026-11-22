"""Policy v1: ordered rules in plain code. OWNER: Krishna.

The decider reads typed Claims and Checks only, never raw email text, so pressure, politeness and
planted notes cannot move it. Precedence: any BLOCK > any ESCALATE > ALLOW. Every rule that fires adds
a Reason naming its rule id and the checks behind it, so a decision can be replayed and explained.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Optional

from gate.contracts import (POLICY_VERSION, BankAccount, Check, CheckStatus, Claims, Decision,
                            PaymentAction, Reason, Request, RequestKind, Vendor, Verdict, action_hash)
from gate.keys import account_hash, idempotency_key, invoice_key, payment_fingerprint

COOLING_OFF_BUSINESS_DAYS = 3

C, U, V = CheckStatus.CONTRADICTED, CheckStatus.UNVERIFIABLE, CheckStatus.VERIFIED

# rule id -> one-line description (shown in the UI and README)
RULES = {
    "B1": "Duplicate invoice: same GSTIN, invoice number and financial year already seen",
    "B2": "Sender domain imitates the vendor's domain, or was registered under 90 days ago",
    "B3": "The requester has left the vendor",
    "B4": "The pay-to account belongs to another vendor",
    "B5": "GSTIN fails its checksum or does not match the vendor record",
    "B6": "Pay-to account is not the vendor's verified account, or its details are invalid",
    "E1": "Bank or contact detail change: never applied from email alone; payments to this vendor held",
    "E2": "First payment to an account added within the cooling-off period",
    "E3": "New account's holder name could not be confirmed",
    "E4": "Possible duplicate invoice",
    "E5": "No matching purchase order or goods receipt",
    "E6": "A fact the decision needs could not be verified",
    "E7": "Pay-to country differs from the vendor's country",
    "E8": "Amount above the vendor's payment limit",
    "E9": "A record contradicts the request",
    "E10": "Sender domain resembles the vendor's name but is not a close imitation",
    "A1": "Everything checked out within policy",
}


def _business_days_between(start: date, end: date) -> int:
    days, d = 0, start
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5:
            days += 1
    return days


_COUNTRY_ALIASES = {"INDIA": "IN", "BHARAT": "IN", "IND": "IN", "UNITED STATES": "US", "USA": "US",
                    "UNITED KINGDOM": "GB", "UK": "GB", "CHINA": "CN", "POLAND": "PL", "UAE": "AE"}


def _country(c: str) -> str:
    c = c.strip().upper()
    return _COUNTRY_ALIASES.get(c, c)


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _pay_to_account(claims: Claims, vendor: Vendor) -> tuple[Optional[BankAccount], bool]:
    """The vendor-master account this payment would go to, and whether the text named a different one.

    Money only ever goes to a vendor-master account. If the text names an account, it must match one.
    """
    verified = [a for a in vendor.bank_accounts if a.verified_at]
    digits = re.sub(r"\D", "", claims.pay_to_account or "")
    if claims.pay_to_account and len(digits) <= 4:
        # "account ending 7777": only a reference to the master; it must match exactly one account there
        hits = [a for a in vendor.bank_accounts if digits and a.account_last4 == digits.zfill(4)[-4:]
                and (not claims.pay_to_ifsc or a.ifsc.upper() == claims.pay_to_ifsc.upper())]
        return (hits[0], False) if len(hits) == 1 else (None, True)
    if claims.pay_to_account:
        h = account_hash(claims.pay_to_account)
        for a in vendor.bank_accounts:
            if a.account_hash == h:
                return a, False
        return None, True
    return (verified[0] if verified else None), False


class _Ctx:
    def __init__(self, request: Request, claims: Claims, vendor: Vendor, checks: list[Check], today: date):
        self.request, self.claims, self.vendor, self.today = request, claims, vendor, today
        self.by_name = {c.name: c for c in checks}
        self.reasons: list[Reason] = []
        kind = request.kind if isinstance(request.kind, RequestKind) else RequestKind(request.kind)
        self.is_change = claims.requested_change in ("bank_change", "contact_change") or kind == RequestKind.BANK_CHANGE
        self.is_payment = not self.is_change and (kind == RequestKind.INVOICE or claims.requested_change == "payment")

    def status(self, name: str) -> Optional[CheckStatus]:
        c = self.by_name.get(name)
        return CheckStatus(c.status) if c else None

    def note(self, name: str) -> str:
        c = self.by_name.get(name)
        return (c.note or "") if c else ""

    def add(self, rule_id: str, text: str, *check_names: str) -> None:
        self.reasons.append(Reason(rule_id, text, list(check_names)))


# ----------------------------------------------------------------------------------------- rules

WEAK_LOOKALIKE_REASONS = ("same name under a different ending", "contains the vendor's name")


def _strong_lookalike(check) -> bool:
    """Punycode, look-alike characters or 1-2 edits from the vendor domain: BLOCK. Weak signals escalate.
    A lookalike check without a recognisable reason counts as strong (fail closed)."""
    value = check.value or {}
    if value.get("strength") in ("strong", "weak"):  # set by the check itself
        return value["strength"] == "strong"
    reason = str(value.get("reason") or "")
    return not any(reason.startswith(w) for w in WEAK_LOOKALIKE_REASONS)


def _block_rules(x: _Ctx) -> None:
    if x.status("duplicate_invoice") == C:
        x.add("B1", f"{RULES['B1']}. {x.note('duplicate_invoice')}".strip(), "duplicate_invoice")
    if x.status("domain_age_days") == C:
        x.add("B2", f"{RULES['B2']}. {x.note('domain_age_days')}".strip(), "domain_age_days")
    if x.status("sender_domain_lookalike") == C:
        if _strong_lookalike(x.by_name["sender_domain_lookalike"]):
            x.add("B2", f"{RULES['B2']}. {x.note('sender_domain_lookalike')}".strip(), "sender_domain_lookalike")
        else:  # weak signal (same name, other ending; contains the name): could be a genuine sister domain
            x.add("E10", f"{RULES['E10']}. {x.note('sender_domain_lookalike')}".strip(), "sender_domain_lookalike")
    if x.status("requester_departed") == C:
        x.add("B3", f"{RULES['B3']}. {x.note('requester_departed')}".strip(), "requester_departed")
    if x.status("account_shared_across_vendors") == C:
        x.add("B4", f"{RULES['B4']}. {x.note('account_shared_across_vendors')}".strip(), "account_shared_across_vendors")
    for name in ("gstin_checksum", "gstin_matches_vendor"):
        if x.status(name) == C:
            x.add("B5", f"{RULES['B5']}. {x.note(name)}".strip(), name)
    if x.is_payment:
        _, named_other = _pay_to_account(x.claims, x.vendor)
        if named_other or x.status("account_on_vendor_master") == C:
            x.add("B6", f"{RULES['B6']}: the text asks for payment to an account that is not on the vendor "
                        f"master. Pay only to the verified account on file.", "account_on_vendor_master")
        for name in ("ifsc_valid", "penny_drop_name_match"):
            if x.status(name) == C:
                x.add("B6", f"{RULES['B6']}. {x.note(name)}".strip(), name)


def _escalate_rules(x: _Ctx) -> None:
    cl, v = x.claims, x.vendor
    if x.is_change:
        who = cl.requester_name or "an unnamed sender"
        x.add("E1", f"{RULES['E1']}. {who} asks to change {cl.requested_change.replace('_', ' ')}. "
                    "Confirm by calling back on a number recorded before this request.")
        if x.status("penny_drop_name_match") in (U, None) and cl.pay_to_account:
            x.add("E3", f"{RULES['E3']}. {x.note('penny_drop_name_match') or 'Penny-drop not run.'}",
                  "penny_drop_name_match")
        for name, missing in (("sender_domain_matches_vendor", "the sender's domain"),
                              ("requester_current_role", "the requester's current role at the vendor")):
            if x.status(name) in (U, None):
                x.add("E6", f"Cannot verify {missing}. {x.note(name)}".strip(), name)

    if x.is_payment:
        if cl.amount_inr is None:
            x.add("E6", "Cannot read the amount payable from the invoice.")
        if not cl.invoice_number:
            x.add("E6", "Cannot read the invoice number, so duplicates cannot be ruled out.")
        acct, named_other = _pay_to_account(cl, v)
        if acct is None and not named_other:
            if v.bank_accounts:
                x.add("E3", f"{RULES['E3']}: the vendor's account on file was never verified.")
            else:
                x.add("E6", "The vendor has no bank account on file.")
        if acct is not None:
            added = _parse_date(acct.added_at)
            if added is None or _business_days_between(added, x.today) < COOLING_OFF_BUSINESS_DAYS:
                x.add("E2", f"{RULES['E2']} ({COOLING_OFF_BUSINESS_DAYS} business days); account ending "
                            f"{acct.account_last4} was added {acct.added_at or 'at an unknown date'}.")
            if not acct.verified_at:
                x.add("E3", f"{RULES['E3']}: account ending {acct.account_last4} was never verified.")
        if x.status("near_duplicate_invoice") == C:
            x.add("E4", f"{RULES['E4']}. {x.note('near_duplicate_invoice')}".strip(), "near_duplicate_invoice")
        if x.status("po_match") in (C, U, None):
            x.add("E5", f"{RULES['E5']}. {x.note('po_match')}".strip(), "po_match")
        for name, missing in (("duplicate_invoice", "whether this invoice was already paid"),
                              ("account_on_vendor_master", "the pay-to account against the vendor master")):
            if x.status(name) in (U, None):
                x.add("E6", f"Cannot verify {missing}. {x.note(name)}".strip(), name)
        if v.gstin and x.status("gstin_checksum") in (U, None):
            x.add("E6", f"Cannot verify the GSTIN. {x.note('gstin_checksum')}".strip(), "gstin_checksum")
        if cl.pay_to_country and _country(cl.pay_to_country) != _country(v.country):
            x.add("E7", f"{RULES['E7']}: {cl.pay_to_country} vs {v.country}.")
        if cl.amount_inr is not None and cl.amount_inr > v.per_payment_limit_inr:
            x.add("E8", f"{RULES['E8']}: Rs {cl.amount_inr:,.2f} > Rs {v.per_payment_limit_inr:,.2f}.")

    if not x.is_change and not x.is_payment:
        x.add("E6", "No payment or change request could be identified in the text.")

    # any contradiction not already used by a BLOCK rule still stops automatic action
    used = {n for r in x.reasons for n in r.check_names}
    for name, c in x.by_name.items():
        if CheckStatus(c.status) == C and name not in used:
            x.add("E9", f"{RULES['E9']}: {name}. {c.note}".strip(), name)
    # unverifiable sender checks on a payment are worth surfacing too (but they only escalate)
    for name in ("sender_domain_matches_vendor", "requester_current_role", "vendor_active"):
        if x.is_payment and x.status(name) == U and name not in used:
            x.add("E6", f"Cannot verify {name.replace('_', ' ')}. {x.note(name)}".strip(), name)


# -------------------------------------------------------------------------------------- decide

def build_action(claims: Claims, vendor: Vendor) -> Optional[PaymentAction]:
    acct, named_other = _pay_to_account(claims, vendor)
    if acct is None or named_other or claims.amount_inr is None or not claims.invoice_number:
        return None
    inv_key = invoice_key(claims.vendor_gstin or vendor.gstin, claims.invoice_number, claims.invoice_date)
    amount_paise = int(round(claims.amount_inr * 100))
    fp = payment_fingerprint(inv_key, amount_paise, acct.account_hash)
    return PaymentAction(vendor_id=vendor.vendor_id, invoice_key=inv_key, amount_paise=amount_paise,
                         account_hash=acct.account_hash, account_last4=acct.account_last4, ifsc=acct.ifsc,
                         idempotency_key=idempotency_key(fp))


def decide(request: Request, claims: Claims, vendor: Vendor, checks: list[Check],
           today: Optional[date] = None) -> Decision:
    x = _Ctx(request, claims, vendor, checks, today or date.today())
    _block_rules(x)
    _escalate_rules(x)

    rule_ids = list(dict.fromkeys(r.rule_id for r in x.reasons))
    if any(r.startswith("B") for r in rule_ids):
        verdict = Verdict.BLOCK
    elif rule_ids:
        verdict = Verdict.ESCALATE
    else:
        verdict = Verdict.ALLOW
        x.add("A1", RULES["A1"] + ".", *[c.name for c in checks if CheckStatus(c.status) == V])
        rule_ids = ["A1"]

    # order reasons: blocks first, then escalations, then allow
    x.reasons.sort(key=lambda r: ("BEA".index(r.rule_id[0]), r.rule_id))
    action = build_action(claims, vendor) if x.is_payment and verdict != Verdict.BLOCK else None
    return Decision(request_id=request.request_id, verdict=verdict, rule_ids=sorted(rule_ids, key=lambda r: ("BEA".index(r[0]), r)),
                    reasons=x.reasons, checks=checks, policy_version=POLICY_VERSION, action=action,
                    action_hash=action_hash(action) if action else None, claims=claims)
