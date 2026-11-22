"""Free Indian and domain checks: GSTIN, IFSC, RDAP domain age, lookalike domains. OWNER: Lavya.

Every function returns a contracts.Check and never raises for bad input or a failed source:
a source that can't answer gives UNVERIFIABLE with a note naming what is missing.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Optional

from gate.contracts import Check, Claims, Request, Vendor
from gate.runbudget import RunBudget
from gate.verifiers.common import (C, U, V, HttpUnavailable, check, email_domain, http_get, norm_company,
                                   registrable_domain, src, unverifiable)

# ---------------------------------------------------------------------------------------- GSTIN

_A = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z][A-Z][0-9A-Z]$")


def gstin_check_char(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        p = _A.index(ch) * (1 if i % 2 == 0 else 2)
        total += p // 36 + p % 36
    return _A[(36 - total % 36) % 36]


def gstin_valid(g: str) -> bool:
    g = (g or "").strip().upper()
    return bool(GSTIN_RE.fullmatch(g)) and gstin_check_char(g[:14]) == g[14]


def _claimed_gstin(claims: Claims, vendor: Vendor) -> Optional[str]:
    g = claims.vendor_gstin or vendor.gstin
    return re.sub(r"\s+", "", g).upper() if g else None


def gstin_checksum(claims: Claims, vendor: Vendor) -> Check:
    name = "gstin_checksum"
    g = _claimed_gstin(claims, vendor)
    s = [src("local", "GSTIN mod-36 check digit (CBIC format)", excerpt=g)]
    if not g:
        return unverifiable(name, "No GSTIN on the invoice or the vendor record.", s)
    if not GSTIN_RE.fullmatch(g):
        return check(name, C, f"GSTIN {g} is not in the GSTIN format.", {"gstin": g}, s)
    if gstin_check_char(g[:14]) != g[14]:
        return check(name, C, f"GSTIN {g} fails its check digit (expected {gstin_check_char(g[:14])}).",
                     {"gstin": g}, s)
    return check(name, V, f"GSTIN {g} has a valid check digit.", {"gstin": g}, s)


def gstin_matches_vendor(claims: Claims, vendor: Vendor) -> Check:
    name = "gstin_matches_vendor"
    g = _claimed_gstin(claims, vendor)
    s = [src("vendor_master", f"vendor:{vendor.vendor_id}", excerpt=f"gstin={vendor.gstin} pan={vendor.pan} "
                                                                    f"state={vendor.state_code}")]
    if not g or len(g) != 15:
        return unverifiable(name, "No well-formed GSTIN to compare with the vendor record.", s)
    pan, state = g[2:12], g[:2]
    value = {"gstin": g, "pan": pan, "state_code": state}
    problems = []
    if vendor.gstin and g != vendor.gstin.upper():
        problems.append(f"the invoice GSTIN {g} differs from the vendor's GSTIN {vendor.gstin}")
    if vendor.pan and pan != vendor.pan.upper():
        problems.append(f"its PAN {pan} differs from the vendor's PAN {vendor.pan}")
    if vendor.state_code and state != str(vendor.state_code).zfill(2):
        problems.append(f"its state code {state} differs from the vendor's state {vendor.state_code}")
    if problems:
        return check(name, C, "GSTIN does not match the vendor record: " + "; ".join(problems) + ".", value, s)
    if not (vendor.gstin or vendor.pan or vendor.state_code):
        return unverifiable(name, "The vendor record has no GSTIN, PAN or state to compare with.", s, value)
    return check(name, V, "GSTIN's PAN and state match the vendor record.", value, s)


GST_GOODSERVICE = "https://services.gst.gov.in/services/api/search/goodservice?gstin={g}"


def gstin_exists(claims: Claims, vendor: Vendor, budget: RunBudget | None = None) -> Check:
    name = "gstin_exists"
    g = _claimed_gstin(claims, vendor)
    if not g or not gstin_valid(g):
        return unverifiable(name, "No valid GSTIN to look up on the GST portal.")
    url = GST_GOODSERVICE.format(g=g)
    s = [src("gst_portal", url)]
    try:
        if budget is not None:
            budget.ensure(0)
        status, body = http_get(url, {"Referer": "https://services.gst.gov.in/services/searchtp",
                                      "Accept": "application/json"}, timeout=10)
        if budget is not None:
            budget.charge("gst_portal", "goodservice", 0.0, note=f"http {status}")
    except HttpUnavailable as e:
        return unverifiable(name, f"GST portal unreachable ({e}); cannot confirm the GSTIN is registered.", s)
    except Exception as e:
        return unverifiable(name, f"GST portal check failed: {e}", s)
    if status != 200:
        return unverifiable(name, f"GST portal answered HTTP {status}; cannot confirm the GSTIN is registered.", s)
    try:
        j = json.loads(body)
    except ValueError:
        return unverifiable(name, "GST portal answer was not JSON (blocked or changed).", s)
    items = (j.get("bzgddtls") or []) + (j.get("bzsdtls") or [])
    if items:
        codes = [i.get("hsncd") or i.get("saccd") for i in items if isinstance(i, dict)]
        s[0].excerpt = f"{len(items)} goods/services registered"
        return check(name, V, f"GST portal lists GSTIN {g} with {len(items)} registered goods/services codes.",
                     {"gstin": g, "hsn_codes": [c for c in codes if c][:10]}, s)
    # FO8000 "No records found" can also mean a genuine registration with no HSN list: never a pass, never a block
    msg = j.get("message") or j.get("errorCode") or "no records"
    return unverifiable(name, f"GST portal has no record for GSTIN {g} ({msg}); confirm the registration by hand.",
                        s, {"gstin": g})


# ----------------------------------------------------------------------------------------- IFSC

IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


def ifsc_valid(claims: Claims, vendor: Vendor, budget: RunBudget | None = None) -> Check:
    name = "ifsc_valid"
    ifsc = (claims.pay_to_ifsc or "").strip().upper()
    if not ifsc and vendor.bank_accounts:
        verified = [a for a in vendor.bank_accounts if a.verified_at] or vendor.bank_accounts
        ifsc = verified[0].ifsc.upper()
    if not ifsc:
        return unverifiable(name, "No IFSC in the request or on the vendor record.")
    url = f"https://ifsc.razorpay.com/{ifsc}"
    s = [src("ifsc", url)]
    if not IFSC_RE.fullmatch(ifsc):
        return check(name, C, f"IFSC {ifsc} is not in the IFSC format.", {"ifsc": ifsc}, s)
    try:
        if budget is not None:
            budget.ensure(0)
        status, body = http_get(url, {"Accept": "application/json"}, timeout=8)
        if budget is not None:
            budget.charge("ifsc", "ifsc.razorpay.com", 0.0, note=f"http {status}")
    except HttpUnavailable as e:
        return unverifiable(name, f"IFSC lookup unreachable ({e}).", s, {"ifsc": ifsc})
    if status == 404:
        return check(name, C, f"IFSC {ifsc} does not exist (Razorpay IFSC directory: Not Found).", {"ifsc": ifsc}, s)
    if status != 200:
        return unverifiable(name, f"IFSC lookup answered HTTP {status}.", s, {"ifsc": ifsc})
    try:
        j = json.loads(body)
    except ValueError:
        return unverifiable(name, "IFSC lookup answer was not JSON.", s, {"ifsc": ifsc})
    value = {"ifsc": ifsc, "bank": j.get("BANK"), "branch": j.get("BRANCH"), "city": j.get("CITY"),
             "state": j.get("STATE"), "imps": j.get("IMPS"), "neft": j.get("NEFT"), "rtgs": j.get("RTGS")}
    s[0].excerpt = f"{j.get('BANK')}, {j.get('BRANCH')}, {j.get('CITY')}"
    return check(name, V, f"IFSC {ifsc} is {j.get('BANK')}, {j.get('BRANCH')} ({j.get('CITY')}).", value, s)


# ------------------------------------------------------------------------------------ RDAP age

RDAP_BASES = {"com": "https://rdap.verisign.com/com/v1/", "net": "https://rdap.verisign.com/net/v1/",
              "in": "https://rdap.nixiregistry.in/rdap/"}
MIN_DOMAIN_AGE_DAYS = 90


def rdap_url(domain: str) -> str:
    tld = domain.rsplit(".", 1)[-1]
    return RDAP_BASES.get(tld, "https://rdap.org/") + "domain/" + domain


def domain_age_days(request: Request, vendor: Vendor, budget: RunBudget | None = None,
                    domain: Optional[str] = None) -> Check:
    name = "domain_age_days"
    d = domain or email_domain(request.sender_email)
    if not d:
        return unverifiable(name, "No sender domain to check.")
    d = registrable_domain(d)
    url = rdap_url(d)
    s = [src("rdap", url)]
    try:
        if budget is not None:
            budget.ensure(0)
        status, body = http_get(url, {"Accept": "application/rdap+json"}, timeout=8)
        if budget is not None:
            budget.charge("rdap", url.split("/domain/")[0], 0.0, note=f"http {status}")
    except HttpUnavailable as e:
        return unverifiable(name, f"RDAP lookup for {d} failed ({e}); domain age unknown.", s, {"domain": d})
    if status == 404:
        return check(name, C, f"{d} is not registered (RDAP 404), yet mail claims to come from it.",
                     {"domain": d, "age_days": None, "registered_at": None}, s)
    if status != 200:
        return unverifiable(name, f"RDAP answered HTTP {status} for {d}; domain age unknown.", s, {"domain": d})
    try:
        j = json.loads(body)
    except ValueError:
        return unverifiable(name, f"RDAP answer for {d} was not JSON.", s, {"domain": d})
    reg = [e.get("eventDate") for e in j.get("events", []) if e.get("eventAction") == "registration"]
    if not reg or not reg[0]:
        return unverifiable(name, f"RDAP record for {d} has no registration date.", s, {"domain": d})
    try:
        at = datetime.fromisoformat(reg[0].replace("Z", "+00:00"))
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
    except ValueError:
        return unverifiable(name, f"RDAP registration date for {d} is unreadable: {reg[0]}.", s, {"domain": d})
    age = (datetime.now(timezone.utc) - at).days
    s[0].record_date = at.date().isoformat()
    s[0].excerpt = f"registration {reg[0]}"
    value = {"domain": d, "age_days": age, "registered_at": at.date().isoformat()}
    if age < MIN_DOMAIN_AGE_DAYS:
        return check(name, C, f"{d} was registered {age} days ago ({at.date()}), under {MIN_DOMAIN_AGE_DAYS} days.",
                     value, s)
    return check(name, V, f"{d} was registered {age} days ago ({at.date()}).", value, s)


# ------------------------------------------------------------------------------------ lookalike

_CONFUSABLES = str.maketrans({"0": "o", "1": "l", "3": "e", "5": "s", "4": "a", "7": "t", "8": "b",
                              "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "і": "i", "ԁ": "d", "х": "x",
                              "у": "y", "ѕ": "s", "ј": "j", "һ": "h", "ӏ": "l", "ɑ": "a", "ο": "o", "ν": "v"})


def skeleton(d: str) -> str:
    d = d.lower().strip(".")
    try:
        d = ".".join(p.encode("ascii").decode("idna") if p.startswith("xn--") else p for p in d.split("."))
    except Exception:
        pass
    d = unicodedata.normalize("NFKC", d).translate(_CONFUSABLES)
    return d.replace("rn", "m").replace("vv", "w")


def lev(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _label(d: str) -> str:
    """'bata.co.in' -> 'bata'; 'bata-india.com' -> 'bata-india'."""
    return registrable_domain(d).split(".")[0]


def sender_domain_lookalike(request: Request, vendor: Vendor) -> Check:
    name = "sender_domain_lookalike"
    d = email_domain(request.sender_email)
    vendor_domains = [x.lower() for x in vendor.domains]
    s = [src("local", "punycode, homoglyph map, edit distance <= 2, brand containment",
             excerpt=f"vendor domains: {', '.join(vendor_domains) or 'none'}")]
    if not d:
        return unverifiable(name, "No sender domain to check.", s)
    reg = registrable_domain(d)
    extra = []
    rt = email_domain(request.reply_to)
    if rt and registrable_domain(rt) != reg:
        extra.append(registrable_domain(rt))
    if not vendor_domains:
        return unverifiable(name, "The vendor record has no domains to compare with.", s, {"domain": reg})

    def judge(dom: str) -> Optional[dict]:
        if dom in vendor_domains or any(dom == registrable_domain(v) for v in vendor_domains):
            return None
        sk = skeleton(dom)
        best = None
        for v in vendor_domains:
            vr = registrable_domain(v)
            dist = lev(sk, skeleton(vr))
            lab_d, lab_v = _label(sk), _label(skeleton(vr))
            reason = None
            if "xn--" in dom:
                reason = "punycode (internationalised) domain"
            if sk == skeleton(vr):
                reason = "same as the vendor domain after removing look-alike characters"
            elif dist <= 2:
                reason = f"{dist} character(s) from the vendor domain"
            elif lab_d == lab_v:
                reason = "same name under a different ending"
            elif len(lab_v) >= 4 and lab_v in lab_d:
                reason = "contains the vendor's name"
            brand = norm_company(vendor.legal_name).split(" ")[0] if vendor.legal_name else ""
            if not reason and len(brand) >= 4 and brand in lab_d.replace("-", ""):
                reason = f"contains the vendor's name '{brand}'"
            if reason and (best is None or dist < best["distance"]):
                best = {"domain": dom, "closest": vr, "distance": dist, "reason": reason}
        return best

    for dom in [reg] + extra:
        hit = judge(dom)
        if hit:
            which = "Sender" if dom == reg else "Reply-To"
            return check(name, C, f"{which} domain {dom} imitates the vendor domain {hit['closest']}: {hit['reason']}.",
                         hit, s)
    if reg in vendor_domains or any(reg == registrable_domain(v) for v in vendor_domains):
        return check(name, V, f"{reg} is the vendor's own domain.", {"domain": reg, "closest": reg, "distance": 0,
                                                                     "reason": "exact"}, s)
    return check(name, V, f"{reg} does not imitate any vendor domain (it is simply a different domain).",
                 {"domain": reg, "closest": None, "distance": None, "reason": "unrelated"}, s)
