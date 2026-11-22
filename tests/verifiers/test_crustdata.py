import time

import pytest

from gate.contracts import CheckStatus, Claims, Request, RequestKind
from gate.runbudget import BudgetExceeded
from gate.verifiers import crustdata_checks as cdc
from gate.verifiers import crustdata_client as cc

from tests.verifiers.conftest import VENDOR_ID_CD, days_ago, identify_resp, person_resp

V, C, U = CheckStatus.VERIFIED, CheckStatus.CONTRADICTED, CheckStatus.UNVERIFIABLE
OK = {"x-credits-used": "0.2"}


def _req(email):
    return Request(request_id="R", kind=RequestKind.BANK_CHANGE, raw_text="", sender_email=email)


# ------------------------------------------------------------------ client

def test_cache_second_call_is_free(live, budget):
    t, client = live({"/company/identify": (200, OK, identify_resp("acmeleaf.in"))})
    r1 = client.call("/company/identify", {"domains": ["acmeleaf.in"]}, budget=budget)
    r2 = client.call("/company/identify", {"domains": ["acmeleaf.in"]}, budget=budget)
    assert len(t.calls) == 1 and r1.credits == 0.2 and r2.cached and r2.credits == 0
    assert budget.credits == pytest.approx(0.2)


def test_429_retries_then_succeeds(live, budget, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    answers = iter([(429, {}, {}), (200, OK, identify_resp("acmeleaf.in"))])
    t, client = live({"/company/identify": lambda: next(answers)})
    assert client.call("/company/identify", {"domains": ["acmeleaf.in"]}, budget=budget).data
    assert len(t.calls) == 2


def test_429_forever_raises_typed(live, budget, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    _, client = live({"/company/identify": (429, {}, {})})
    with pytest.raises(cc.CrustdataRateLimited):
        client.call("/company/identify", {"domains": ["x.in"]}, budget=budget)


def test_timeout_raises_typed(live, budget):
    def boom():
        raise TimeoutError("read timed out")
    _, client = live({"/company/identify": boom})
    with pytest.raises(cc.CrustdataTimeout):
        client.call("/company/identify", {"domains": ["x.in"]}, budget=budget)


def test_mock_mode_without_fixture_is_unavailable(budget):
    with pytest.raises(cc.CrustdataUnavailable):
        cc.Crustdata(api_key="k").call("/company/identify", {"domains": ["nofixture.example"]}, budget=budget)


def test_budget_ceiling_blocks_call(live, budget):
    t, client = live({"/company/enrich": (200, {"x-credits-used": "2"}, [])})
    budget.lower_ceiling(1.0)
    with pytest.raises(BudgetExceeded):
        client.call("/company/enrich", {"crustdata_company_ids": [1]}, budget=budget)
    assert t.calls == []


# ------------------------------------------------------------------ sender domain

def test_domain_matches_vendor(live, vendor, budget):
    live({"/company/identify": (200, OK, identify_resp("acmeleaf.in"))})
    c = cdc.sender_domain_matches_vendor(_req("ap@acmeleaf.in"), vendor, budget)
    assert c.status == V and c.sources[0].request_id and c.sources[0].kind == "crustdata"


def test_domain_score_one_but_not_in_all_domains(live, vendor, budget):
    # research gotcha: confidence 1.0 for a company that doesn't list the domain
    live({"/company/identify": (200, OK, identify_resp("evil.in", cid=1, name="Other", all_domains=["other.com"]))})
    assert cdc.sender_domain_matches_vendor(_req("ap@evil.in"), vendor, budget).status == C


def test_domain_belongs_to_other_company(live, vendor, budget):
    live({"/company/identify": (200, OK, identify_resp("other.com", cid=5, name="Other Co"))})
    assert cdc.sender_domain_matches_vendor(_req("ap@other.com"), vendor, budget).status == C


def test_domain_crustdata_down(live, vendor, budget):
    live({"/company/identify": (500, {}, {"error": "x"})})
    assert cdc.sender_domain_matches_vendor(_req("ap@unknown.com"), vendor, budget).status == U
    # fail closed even for the vendor's own domain (spec: case 9)
    assert cdc.sender_domain_matches_vendor(_req("ap@acmeleaf.in"), vendor, budget).status == U


def test_domain_on_master_but_not_in_crustdata(live, vendor, budget):
    # spec: case 6, small vendor not in the index
    live({"/company/identify": (200, {}, [{"matched_on": "acmeleaf.in", "matches": []}])})
    assert cdc.sender_domain_matches_vendor(_req("ap@acmeleaf.in"), vendor, budget).status == U


def test_parent_domain_on_master_is_flagged_not_contradicted(live, vendor, budget):
    # real case: bata.com is on Bata India's master, but Crustdata files it under Bata Group (another record)
    vendor.domains = ["acmeleaf.in", "acmeleafgroup.com"]
    live({"/company/identify": (200, OK, identify_resp("acmeleafgroup.com", cid=77, name="Acmeleaf Group"))})
    c = cdc.sender_domain_matches_vendor(_req("ap@acmeleafgroup.com"), vendor, budget)
    assert c.status == U and "same company under another name" in c.note and c.value["crustdata_company_id"] == 77


def test_rebrand_sharing_a_domain_is_flagged_not_contradicted(live, vendor, budget):
    # Zomato/Eternal style: the new name isn't on our master, but its record lists the vendor's old domain
    live({"/company/identify": (200, OK, identify_resp("eternleaf.com", cid=88, name="Eternleaf Ltd",
                                                       all_domains=["eternleaf.com", "acmeleaf.in"]))})
    c = cdc.sender_domain_matches_vendor(_req("ap@eternleaf.com"), vendor, budget)
    assert c.status == U and "also lists acmeleaf.in" in c.note and "rebrand" in c.note


def test_unrelated_company_domain_is_contradicted(live, vendor, budget):
    live({"/company/identify": (200, OK, identify_resp("other.com", cid=5, name="Other Co",
                                                       all_domains=["other.com", "other.in"]))})
    assert cdc.sender_domain_matches_vendor(_req("ap@other.com"), vendor, budget).status == C


# ------------------------------------------------------------------ requester

AT_VENDOR = {"name": "Acmeleaf", "title": "Chief Financial Officer", "start_date": "2024-01-01T00:00:00",
             "crustdata_company_id": VENDOR_ID_CD}


def test_requester_current(live, vendor, budget):
    live({"/person/search": (200, {"x-credits-used": "0.23"}, person_resp("Riya Synthetic", current=[AT_VENDOR]))})
    cur, dep = cdc.requester_checks(Claims(requester_name="Riya Synthetic", requester_role="CFO"), vendor, budget)
    assert cur.status == V and dep.status == V and cur.value["title"] == "Chief Financial Officer"
    assert "linkedin" not in str(cur.value).lower()


def test_requester_wrong_role(live, vendor, budget):
    live({"/person/search": (200, {}, person_resp("Riya Synthetic", current=[{**AT_VENDOR, "title": "Store Manager"}]))})
    cur, _ = cdc.requester_checks(Claims(requester_name="Riya Synthetic", requester_role="CFO"), vendor, budget)
    assert cur.status == C


def test_requester_departed(live, vendor, budget):
    past = [{**AT_VENDOR, "end_date": "2026-10-01T00:00:00"}]
    now = [{"name": "Elsewhere Ltd", "title": "CFO", "crustdata_company_id": 7}]
    live({"/person/search": (200, {}, person_resp("Riya Synthetic", current=now, past=past))})
    cur, dep = cdc.requester_checks(Claims(requester_name="Riya Synthetic", requester_role="CFO"), vendor, budget)
    assert dep.status == C and {k: dep.value[k] for k in ("name", "end_date", "current_employer", "person_id")} == \
        {"name": "Riya Synthetic", "end_date": "2026-10-01", "current_employer": "Elsewhere Ltd", "person_id": 4242}
    assert cur.status == C


def _two_same_name(first_title, second_title, second_current=False):
    """Two synthetic people called 'Dev Synthetic' who both worked at the vendor; the intern comes back first."""
    intern = {"crustdata_person_id": 111, "metadata": {"updated_at": days_ago(3)}, "basic_profile": {"name": "Dev Synthetic"},
              "experience": {"employment_details": {
                  "current": [{"name": "Elsewhere Ltd", "title": "Regional Sales Manager", "crustdata_company_id": 7}],
                  "past": [{**AT_VENDOR, "title": first_title, "start_date": "2015-05-01T00:00:00",
                            "end_date": "2015-08-01T00:00:00"}]}}}
    role = {**AT_VENDOR, "title": second_title, "start_date": "2024-11-01T00:00:00"}
    head = {"crustdata_person_id": 222, "metadata": {"updated_at": days_ago(5)}, "basic_profile": {"name": "Dev Synthetic"},
            "experience": {"employment_details": {
                "current": [role] if second_current else [],
                "past": [] if second_current else [{**role, "end_date": "2026-10-01T00:00:00"}]}}}
    return {"total_count": 2, "profiles": [intern, head]}


def test_same_name_picks_the_one_whose_role_matches(live, vendor, budget):
    # spec: private case 12 (two same-name people at the vendor; the finance head left 2026-10)
    live({"/person/search": (200, {}, _two_same_name("Sales And Marketing Intern", "Head - Finance Shared Services"))})
    cur, dep = cdc.requester_checks(Claims(requester_name="Dev Synthetic",
                                           requester_role="Head - Finance Shared Services"), vendor, budget)
    assert dep.status == C and dep.value["person_id"] == 222 and dep.value["end_date"] == "2026-10-01"
    assert dep.value["title"] == "Head - Finance Shared Services" and dep.sources[0].record_id == "222"
    assert "Picked person 222 of 2" in dep.note


def test_same_name_current_holder_wins(live, vendor, budget):
    live({"/person/search": (200, {}, _two_same_name("Finance Intern", "Chief Financial Officer", second_current=True))})
    cur, dep = cdc.requester_checks(Claims(requester_name="Dev Synthetic", requester_role="CFO"), vendor, budget)
    assert cur.status == V and cur.value["person_id"] == 222 and dep.status == V


def test_same_name_ambiguous_is_unverifiable(live, vendor, budget):
    # both held finance roles: the claimed role can't separate them -> never CONTRADICTED
    live({"/person/search": (200, {}, _two_same_name("Finance Manager", "Finance Manager"))})
    cur, dep = cdc.requester_checks(Claims(requester_name="Dev Synthetic", requester_role="Finance Manager"),
                                    vendor, budget)
    assert cur.status == U and dep.status == U and "2 people" in dep.note and "call back" in cur.note


def test_same_name_no_role_claimed_is_unverifiable(live, vendor, budget):
    live({"/person/search": (200, {}, _two_same_name("Sales Intern", "Head - Finance Shared Services"))})
    cur, dep = cdc.requester_checks(Claims(requester_name="Dev Synthetic"), vendor, budget)
    assert cur.status == U and dep.status == U


def test_requester_stale_record(live, vendor, budget):
    live({"/person/search": (200, {}, person_resp("Riya Synthetic", current=[AT_VENDOR], updated=days_ago(60)))})
    cur, dep = cdc.requester_checks(Claims(requester_name="Riya Synthetic", requester_role="CFO"), vendor, budget)
    assert cur.status == U and dep.status == U


def test_requester_not_found_says_call_back(live, vendor, budget):
    live({"/person/search": (200, {}, {"total_count": 0, "profiles": []})})
    cur, dep = cdc.requester_checks(Claims(requester_name="Nobody Here"), vendor, budget)
    assert cur.status == U and "call back on the number on file" in cur.note and dep.status == U


def test_requester_small_vendor_unlinked(vendor, budget):
    vendor.crustdata_company_id = None
    cur, _ = cdc.requester_checks(Claims(requester_name="Riya Synthetic"), vendor, budget)
    assert cur.status == U and "call back" in cur.note


# ------------------------------------------------------------------ vendor active

def _company(status="active", updated=None):
    return {"companies": [{"crustdata_company_id": VENDOR_ID_CD, "basic_info": {"status": status},
                           "metadata": {"updated_at": updated or days_ago(3)}}]}


def test_vendor_active(live, vendor, budget):
    live({"/company/search": (200, {}, _company()),
          "/web/enrich/live": (200, {"x-credits-used": "1"}, [{"success": True, "http_status": 200,
                                                               "title": "Acmeleaf Tanners", "content": "<html>"}])})
    c = cdc.vendor_active(vendor, budget)
    assert c.status == V and c.value["site_live"] is True


def test_vendor_index_active_but_domain_expired(live, vendor, budget):
    live({"/company/search": (200, {}, _company()),
          "/web/enrich/live": (200, {}, [{"success": True, "http_status": 200, "title": "acmeleaf.in has expired",
                                          "content": ""}])})
    assert cdc.vendor_active(vendor, budget).status == C


def test_vendor_site_blocks_bots_but_record_fresh(live, vendor, budget):
    # real case: bata.in answers Crustdata's fetcher with 403 "Access Denied", even in human_mode
    t, _ = live({"/company/search": (200, {}, _company()),
                 "/web/enrich/live": (200, {"x-credits-used": "1"}, [{"success": True, "http_status": 403,
                                                                      "title": "Access Denied", "content": "x"}])})
    c = cdc.vendor_active(vendor, budget)
    assert c.status == V and "refuses automated fetches" in c.note
    assert [b for p, b in t.calls if p == "/web/enrich/live"][1].get("human_mode") is True  # retried as a browser


def test_vendor_site_blocks_bots_and_record_stale(live, vendor, budget):
    live({"/company/search": (200, {}, _company(updated=days_ago(90))),
          "/web/enrich/live": (200, {}, [{"success": True, "http_status": 403, "title": "Access Denied", "content": ""}])})
    assert cdc.vendor_active(vendor, budget).status == U


def test_vendor_deleted(live, vendor, budget):
    live({"/company/search": (200, {}, _company("deleted")),
          "/web/enrich/live": (200, {}, [{"success": True, "http_status": 200, "title": "ok", "content": ""}])})
    assert cdc.vendor_active(vendor, budget).status == C
