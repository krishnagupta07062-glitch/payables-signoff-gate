"""Checks on live Crustdata records: sender domain, vendor alive, requester's role or departure. OWNER: Lavya.

Gotchas from docs/research/05_crustdata_verification.md that this code handles:
- identify confidence 1.0 is not proof: the domain must be in basic_info.all_domains / primary_domain.
- identify scores below 0.8 are no match. Legal suffixes (Ltd/Limited/Pvt) are normalised before comparing names.
- index "active" is not "alive": the vendor's site is fetched live; expired/parked pages are CONTRADICTED.
- person search: filter `experience.employment_details.company_id`, read `current[].crustdata_company_id`;
  a person only in past[] at the vendor is a departure. Records older than 30 days are stale -> UNVERIFIABLE.
- Only name, title and dates go into Check.value, never the raw profile.
"""
from __future__ import annotations

import re
from typing import Optional

from rapidfuzz import fuzz

from gate.contracts import Check, Claims, Request, Source, Vendor
from gate.runbudget import BudgetExceeded, RunBudget
from gate.verifiers.common import (C, STALE_DAYS, U, V, age_days, check, email_domain, norm_company, norm_person,
                                   registrable_domain, unverifiable)
from gate.verifiers.crustdata_client import CallResult, Crustdata, CrustdataError, default_client

MIN_IDENTIFY_SCORE = 0.8
CALLBACK = "cannot verify the requester; call back on the number on file"


def _src(res: CallResult, record_id=None, record_date=None, excerpt=None) -> Source:
    return Source(kind="crustdata", ref=f"POST https://api.crustdata.com{res.path}", retrieved_at=res.retrieved_at,
                  request_id=res.request_id, record_id=str(record_id) if record_id is not None else None,
                  record_date=record_date, excerpt=excerpt)


def _call(cd: Crustdata, path: str, body: dict, budget: Optional[RunBudget]) -> CallResult:
    return cd.call(path, body, budget=budget)


def _fail(name: str, e: Exception, what: str) -> Check:
    kind = "budget ceiling reached" if isinstance(e, BudgetExceeded) else f"Crustdata unavailable ({e})"
    return unverifiable(name, f"{kind}; {what}.", [Source(kind="crustdata", ref="https://api.crustdata.com",
                                                          excerpt=str(e)[:200])])


# ------------------------------------------------------------------------------- sender domain

def _identify_domain(cd: Crustdata, domain: str, budget) -> tuple[CallResult, list[dict]]:
    res = _call(cd, "/company/identify", {"domains": [domain]}, budget)
    rows = res.data if isinstance(res.data, list) else res.data.get("results", []) if isinstance(res.data, dict) else []
    matches = []
    for row in rows:
        for m in (row.get("matches") or []):
            cdata = m.get("company_data") or {}
            bi = cdata.get("basic_info") or {}
            matches.append({"id": cdata.get("crustdata_company_id") or bi.get("crustdata_company_id"),
                            "name": bi.get("name"), "primary_domain": (bi.get("primary_domain") or "").lower(),
                            "all_domains": [d.lower() for d in (bi.get("all_domains") or [])],
                            "score": float(m.get("confidence_score") or 0)})
    return res, matches


