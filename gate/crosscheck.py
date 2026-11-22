"""Second reading of the fields that move money.

The extractor is the one place a model still shapes the outcome. IFSC, GSTIN, account numbers and
invoice numbers have strict formats, so we read them a second way with fixed patterns, from the same
visible (sanitised) text. If the model returns a value that is not actually in the text, the two
readings disagree: the check is CONTRADICTED and the policy escalates (E9). "Disagreement goes to a
person", applied to the money fields.

A field the model left empty is not a disagreement (missing facts are handled by the policy).
A 1-4 digit "account ending 7777" is a reference to the vendor master, not a full number; skipped here.
"""
from __future__ import annotations

import re

from gate.contracts import Check, CheckStatus, Claims, Source
from gate.keys import norm_invoice_number

NAME = "extraction_crosscheck"
IFSC_RE = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")
GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")
ACCOUNT_RE = re.compile(r"(?<![\dA-Za-z])\d(?:[ -]?\d){8,17}(?![\dA-Za-z])")  # 9-18 digits, spaces/dashes allowed


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def readings(visible_text: str) -> dict[str, set[str]]:
    up = visible_text.upper()
    return {
        "ifsc": set(IFSC_RE.findall(up)),
        "gstin": set(GSTIN_RE.findall(up)),
        "account": {_digits(m) for m in ACCOUNT_RE.findall(visible_text)},
    }


def _invoice_in_text(inv: str, visible_text: str) -> bool:
    flat = re.sub(r"\s+", "", visible_text).lower()
    if re.sub(r"\s+", "", inv).lower() in flat:
        return True
    # the same number in another layout ("INV/2026-27/0042" vs "2026-27-42") still counts as present
    target = norm_invoice_number(inv)
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9/\-#.]*\d[A-Za-z0-9/\-#.]*", visible_text)
    return bool(target) and any(norm_invoice_number(t.strip(".-/#")) == target for t in tokens)


def crosscheck(claims: Claims, visible_text: str) -> Check:
    r = readings(visible_text)
    found, bad = [], []

    def compare(field: str, value, present: bool, shown: str):
        if value in (None, ""):
            return
        (found if present else bad).append(f"{field}={shown}")

    if claims.pay_to_ifsc:
        v = claims.pay_to_ifsc.strip().upper()
        compare("pay_to_ifsc", v, v in r["ifsc"], v)
    if claims.vendor_gstin:
        v = claims.vendor_gstin.strip().upper()
        compare("vendor_gstin", v, v in r["gstin"], v)
    acct = _digits(claims.pay_to_account or "")
    if len(acct) > 4:
        compare("pay_to_account", acct, acct in r["account"], f"…{acct[-4:]}")
    if claims.invoice_number:
        compare("invoice_number", claims.invoice_number, _invoice_in_text(claims.invoice_number, visible_text),
                claims.invoice_number)

    src = [Source(kind="local", ref="gate/crosscheck.py (fixed-format second reading of the visible text)",
                  excerpt=", ".join(found + bad)[:300] or None)]
    if bad:
        return Check(NAME, CheckStatus.CONTRADICTED,
                     {"not_in_text": bad, "confirmed": found},
                     src, note=f"The model's reading of {', '.join(b.split('=')[0] for b in bad)} does not appear "
                               f"in the email text ({'; '.join(bad)}). Check the original before acting.")
    return Check(NAME, CheckStatus.VERIFIED, {"confirmed": found}, src,
                 note=("Money fields confirmed in the text by a second, fixed-format reading: " + ", ".join(found))
                 if found else "No money fields to cross-check.")
