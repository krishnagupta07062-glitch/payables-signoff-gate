from datetime import datetime, timedelta, timezone

from gate.contracts import CheckStatus, Claims, Request, RequestKind
from gate.verifiers import india_checks as ic

V, C, U = CheckStatus.VERIFIED, CheckStatus.CONTRADICTED, CheckStatus.UNVERIFIABLE


def test_gstin_checksum_known_values():
    assert ic.gstin_valid("27AAACR5055K1Z7")
    assert ic.gstin_valid("33AAACC1206D1ZN")
    assert not ic.gstin_valid("33AAACC1206D1ZM")
    assert not ic.gstin_valid("29AAACR5055K1ZX")


def test_gstin_checksum_statuses(vendor):
    assert ic.gstin_checksum(Claims(vendor_gstin="27AAACR5055K1Z7"), vendor).status == V
    assert ic.gstin_checksum(Claims(vendor_gstin="27AAACR5055K1Z8"), vendor).status == C
    vendor.gstin = None
    assert ic.gstin_checksum(Claims(), vendor).status == U


def test_gstin_matches_vendor(vendor):
    assert ic.gstin_matches_vendor(Claims(vendor_gstin="27AAACR5055K1Z7"), vendor).status == V
    c = ic.gstin_matches_vendor(Claims(vendor_gstin="29AAACR5055K1Z3"), vendor)
    assert c.status == C and "state" in c.note
    vendor.gstin = vendor.pan = vendor.state_code = None
    assert ic.gstin_matches_vendor(Claims(vendor_gstin="27AAACR5055K1Z7"), vendor).status == U


def test_gstin_exists(vendor, http):
    http({"goodservice": (200, {"bzgddtls": [{"gdes": "leather", "hsncd": "4107"}]})})
    c = ic.gstin_exists(Claims(vendor_gstin="27AAACR5055K1Z7"), vendor)
    assert c.status == V and c.value["hsn_codes"] == ["4107"] and c.sources[0].ref.startswith("https://services.gst")
    http({"goodservice": (200, {"errorCode": "FO8000", "message": "No records found"})})
    assert ic.gstin_exists(Claims(vendor_gstin="27AAACR5055K1Z7"), vendor).status == U  # never CONTRADICTED
    http({"goodservice": (0, TimeoutError("slow"))})
    assert ic.gstin_exists(Claims(vendor_gstin="27AAACR5055K1Z7"), vendor).status == U


def test_ifsc(vendor, http):
    http({"HDFC0CAGSBK": (200, {"BANK": "HDFC Bank", "BRANCH": "X", "CITY": "Pune", "IMPS": True}),
          "ABCD0123456": (404, "Not Found")})
    assert ic.ifsc_valid(Claims(pay_to_ifsc="HDFC0CAGSBK"), vendor).status == V
    assert ic.ifsc_valid(Claims(pay_to_ifsc="ABCD0123456"), vendor).status == C
    assert ic.ifsc_valid(Claims(pay_to_ifsc="BAD"), vendor).status == C
    http({})  # every URL times out
    assert ic.ifsc_valid(Claims(pay_to_ifsc="HDFC0CAGSBK"), vendor).status == U


def _req(email):
    return Request(request_id="R", kind=RequestKind.BANK_CHANGE, raw_text="", sender_email=email)


def _rdap(days):
    d = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"events": [{"eventAction": "registration", "eventDate": d}]}


def test_domain_age(vendor, http):
    http({"old.in": (200, _rdap(2000)), "new.com": (200, _rdap(10)), "gone.com": (404, "")})
    assert ic.domain_age_days(_req("a@old.in"), vendor).status == V
    c = ic.domain_age_days(_req("a@new.com"), vendor)
    assert c.status == C and c.value["age_days"] < 90 and "rdap.verisign.com" in c.sources[0].ref
    assert ic.domain_age_days(_req("a@gone.com"), vendor).status == C
    assert ic.domain_age_days(_req("a@other.com"), vendor).status == U  # timeout -> never a pass


def test_domain_age_offline_is_unverifiable(vendor):
    # MOCK=1 and no fixture: no network, fail closed
    assert ic.domain_age_days(_req("a@acmeleaf.in"), vendor).status == U


def test_lookalike(vendor):
    assert ic.sender_domain_lookalike(_req("x@acmeleaf.in"), vendor).status == V
    assert ic.sender_domain_lookalike(_req("x@mail.acmeleaf.in"), vendor).status == V
    for bad in ("acrneleaf.in", "acmeleaf.co", "acme1eaf.in", "acmeleaf-payments.com", "acmeleaff.in"):
        c = ic.sender_domain_lookalike(_req(f"x@{bad}"), vendor)
        assert c.status == C, bad
    assert ic.sender_domain_lookalike(_req("x@gmail.com"), vendor).status == V  # different, not a lookalike
    r = _req("x@acmeleaf.in")
    r.reply_to = "pay@acmeleaf-in.com"
    assert ic.sender_domain_lookalike(r, vendor).status == C