def sender_domain_matches_vendor(request: Request, vendor: Vendor, budget: Optional[RunBudget] = None,
                                 cd: Optional[Crustdata] = None) -> Check:
    name = "sender_domain_matches_vendor"
    d = email_domain(request.sender_email)
    if not d:
        return unverifiable(name, "No sender email address, so no domain to check.")
    d = registrable_domain(d)
    on_master = d in [x.lower() for x in vendor.domains] or d in [registrable_domain(x) for x in vendor.domains]
    master_src = Source(kind="vendor_master", ref=f"vendor:{vendor.vendor_id}",
                        excerpt=f"domains on file: {', '.join(vendor.domains) or 'none'}")
    cd = cd or default_client()
    try:
        res, matches = _identify_domain(cd, d, budget)
    except (CrustdataError, BudgetExceeded) as e:
        # fail closed: our own record listing the domain is not an independent confirmation
        return _fail(name, e, f"cannot confirm {d} belongs to {vendor.legal_name}"
                              + (" (it is on the vendor master)" if on_master else ""))
    owning = [m for m in matches if m["score"] >= MIN_IDENTIFY_SCORE and (d in m["all_domains"] or d == m["primary_domain"])]
    srcs = [master_src]
    if vendor.crustdata_company_id:
        same = [m for m in owning if m["id"] == vendor.crustdata_company_id]
        if same:
            m = same[0]
            srcs.insert(0, _src(res, m["id"], excerpt=f"{m['name']}: all_domains {m['all_domains'][:6]}"))
            return check(name, V, f"{d} belongs to {m['name']} (Crustdata id {m['id']}), the vendor on file.",
                         {"domain": d, "crustdata_company_id": m["id"]}, srcs, res.credits)
        if owning:
            m = owning[0]
            srcs.insert(0, _src(res, m["id"], excerpt=f"{m['name']}: all_domains {m['all_domains'][:6]}"))
            if on_master:
                return unverifiable(name, f"{d} is on the vendor master, but Crustdata says it belongs to "
                                          f"{m['name']} (id {m['id']}), not vendor id {vendor.crustdata_company_id}. "
                                          "Possible rebrand or parent/subsidiary; confirm by hand.",
                                    srcs, {"domain": d, "crustdata_company_id": m["id"]}, res.credits)
            return check(name, C, f"{d} belongs to {m['name']} (Crustdata id {m['id']}), not to {vendor.legal_name}.",
                         {"domain": d, "crustdata_company_id": m["id"]}, srcs, res.credits)
    elif owning:
        m = owning[0]
        srcs.insert(0, _src(res, m["id"], excerpt=f"{m['name']}: all_domains {m['all_domains'][:6]}"))
        if on_master or fuzz.token_set_ratio(norm_company(m["name"]), norm_company(vendor.legal_name)) >= 90:
            return check(name, V, f"{d} belongs to {m['name']} (Crustdata id {m['id']}).",
                         {"domain": d, "crustdata_company_id": m["id"]}, srcs, res.credits)
        return check(name, C, f"{d} belongs to {m['name']}, not to {vendor.legal_name}.",
                     {"domain": d, "crustdata_company_id": m["id"]}, srcs, res.credits)
    # no Crustdata record owns this domain
    srcs.insert(0, _src(res, excerpt=f"{len(matches)} candidate(s), none listing {d} in all_domains"))
    if on_master:
        return unverifiable(name, f"{d} is on the vendor master, but no Crustdata record lists it, so nothing "
                                  "independent confirms it.", srcs, {"domain": d, "crustdata_company_id": None},
                            res.credits)
    return check(name, C, f"{d} is not on the vendor master and no Crustdata record ties it to {vendor.legal_name}.",
                 {"domain": d, "crustdata_company_id": None}, srcs, res.credits)


# ------------------------------------------------------------------------------- vendor active

_DEAD_PAGE = re.compile(r"(domain (has )?expired|this domain is for sale|buy this domain|domain parking|parked free|"
                        r"has expired|account suspended|website is under construction|sedo|godaddy\.com/.*forsale)", re.I)


