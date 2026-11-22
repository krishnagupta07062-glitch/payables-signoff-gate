"""Verification checks. OWNER: Lavya.

Contract: run_all() never raises. Every check that errors or times out comes back as
Check(status=UNVERIFIABLE, note=<what is missing>). See gate/contracts.py CHECK_NAMES for names.

Which checks run:
- every request with a sender: sender_domain_lookalike, domain_age_days, sender_domain_matches_vendor
- bank / contact change: + requester_current_role, requester_departed, ifsc_valid, account_on_vendor_master,
  account_shared_across_vendors, penny_drop_name_match
- invoice / payment: + gstin_checksum, gstin_matches_vendor, gstin_exists, duplicate_invoice,
  near_duplicate_invoice, po_match, account_on_vendor_master, account_shared_across_vendors, ifsc_valid,
  penny_drop_name_match, vendor_active (and the requester checks when a requester is named)
"""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Callable

from gate.contracts import CHECK_NAMES, Check, CheckStatus, Claims, Request, RequestKind, Vendor
from gate.runbudget import RunBudget
from gate.verifiers import crustdata_checks as cdc
from gate.verifiers import history_checks as hc
from gate.verifiers import india_checks as ic

PER_CHECK_TIMEOUT_S = float(os.environ.get("CHECK_TIMEOUT_S", "20"))
_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="verifier")


def _kind(request: Request) -> RequestKind:
    try:
        return request.kind if isinstance(request.kind, RequestKind) else RequestKind(request.kind)
    except ValueError:
        return RequestKind.EMAIL


def plan(request: Request, claims: Claims, vendor: Vendor, history: list[dict] | None,
         budget: RunBudget) -> list[tuple[tuple[str, ...], Callable[[], object]]]:
    """[(check names this job yields, zero-arg job)]. A job returns one Check or a list of Checks."""
    kind = _kind(request)
    is_change = kind == RequestKind.BANK_CHANGE or claims.requested_change in ("bank_change", "contact_change")
    is_payment = not is_change and (kind == RequestKind.INVOICE or claims.requested_change == "payment")
    jobs: list[tuple[tuple[str, ...], Callable]] = []
    add = lambda names, fn: jobs.append((names, fn))  # noqa: E731

    if request.sender_email:
        add(("sender_domain_lookalike",), lambda: ic.sender_domain_lookalike(request, vendor))
        add(("domain_age_days",), lambda: ic.domain_age_days(request, vendor, budget))
        add(("sender_domain_matches_vendor",), lambda: cdc.sender_domain_matches_vendor(request, vendor, budget))

    if is_change or claims.requester_name:
        add(("requester_current_role", "requester_departed"), lambda: cdc.requester_checks(claims, vendor, budget))

    if is_change or is_payment:
        add(("ifsc_valid",), lambda: ic.ifsc_valid(claims, vendor, budget))
        if is_payment:  # a bank change names a new account by definition; E1 already holds it for a person
            add(("account_on_vendor_master",), lambda: hc.account_on_vendor_master(claims, vendor))
        add(("account_shared_across_vendors",), lambda: hc.account_shared_across_vendors(claims, vendor, history))
        add(("penny_drop_name_match",), lambda: hc.penny_drop_name_match(claims, vendor))

    if is_payment:
        add(("gstin_checksum",), lambda: ic.gstin_checksum(claims, vendor))
        add(("gstin_matches_vendor",), lambda: ic.gstin_matches_vendor(claims, vendor))
        add(("gstin_exists",), lambda: ic.gstin_exists(claims, vendor, budget))
        add(("duplicate_invoice",), lambda: hc.duplicate_invoice(request, claims, vendor, history))
        add(("near_duplicate_invoice",), lambda: hc.near_duplicate_invoice(request, claims, vendor, history))
        add(("po_match",), lambda: hc.po_match(request, claims))
        add(("vendor_active",), lambda: cdc.vendor_active(vendor, budget))
    return jobs


def _unverifiable(name: str, note: str) -> Check:
    return Check(name=name, status=CheckStatus.UNVERIFIABLE, note=note)


def run_all(request: Request, claims: Claims, vendor: Vendor, history: list[dict],
            budget: RunBudget) -> list[Check]:
    """Run every relevant check for this request against live sources and the trusted vendor record.

    history: prior requests/decisions for this vendor and others, from store.history_for(); each dict
    has at least request_id, vendor_id, invoice_key, invoice_number, amount_inr, invoice_date,
    account_hash, verdict.
    """
    try:
        jobs = plan(request, claims, vendor, history, budget)
    except Exception as e:  # never raise: a planning bug still yields a fail-closed answer
        return [_unverifiable(n, f"verifiers could not start: {type(e).__name__}: {e}")
                for n in ("duplicate_invoice", "account_on_vendor_master", "sender_domain_matches_vendor")]

    futures = [(names, _POOL.submit(fn)) for names, fn in jobs]
    deadline = time.monotonic() + PER_CHECK_TIMEOUT_S  # checks run in parallel, so one shared deadline
    out: list[Check] = []
    for names, fut in futures:
        try:
            res = fut.result(timeout=max(0.05, deadline - time.monotonic()))
            got = res if isinstance(res, list) else [res]
            by_name = {c.name: c for c in got if isinstance(c, Check)}
            for n in names:
                out.append(by_name.get(n) or _unverifiable(n, "check returned no result"))
        except FutureTimeout:
            fut.cancel()
            out.extend(_unverifiable(n, f"check timed out after {PER_CHECK_TIMEOUT_S:.0f}s; source did not answer")
                       for n in names)
        except Exception as e:
            out.extend(_unverifiable(n, f"check failed: {type(e).__name__}: {str(e)[:160]}") for n in names)
    for c in out:  # guard the frozen contract: only known names leave this module
        if c.name not in CHECK_NAMES:
            c.note = f"(unknown check name) {c.note}"
    return out
