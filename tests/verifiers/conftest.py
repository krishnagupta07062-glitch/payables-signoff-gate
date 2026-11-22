"""Shared fixtures for the checks. Synthetic companies and people only."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from gate.contracts import BankAccount, Claims, Contact, Request, RequestKind, Vendor
from gate.keys import account_hash
from gate.runbudget import RunBudget
from gate.verifiers import common
from gate.verifiers import crustdata_client as cc

GOOD_GSTIN = "27AAACR5055K1Z7"  # checksum-valid example from the research report
VENDOR_ID_CD = 990001
ACCT = "123456789012"


def days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("GATE_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("ACCOUNT_HASH_KEY", "test-key")
    monkeypatch.setenv("MOCK", "1")
    monkeypatch.setattr(common, "HTTP_GET", common._real_http_get)
    cc.set_default_client(None)
    yield
    cc.set_default_client(None)


@pytest.fixture
def budget(tmp_path):
    import gate.runbudget as rb
    rb.RUNS_DIR = tmp_path / "runs"
    return RunBudget(max_credits=10, max_seconds=60)


@pytest.fixture
def vendor():
    return Vendor(vendor_id="V001", legal_name="Acmeleaf Tanners Private Limited", gstin=GOOD_GSTIN,
                  pan="AAACR5055K", state_code="27", domains=["acmeleaf.in"], crustdata_company_id=VENDOR_ID_CD,
                  bank_accounts=[BankAccount(ifsc="HDFC0CAGSBK", account_last4=ACCT[-4:], account_hash=account_hash(ACCT),
                                             holder_name="Acmeleaf Tanners Pvt Ltd", verified_at="2026-01-10",
                                             added_at="2026-01-05")],
                  contacts=[Contact(name="Riya Synthetic", role="CFO", email="riya@acmeleaf.in")])


@pytest.fixture
def invoice_request():
    return Request(request_id="R1", kind=RequestKind.INVOICE, raw_text="(synthetic)", sender_email="ap@acmeleaf.in",
                   vendor_id="V001", po={"po_number": "PO-77", "amount_inr": 125000.0, "grn": True})


@pytest.fixture
def invoice_claims():
    return Claims(vendor_name="Acmeleaf Tanners Pvt Ltd", vendor_gstin=GOOD_GSTIN, invoice_number="INV/2026-27/0042",
                  invoice_date="2026-11-20", amount_inr=125000.0, po_number="PO-77", requested_change="payment")


class FakeTransport:
    """Answers Crustdata calls from a {path: (status, headers, body)} map, or a callable per path."""

    def __init__(self, routes: dict):
        self.routes, self.calls = routes, []

    def __call__(self, method, url, body, headers, timeout):
        path = url.replace(cc.BASE_URL, "")
        self.calls.append((path, json.loads(body) if body else None))
        r = self.routes.get(path)
        if r is None:
            return 404, {}, b'{"error":"no route"}'
        if callable(r):
            r = r()
        status, hdrs, data = r
        return status, {"x-request-id": f"req-{len(self.calls)}", **hdrs}, json.dumps(data).encode()


@pytest.fixture
def live(monkeypatch, tmp_path):
    """Returns a factory: live(routes) installs a fake-transport client as the default, with MOCK=0."""
    monkeypatch.setenv("MOCK", "0")

    class _NoWait:
        def wait(self, max_wait=0):
            return None

    def make(routes: dict, use_cache: bool = True):
        t = FakeTransport(routes)
        client = cc.Crustdata(api_key="test", transport=t, cache_dir=tmp_path / "cache", use_cache=use_cache,
                              limiter=_NoWait())
        cc.set_default_client(client)
        return t, client
    return make


@pytest.fixture
def http(monkeypatch):
    """Installs a fake GET for RDAP/IFSC/GST: http({url_substring: (status, body_obj_or_str)})."""
    def make(routes: dict):
        def fake(url, headers, timeout):
            for k, (status, body) in routes.items():
                if k in url:
                    if isinstance(body, Exception):
                        raise body
                    return status, (body if isinstance(body, str) else json.dumps(body)).encode()
            raise TimeoutError("no route")
        monkeypatch.setattr(common, "HTTP_GET", fake)
    return make


def identify_resp(domain, cid=VENDOR_ID_CD, name="Acmeleaf Tanners Private Limited", score=1.0, all_domains=None):
    return [{"matched_on": domain, "match_type": "domain", "matches": [{"confidence_score": score, "company_data": {
        "crustdata_company_id": cid, "basic_info": {"name": name, "primary_domain": (all_domains or [domain])[0],
                                                    "all_domains": all_domains or [domain]}}}]}]


def person_resp(name, current=None, past=None, updated=None):
    return {"total_count": 1, "profiles": [{"crustdata_person_id": 4242, "metadata": {"updated_at": updated or days_ago(5)},
                                            "basic_profile": {"name": name},
                                            "experience": {"employment_details": {"current": current or [],
                                                                                  "past": past or []}}}]}