def vendor_active(vendor: Vendor, budget: Optional[RunBudget] = None, cd: Optional[Crustdata] = None) -> Check:
    name = "vendor_active"
    cd = cd or default_client()
    credits, srcs = 0.0, []
    status, updated_at, site_live = None, None, None
    if not vendor.crustdata_company_id and not vendor.domains:
        return unverifiable(name, "Vendor has no Crustdata id and no domain to check.")
    try:
        if vendor.crustdata_company_id:
            res = _call(cd, "/company/search", {
                "filters": {"field": "crustdata_company_id", "type": "=", "value": vendor.crustdata_company_id},
                "fields": ["crustdata_company_id", "basic_info.name", "basic_info.status", "metadata.updated_at"],
                "limit": 1}, budget)
            credits += res.credits
            comps = (res.data or {}).get("companies") or (res.data or {}).get("results") or []
            if comps:
                c0 = comps[0]
                status = ((c0.get("basic_info") or {}).get("status") or "").lower() or None
                updated_at = (c0.get("metadata") or {}).get("updated_at")
                srcs.append(_src(res, vendor.crustdata_company_id, updated_at, f"status={status}"))
            else:
                srcs.append(_src(res, vendor.crustdata_company_id, excerpt="no company record"))
        blocked = False
        if vendor.domains:
            url = f"https://{registrable_domain(vendor.domains[0])}"
            p, res = _fetch_page(cd, url, budget, human_mode=False)
            credits += res.credits
            if _http(p) in _BOT_BLOCK:  # bot protection (e.g. bata.in answers 403 "Access Denied"): try as a browser
                p, res = _fetch_page(cd, url, budget, human_mode=True)
                credits += res.credits
            http_status = _http(p)
            text = f"{p.get('title') or ''} {(p.get('content') or '')[:20000]}"
            dead = bool(_DEAD_PAGE.search(text))
            blocked = http_status in _BOT_BLOCK and not dead
            site_live = bool(p.get("success")) and http_status is not None and http_status < 400 and not dead
            srcs.append(Source(kind="web", ref=url, retrieved_at=res.retrieved_at, request_id=res.request_id,
                               excerpt=f"http {http_status}; title: {(p.get('title') or '')[:80]}"
                                       + ("; looks expired/parked" if dead else "")
                                       + ("; server refuses automated fetches" if blocked else "")))
            if dead:
                return check(name, C, f"{url} looks expired or parked ('{(p.get('title') or '')[:60]}').",
                             {"status": status, "updated_at": updated_at, "site_live": False}, srcs, credits)
    except (CrustdataError, BudgetExceeded) as e:
        return _fail(name, e, "cannot confirm the vendor is still operating")
    value = {"status": status, "updated_at": updated_at, "site_live": site_live}
    if status == "deleted":
        return check(name, C, f"Crustdata marks {vendor.legal_name} as deleted.", value, srcs, credits)
    if vendor.crustdata_company_id and status is None:
        return unverifiable(name, "No company status in Crustdata.", srcs, value, credits)
    age = age_days(updated_at)
    fresh = updated_at is not None and age is not None and age <= STALE_DAYS
    if blocked:
        # A server that refuses bots is a live server: expired domains show parked pages or don't resolve.
        # Only good enough together with a fresh, active company record.
        if status == "active" and fresh:
            value["site_live"] = True
            return check(name, V, f"{vendor.legal_name} is active in Crustdata (record updated {updated_at[:10]}); its "
                                  f"site answers but refuses automated fetches (HTTP {_http(p)}).", value, srcs, credits)
        return unverifiable(name, f"The vendor's site refuses automated fetches (HTTP {_http(p)}) and the company "
                                  "record is not fresh enough to rely on alone.", srcs, value, credits)
    if site_live is False:
        return unverifiable(name, "The vendor's website did not load (HTTP error or empty); cannot confirm it is alive.",
                            srcs, value, credits)
    if updated_at and age is not None and age > STALE_DAYS and site_live is None:
        return unverifiable(name, f"Company record last updated {age} days ago (stale).", srcs, value, credits)
    return check(name, V, f"{vendor.legal_name} is {status or 'listed'} and its site is live.", value, srcs, credits)


_BOT_BLOCK = {401, 403, 429}


def _http(p: dict) -> Optional[int]:
    try:
        return int(p.get("http_status")) if p.get("http_status") is not None else None
    except (TypeError, ValueError):
        return None


