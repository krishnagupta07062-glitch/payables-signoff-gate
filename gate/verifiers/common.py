"""Small helpers shared by the checks. OWNER: Lavya."""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from gate.contracts import Check, CheckStatus, Source, now_iso
from gate.verifiers.crustdata_client import mock_mode

V, C, U = CheckStatus.VERIFIED, CheckStatus.CONTRADICTED, CheckStatus.UNVERIFIABLE
HTTP_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "verifiers" / "fixtures" / "http"
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/131.0 Safari/537.36")
STALE_DAYS = 30


class HttpUnavailable(RuntimeError):
    """Network off (MOCK=1 with no fixture), timeout, or connection error."""


def check(name: str, status: CheckStatus, note: str = "", value: dict | None = None,
          sources: list[Source] | None = None, credits: float = 0.0) -> Check:
    return Check(name=name, status=status, value=value or {}, sources=sources or [], credits=round(credits, 3),
                 note=note)


def unverifiable(name: str, note: str, sources: list[Source] | None = None, value: dict | None = None,
                 credits: float = 0.0) -> Check:
    return check(name, U, note, value, sources, credits)


def http_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _real_http_get(url: str, headers: dict, timeout: float) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() or b""


# Tests replace this: fn(url, headers, timeout) -> (status, body_bytes)
HTTP_GET: Callable[[str, dict, float], tuple[int, bytes]] = _real_http_get


def http_get(url: str, headers: dict | None = None, timeout: float = 8.0) -> tuple[int, bytes]:
    """GET for the free public sources (RDAP, IFSC, GST portal). Raises HttpUnavailable, never returns junk.

    MOCK=1 reads tests/verifiers/fixtures/http/<sha256(url)>.json as {"status": int, "body": str}.
    """
    if mock_mode() and HTTP_GET is _real_http_get:
        fx = HTTP_FIXTURE_DIR / f"{http_key(url)}.json"
        if not fx.exists():
            raise HttpUnavailable(f"offline (MOCK=1, no fixture for {url})")
        j = json.loads(fx.read_text(encoding="utf-8"))
        return int(j["status"]), j.get("body", "").encode("utf-8")
    try:
        return HTTP_GET(url, {"User-Agent": BROWSER_UA, **(headers or {})}, timeout)
    except HttpUnavailable:
        raise
    except Exception as e:  # timeout, DNS, TLS reset
        raise HttpUnavailable(f"{type(e).__name__}: {str(e)[:120]}") from None


def email_domain(email: Optional[str]) -> Optional[str]:
    if not email or "@" not in email:
        return None
    d = email.rsplit("@", 1)[1].strip().strip(">").strip().lower().rstrip(".")
    return d or None


def registrable_domain(d: str) -> str:
    """'mail.bata.co.in' -> 'bata.co.in'; 'x.bata.in' -> 'bata.in'. Good enough for Indian and .com domains."""
    parts = d.lower().strip(".").split(".")
    if len(parts) >= 3 and parts[-2] in ("co", "net", "org", "gov", "ac", "firm", "gen", "ind", "com") and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def age_days(s: Optional[str]) -> Optional[int]:
    d = parse_dt(s)
    return None if d is None else (datetime.now(timezone.utc) - d).days


_SUFFIXES = r"\b(private|pvt|limited|ltd|llp|inc|incorporated|corp|corporation|co|company|plc|gmbh)\b\.?"


def norm_company(name: Optional[str]) -> str:
    s = (name or "").lower().replace("&", " and ")
    s = re.sub(_SUFFIXES, " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_person(name: Optional[str]) -> str:
    s = (name or "").lower()
    s = re.sub(r"\b(mr|mrs|ms|dr|shri|smt|ca|cs)\b\.?", " ", s)
    s = re.sub(r"[^a-z ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def src(kind: str, ref: str, **kw) -> Source:
    return Source(kind=kind, ref=ref, retrieved_at=kw.pop("retrieved_at", None) or now_iso(), **kw)
