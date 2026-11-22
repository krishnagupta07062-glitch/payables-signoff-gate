"""Shared types for the Payables Sign-Off Gate.

FROZEN CONTRACT: all three workstreams code against these types. Only Krishna (core) changes this
file, and only after telling the team. Adding an optional field with a default is safe; renaming or
removing a field is not.

Flow:  Request --extract--> Claims --verifiers.run_all--> [Check] --policy.decide--> Decision
       Decision(ALLOW) --executor--> PaymentAction paid exactly once.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

POLICY_VERSION = "policy-v1"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------------------------- enums

class Verdict(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"


class CheckStatus(str, Enum):
    VERIFIED = "VERIFIED"          # a record confirms the claim
    CONTRADICTED = "CONTRADICTED"  # a record contradicts the claim
    UNVERIFIABLE = "UNVERIFIABLE"  # not found, stale, conflicting, timed out, or errored: never a pass


class RequestKind(str, Enum):
    INVOICE = "invoice"            # an invoice to pay
    BANK_CHANGE = "bank_change"    # a request to change a vendor's bank details
    EMAIL = "email"                # anything else; the extractor decides what it asks for


# Check names the policy reads. Verifiers must use exactly these names.
# value-dict keys each check should fill are listed after the name.
CHECK_NAMES = {
    "sender_domain_matches_vendor":   "VERIFIED if sender domain is in the vendor's all_domains. value: domain, crustdata_company_id",
    "sender_domain_lookalike":        "CONTRADICTED if the domain imitates a vendor domain. value: domain, closest, distance, reason",
    "domain_age_days":                "VERIFIED if age >= 90 days, CONTRADICTED if younger. value: domain, age_days, registered_at",
    "vendor_active":                  "VERIFIED if the company record is active and its site is live. value: status, updated_at, site_live",
    "requester_current_role":         "VERIFIED if the requester currently works at the vendor in the claimed role. value: name, title, start_date, updated_at",
    "requester_departed":             "CONTRADICTED if the requester appears only in past roles at the vendor. value: name, end_date, current_employer",
    "gstin_checksum":                 "VERIFIED if the GSTIN check digit is valid. value: gstin",
    "gstin_matches_vendor":           "VERIFIED if the GSTIN's PAN and state match the vendor record. value: gstin, pan, state_code",
    "gstin_exists":                   "VERIFIED if the GST portal knows the GSTIN. value: gstin, hsn_codes",
    "ifsc_valid":                     "VERIFIED if the IFSC resolves to a branch. value: ifsc, bank, branch, imps, neft, rtgs",
    "account_on_vendor_master":       "VERIFIED if the pay-to account is a verified account on the vendor record. value: account_last4",
    "account_shared_across_vendors":  "CONTRADICTED if the pay-to account belongs to another vendor. value: account_last4, other_vendor_ids",
    "penny_drop_name_match":          "value: score (0-100), registered_name. VERIFIED >= 90, UNVERIFIABLE 60-89 or failed, CONTRADICTED < 60",
    "duplicate_invoice":              "CONTRADICTED if same GSTIN + normalised invoice number + financial year was seen. value: invoice_key, prior_request_id",
    "near_duplicate_invoice":         "CONTRADICTED if a fuzzy match exists. value: score, prior_request_id, reason",
    "po_match":                       "VERIFIED if a PO/goods receipt matches within tolerance. value: po_number, po_amount_inr, invoice_amount_inr",
    "vendor_news":                    "CONTRADICTED if recent news signals acquisition/rebrand/fraud warning. value: items[{title, date, url}]",
}


# --------------------------------------------------------------------------------------- evidence

@dataclass
class Source:
    kind: str                         # crustdata | rdap | ifsc | gst_portal | vendor_master | history | penny_drop | web
    ref: str                          # endpoint path or URL that a person can open
    retrieved_at: str = field(default_factory=now_iso)
    request_id: Optional[str] = None  # e.g. Crustdata X-Request-Id
    record_id: Optional[str] = None   # e.g. crustdata_company_id / person id (never a raw profile)
    record_date: Optional[str] = None # date the record itself states (updated_at, publish date)
    excerpt: Optional[str] = None     # the exact field or passage that states the claim


@dataclass
class Check:
    name: str                         # one of CHECK_NAMES
    status: CheckStatus
    value: dict = field(default_factory=dict)
    sources: list[Source] = field(default_factory=list)
    credits: float = 0.0              # credits this check spent (0 when cached)
    note: str = ""                    # human-readable; for UNVERIFIABLE, name what is missing


# --------------------------------------------------------------------------- trusted base record

@dataclass
class BankAccount:
    ifsc: str
    account_last4: str
    account_hash: str                 # keyed hash of the full number; the full number is never stored
    holder_name: str
    verified_at: Optional[str] = None # penny-drop or manual verification time
    added_at: Optional[str] = None


@dataclass
class Contact:
    name: str
    role: str
    email: str
    phone_on_file: Optional[str] = None
    recorded_at: Optional[str] = None # contacts recorded before a request are the only callback channel


@dataclass
class Vendor:
    vendor_id: str
    legal_name: str
    gstin: Optional[str] = None
    pan: Optional[str] = None
    state_code: Optional[str] = None
    country: str = "IN"
    domains: list[str] = field(default_factory=list)
    crustdata_company_id: Optional[int] = None
    bank_accounts: list[BankAccount] = field(default_factory=list)
    contacts: list[Contact] = field(default_factory=list)
    per_payment_limit_inr: float = 500000.0
    per_day_limit_inr: float = 1000000.0
    created_at: Optional[str] = None


# ------------------------------------------------------------------------------------------ input

@dataclass
class Request:
    request_id: str
    kind: RequestKind
    raw_text: str                     # email body / invoice text, untrusted
    sender_email: Optional[str] = None
    sender_display: Optional[str] = None
    reply_to: Optional[str] = None
    received_at: str = field(default_factory=now_iso)
    vendor_id: Optional[str] = None   # set when the request arrives on a known vendor thread
    attachments: list[str] = field(default_factory=list)
    po: Optional[dict] = None         # {po_number, amount_inr, grn: bool} from the buyer's own system


@dataclass
class Claims:
    """What the untrusted text claims. The extractor fills it; it never decides."""
    vendor_name: Optional[str] = None
    vendor_gstin: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None      # ISO date
    amount_inr: Optional[float] = None
    po_number: Optional[str] = None
    pay_to_ifsc: Optional[str] = None
    pay_to_account: Optional[str] = None    # full number as written; hash it before storing
    pay_to_holder: Optional[str] = None
    pay_to_country: Optional[str] = None
    requester_name: Optional[str] = None
    requester_role: Optional[str] = None
    requested_change: str = "none"          # none | bank_change | contact_change | payment
    urgency_cues: list[str] = field(default_factory=list)  # logged only; never used to relax a rule
    language: Optional[str] = None
    removed_hidden_content: list[str] = field(default_factory=list)  # from sanitize
    extraction_notes: str = ""


# ----------------------------------------------------------------------------------------- output

@dataclass
class PaymentAction:
    vendor_id: str
    invoice_key: str                  # GSTIN|normalised invoice no|financial year
    amount_paise: int
    account_hash: str
    account_last4: str
    ifsc: str
    idempotency_key: str              # uuid5 of the invoice fingerprint; same invoice -> same key
    purpose: str = "vendor bill"


@dataclass
class Reason:
    rule_id: str                      # e.g. B2, E6, A1
    text: str
    check_names: list[str] = field(default_factory=list)


@dataclass
class Decision:
    request_id: str
    verdict: Verdict
    rule_ids: list[str]
    reasons: list[Reason]
    checks: list[Check]
    policy_version: str = POLICY_VERSION
    action: Optional[PaymentAction] = None
    action_hash: Optional[str] = None  # action_hash(action); the executor recomputes it
    decided_at: str = field(default_factory=now_iso)
    claims: Optional[Claims] = None


# ---------------------------------------------------------------------------------------- helpers

def to_dict(obj: Any) -> Any:
    """Dataclasses and enums to plain JSON-able structures."""
    if is_dataclass(obj):
        return {k: to_dict(v) for k, v in asdict(obj).items()}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_dict(v) for v in obj]
    return obj


def canonical_json(obj: Any) -> str:
    """Sorted keys, no spaces, UTF-8 kept: stable bytes for hashing (RFC 8785 in spirit)."""
    return json.dumps(to_dict(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def action_hash(action: PaymentAction) -> str:
    return hashlib.sha256(canonical_json(action).encode("utf-8")).hexdigest()


def check_by_name(checks: list[Check], name: str) -> Optional[Check]:
    for c in checks:
        if c.name == name:
            return c
    return None