def _fetch_page(cd: Crustdata, url: str, budget, human_mode: bool) -> tuple[dict, CallResult]:
    body = {"urls": [url], "human_mode": True} if human_mode else {"urls": [url]}
    res = _call(cd, "/web/enrich/live", body, budget)
    pages = res.data if isinstance(res.data, list) else (res.data or {}).get("results") or []
    return (pages[0] if pages else {}), res


# ------------------------------------------------------------------------------- requester

_ROLE_ALIASES = {
    "cfo": "chief financial officer", "ceo": "chief executive officer", "coo": "chief operating officer",
    "cto": "chief technology officer", "md": "managing director", "vp": "vice president",
    "gm": "general manager", "avp": "assistant vice president", "ap": "accounts payable",
    "fc": "financial controller", "hod": "head of department",
}


def _norm_role(r: Optional[str]) -> str:
    s = (r or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z ]+", " ", s)
    words = [_ROLE_ALIASES.get(w, w) for w in s.split()]
    return " ".join(words)


def role_matches(claimed: Optional[str], title: Optional[str]) -> bool:
    if not claimed:
        return True  # no role claimed: being current at the vendor is all we can check
    a, b = _norm_role(claimed), _norm_role(title)
    return bool(b) and (fuzz.token_set_ratio(a, b) >= 80 or a in b)


_PERSON_FIELDS = [
    "basic_profile.name", "basic_profile.current_title",
    "experience.employment_details.current.name", "experience.employment_details.current.title",
    "experience.employment_details.current.start_date", "experience.employment_details.current.crustdata_company_id",
    "experience.employment_details.past.name", "experience.employment_details.past.title",
    "experience.employment_details.past.start_date", "experience.employment_details.past.end_date",
    "experience.employment_details.past.crustdata_company_id", "metadata.updated_at"]


def _person_search(cd: Crustdata, name: str, company_id: int, budget) -> CallResult:
    # limit 10, not 3: with several same-name people at a vendor we must see them all to pick the right one
    # (billed per returned result, so a unique name still costs one result)
    return _call(cd, "/person/search", {
        "filters": {"op": "and", "conditions": [
            {"field": "basic_profile.name", "type": "(.)", "value": name},
            {"field": "experience.employment_details.company_id", "type": "=", "value": company_id}]},
        "fields": _PERSON_FIELDS, "limit": 10}, budget)


MIN_ROLE_SCORE = 60   # with several same-name candidates, the best one's role must match at least this well
ROLE_MARGIN = 10      # ...and beat the runner-up by more than this, or we can't tell them apart


def _role_score(claimed: Optional[str], title: Optional[str]) -> float:
    if not claimed or not title:
        return 0.0
    return float(fuzz.token_set_ratio(_norm_role(claimed), _norm_role(title)))


def _candidate(p: dict, who: str, claimed_role: Optional[str], vid: int) -> dict:
    """One person-search profile, scored for 'is this the person who signed the request?'."""
    emp = (p.get("experience") or {}).get("employment_details") or {}
    here = [dict(r, _current=True) for r in (emp.get("current") or []) if r.get("crustdata_company_id") == vid] + \
           [dict(r, _current=False) for r in (emp.get("past") or []) if r.get("crustdata_company_id") == vid]
    best = max(here, key=lambda r: _role_score(claimed_role, r.get("title")), default=None)
    recency = max(("9999" if r["_current"] else (r.get("end_date") or "")) for r in here) if here else ""
    return {"profile": p, "pid": p.get("crustdata_person_id"),
            "name_score": fuzz.token_set_ratio(norm_person(who), norm_person((p.get("basic_profile") or {}).get("name"))),
            "role_score": _role_score(claimed_role, best.get("title")) if best else 0.0,
            "vendor_title": best.get("title") if best else None, "recency": recency}


