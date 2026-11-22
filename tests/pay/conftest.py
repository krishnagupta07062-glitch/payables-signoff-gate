"""Shared fixtures for the pay tests: a fresh SQLite DB per test, mock payments, synthetic data."""
from __future__ import annotations

import uuid

import pytest

from gate import store
from gate.contracts import (BankAccount, Check, CheckStatus, Decision, PaymentAction, Reason, Source,
                            Vendor, Verdict, action_hash)


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "gate.sqlite")
    monkeypatch.setenv("GATE_DB", path)
    monkeypatch.setenv("PAYMENTS_MODE", "mock")
    monkeypatch.setenv("ACCOUNT_HASH_KEY", "test-key")
    monkeypatch.delenv("GATE_CRASH_AT", raising=False)
    store.init_db(path)
    return path


def make_vendor(vid="V-ACME", account="50100012345678") -> Vendor:
    return Vendor(vendor_id=vid, legal_name="Acme Test Supplies Pvt Ltd", gstin="29ABCDE1234F1Z5",
                  pan="ABCDE1234F", state_code="29", domains=["acme-test.example"],
                  bank_accounts=[BankAccount(ifsc="HDFC0000001", account_last4=store.last4(account),
                                             account_hash=store.hash_account(account),
                                             holder_name="Acme Test Supplies", added_at="2026-01-01T00:00:00+00:00")])


def make_decision(verdict=Verdict.ALLOW, request_id=None, amount_paise=1250000, invoice="42",
                  vendor_id="V-ACME") -> Decision:
    rid = request_id or "REQ-" + uuid.uuid4().hex[:8]
    acct = "50100012345678"
    fp = f"29ABCDE1234F1Z5|{invoice}|2026-2027|{amount_paise}"
    action = PaymentAction(vendor_id=vendor_id, invoice_key=f"29ABCDE1234F1Z5|{invoice}|2026-2027",
                           amount_paise=amount_paise, account_hash=store.hash_account(acct),
                           account_last4=acct[-4:], ifsc="HDFC0000001",
                           idempotency_key=str(uuid.uuid5(uuid.UUID("6f1c2a4e-9b1d-4c33-8e0a-5a7d2b9c0f11"), fp)))
    checks = [Check("gstin_checksum", CheckStatus.VERIFIED, {"gstin": "29ABCDE1234F1Z5"},
                    [Source("vendor_master", "local:gstin_checksum")])]
    rule = {"ALLOW": "A1", "BLOCK": "B1", "ESCALATE": "E1"}[verdict.value]
    return Decision(request_id=rid, verdict=verdict, rule_ids=[rule], reasons=[Reason(rule, "test", ["gstin_checksum"])],
                    checks=checks, action=action, action_hash=action_hash(action))
