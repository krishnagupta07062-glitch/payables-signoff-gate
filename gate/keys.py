"""Shared keys. Everyone must use these, so duplicates and idempotency agree.

- invoice_key: GSTIN | normalised invoice number | Indian financial year. CGST Rule 46 makes the
  invoice number unique per supplier per financial year, so a repeat of this key is a duplicate.
- payment_fingerprint / idempotency_key: same invoice + amount + account -> same key, on every retry.
- account_hash: HMAC of the full account number with ACCOUNT_HASH_KEY; the number itself is never stored.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import unicodedata
import uuid
from datetime import date

NAMESPACE = uuid.UUID("6f1c2a4e-9b1d-4c33-8e0a-5a7d2b9c0f11")


def norm_invoice_number(s: str | None) -> str:
    """'INV/2026-27/0042', 'inv 2026 27 42' and 'INV-2O26-27-042' all -> '2026-27-42'.

    Upper-case, strip a leading INV/BILL-style prefix, drop separators, read O/I/L as 0/1 inside digit
    runs, and strip leading zeros of each digit run.
    """
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s).upper().strip()
    s = re.sub(r"^(?:TAX\s*INVOICE|INVOICE|INV|BILL)\s*(?:NO\.?|NUMBER|#)?\s*[:#.\-/ ]*", "", s)
    tokens = [t for t in re.split(r"[^A-Z0-9]+", s) if t]
    out = []
    for t in tokens:
        if re.search(r"\d", t):  # OCR-style confusions only inside numeric tokens
            t = t.translate(str.maketrans("OIL", "011"))
        if t.isdigit():
            t = t.lstrip("0") or "0"
        out.append(t)
    return "-".join(out)


def financial_year(d: date | str | None) -> str:
    if d is None:
        return "FY?"
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    return f"{d.year}-{d.year + 1}" if d.month >= 4 else f"{d.year - 1}-{d.year}"


def invoice_key(gstin: str | None, invoice_number: str | None, invoice_date: date | str | None) -> str:
    return f"{(gstin or 'NOGSTIN').upper()}|{norm_invoice_number(invoice_number)}|{financial_year(invoice_date)}"


def account_hash(account_number: str) -> str:
    key = os.environ.get("ACCOUNT_HASH_KEY", "dev-only-account-hash-key").encode()
    digits = re.sub(r"\D", "", account_number or "")
    return hmac.new(key, digits.encode(), hashlib.sha256).hexdigest()


def payment_fingerprint(inv_key: str, amount_paise: int, acct_hash: str) -> str:
    return f"{inv_key}|{int(amount_paise)}|{acct_hash}"


def idempotency_key(fingerprint: str) -> str:
    """UUIDv5: 36 characters, within RazorpayX's 4-36 limit. Never includes an attempt number."""
    return str(uuid.uuid5(NAMESPACE, fingerprint))