def requester_checks(claims: Claims, vendor: Vendor, budget: Optional[RunBudget] = None,
                     cd: Optional[Crustdata] = None) -> list[Check]:
    """Returns [requester_current_role, requester_departed] from one person search."""
    n1, n2 = "requester_current_role", "requester_departed"
    who = (claims.requester_name or "").strip()
    if not who:
        return [unverifiable(n1, f"No requester name in the request; {CALLBACK}."),
                unverifiable(n2, "No requester name in the request.")]
    if not vendor.crustdata_company_id:
        return [unverifiable(n1, f"Vendor is not linked to a Crustdata company; {CALLBACK}."),
                unverifiable(n2, "Vendor is not linked to a Crustdata company.")]
    cd = cd or default_client()
    try:
        res = _person_search(cd, who, vendor.crustdata_company_id, budget)
    except (CrustdataError, BudgetExceeded) as e:
        return [_fail(n1, e, CALLBACK), _fail(n2, e, "cannot tell whether the requester left the vendor")]
    profiles = (res.data or {}).get("profiles") or []
    vid = vendor.crustdata_company_id
    cands = [c for c in (_candidate(p, who, claims.requester_role, vid) for p in profiles) if c["name_score"] >= 85]
    if not cands:
        s0 = _src(res, excerpt=f"no person named '{who}' at company {vid}")
        return [unverifiable(n1, f"No one named {who} found at {vendor.legal_name} in Crustdata; {CALLBACK}.", [s0],
                             credits=res.credits),
                unverifiable(n2, f"No one named {who} found at {vendor.legal_name} in Crustdata.", [s0])]
    # Same-name risk: several people with this name worked at the vendor. Pick by how well their role there
    # matches the claimed role, then by the most recent role. If that still doesn't separate them, say so.
    cands.sort(key=lambda c: (c["role_score"], c["name_score"], c["recency"]), reverse=True)
    if len(cands) > 1:
        best, second = cands[0], cands[1]
        if best["role_score"] < MIN_ROLE_SCORE or second["role_score"] >= best["role_score"] - ROLE_MARGIN:
            s0 = _src(res, excerpt="; ".join(f"person {c['pid']}: {c['vendor_title'] or '?'}" for c in cands[:5]))
            msg = (f"{len(cands)} people named like {who} worked at {vendor.legal_name}, and the claimed role "
                   f"'{claims.requester_role or 'none'}' doesn't tell them apart")
            return [unverifiable(n1, f"{msg}; {CALLBACK}.", [s0], {"candidates": len(cands)}, res.credits),
                    unverifiable(n2, f"{msg}; cannot tell which one sent this.", [s0], {"candidates": len(cands)})]
    chosen = cands[0]
    p = chosen["profile"]
    pid = p.get("crustdata_person_id")
    picked_note = (f" Picked person {pid} of {len(cands)} with this name: role '{chosen['vendor_title']}' best matches "
                   f"'{claims.requester_role}'.") if len(cands) > 1 else ""
    pname = (p.get("basic_profile") or {}).get("name") or who
    updated_at = (p.get("metadata") or {}).get("updated_at")
    emp = (p.get("experience") or {}).get("employment_details") or {}
    cur_here = [r for r in (emp.get("current") or []) if r.get("crustdata_company_id") == vid]
    past_here = [r for r in (emp.get("past") or []) if r.get("crustdata_company_id") == vid]
    cur_else = [r for r in (emp.get("current") or []) if r.get("crustdata_company_id") != vid]
    age = age_days(updated_at)
    stale = age is None or age > STALE_DAYS
    s = _src(res, pid, (updated_at or "")[:10] or None,
             f"{pname}: current at vendor={bool(cur_here)}, past at vendor={bool(past_here)}")

    if cur_here:
        r = max(cur_here, key=lambda x: _role_score(claims.requester_role, x.get("title")))
        start = (r.get("start_date") or "")[:10] or None
        v1 = {"name": pname, "title": r.get("title"), "start_date": start, "updated_at": updated_at, "person_id": pid}
        v2 = {"name": pname, "end_date": None, "current_employer": r.get("name"), "title": r.get("title"),
              "start_date": start, "person_id": pid}
        departed = check(n2, V, f"{pname} is a current employee of {vendor.legal_name}.{picked_note}", v2, [s])
        if stale:
            return [unverifiable(n1, f"{pname}'s record is {age if age is not None else '?'} days old (stale, over "
                                     f"{STALE_DAYS}); {CALLBACK}.", [s], v1, res.credits),
                    unverifiable(n2, f"{pname}'s record is stale; cannot rule out a recent departure.", [s], v2)]
        if not role_matches(claims.requester_role, r.get("title")):
            return [check(n1, C, f"{pname} works at {vendor.legal_name} as '{r.get('title')}', not as "
                                 f"'{claims.requester_role}'.{picked_note}", v1, [s], res.credits), departed]
        return [check(n1, V, f"{pname} is {r.get('title')} at {vendor.legal_name} since "
                             f"{(r.get('start_date') or '?')[:7]} (record updated {(updated_at or '?')[:10]}).{picked_note}",
                      v1, [s], res.credits), departed]
    if past_here:
        r = max(past_here, key=lambda x: (_role_score(claims.requester_role, x.get("title")), x.get("end_date") or ""))
        now_at = cur_else[0].get("name") if cur_else else None
        end = (r.get("end_date") or "")[:10] or None
        start = (r.get("start_date") or "")[:10] or None
        v2 = {"name": pname, "end_date": end, "current_employer": now_at, "title": r.get("title"), "start_date": start,
              "person_id": pid}
        return [check(n1, C, f"{pname} no longer works at {vendor.legal_name} (left {end or 'at an unknown date'})."
                             f"{picked_note}",
                      {"name": pname, "title": r.get("title"), "start_date": start, "updated_at": updated_at,
                       "person_id": pid}, [s], res.credits),
                check(n2, C, f"{pname} left {vendor.legal_name} ({r.get('title')}, {start[:7] if start else '?'} to "
                             f"{end[:7] if end else '?'})" + (f" and now works at {now_at}." if now_at else ".")
                             + picked_note, v2, [s])]
    return [unverifiable(n1, f"{pname} was found but not linked to {vendor.legal_name}; {CALLBACK}.", [s],
                         credits=res.credits),
            unverifiable(n2, f"{pname} was found but not linked to {vendor.legal_name}.", [s])]


