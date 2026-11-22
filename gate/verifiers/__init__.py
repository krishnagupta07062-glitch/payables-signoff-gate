"""Verification checks. OWNER: Lavya.

Contract: run_all() never raises. Every check that errors or times out comes back as
Check(status=UNVERIFIABLE, note=<what is missing>). See gate/contracts.py CHECK_NAMES for names.
"""
from __future__ import annotations

from gate.contracts import Check, Claims, Request, Vendor
from gate.runbudget import RunBudget


def run_all(request: Request, claims: Claims, vendor: Vendor, history: list[dict],
            budget: RunBudget) -> list[Check]:
    """Run every relevant check for this request against live sources and the trusted vendor record.

    history: prior requests/decisions for this vendor and others, from store.history_for(); each dict
    has at least request_id, vendor_id, invoice_key, invoice_number, amount_inr, invoice_date,
    account_hash, verdict.
    """
    raise NotImplementedError("Lavya: implement in gate/verifiers/")