def current_role_holder(vendor: Vendor, role: str, budget: Optional[RunBudget] = None,
                        cd: Optional[Crustdata] = None) -> Optional[dict]:
    """Who holds `role` at the vendor now, for the callback hint. Returns {name, title, start_date, updated_at,
    source} or None. Never raises."""
    if not vendor.crustdata_company_id or not role:
        return None
    cd = cd or default_client()
    full = _norm_role(role)
    try:
        res = _call(cd, "/person/search", {
            "filters": {"op": "and", "conditions": [
                {"field": "experience.employment_details.current.company_id", "type": "=",
                 "value": vendor.crustdata_company_id},
                {"field": "experience.employment_details.current.title", "type": "(.)", "value": full.title()}]},
            "fields": ["basic_profile.name", "experience.employment_details.current.title",
                       "experience.employment_details.current.start_date",
                       "experience.employment_details.current.crustdata_company_id", "metadata.updated_at"],
            "limit": 3}, budget)
    except Exception:
        return None
    best = None
    for p in (res.data or {}).get("profiles") or []:
        for r in ((p.get("experience") or {}).get("employment_details") or {}).get("current") or []:
            if r.get("crustdata_company_id") == vendor.crustdata_company_id and role_matches(role, r.get("title")):
                upd = (p.get("metadata") or {}).get("updated_at")
                if best is None or (upd or "") > (best["updated_at"] or ""):
                    best = {"name": (p.get("basic_profile") or {}).get("name"), "title": r.get("title"),
                            "start_date": (r.get("start_date") or "")[:10] or None, "updated_at": upd,
                            "source": _src(res, p.get("crustdata_person_id"), (upd or "")[:10] or None)}
    return best
