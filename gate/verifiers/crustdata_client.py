"""Crustdata API client (API version 2025-11-01) with a cache, a rate limiter and budget charging. OWNER: Lavya.

Usage:
    from gate.verifiers.crustdata_client import Crustdata
    cd = Crustdata()
    res = cd.call("/company/identify", {"domains": ["bata.in"]}, budget=budget)
    res.data, res.request_id, res.credits, res.cached

    cd.post("/company/search", {...})     # old interface, still works (no budget, no cache)

Behaviour:
- Cache: SQLite under cache/, keyed by sha256(path + canonical body + API version). A cached answer costs 0.
  An "inflight" row is written before each live call, so a crash mid-call is visible. A 4xx answer is
  cached too and replayed as the same error; 5xx, 429 and timeouts are not cached, so the next run retries.
- Rate limit: 5 calls per rolling minute (shared by every thread in the process).
- 429: retry with backoff (up to 3 tries), then CrustdataRateLimited.
- Timeout / network error: CrustdataTimeout. Other HTTP errors: CrustdataError.
- MOCK=1: never touches the network. Answers come from tests/verifiers/fixtures/<cache key>.json;
  a missing fixture raises CrustdataUnavailable. Checks turn every one of these errors into UNVERIFIABLE.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

BASE_URL = "https://api.crustdata.com"
API_VERSION = "2025-11-01"
ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = Path(os.environ.get("CRUSTDATA_CACHE_DIR", ROOT / "cache"))
FIXTURE_DIR = ROOT / "tests" / "verifiers" / "fixtures"
RATE_LIMIT_PER_MIN = int(os.environ.get("CRUSTDATA_RPM", "5"))
TIMEOUT_S = float(os.environ.get("CRUSTDATA_TIMEOUT_S", "15"))

# expected cost per call, used for budget.ensure() before the call
EXPECTED_CREDITS = {
    "/company/identify": 0.2, "/company/enrich": 2.0, "/company/search": 0.1,
    "/person/search": 0.7, "/web/enrich/live": 1.0, "/web/search/live": 1.0,
}


class CrustdataError(RuntimeError):
    """An HTTP error or bad response from Crustdata."""


class CrustdataTimeout(CrustdataError):
    """The call timed out or the network failed."""


class CrustdataRateLimited(CrustdataError):
    """Still rate-limited (429) after retries."""


class CrustdataUnavailable(CrustdataError):
    """No key, or MOCK=1 with no fixture for this call."""


@dataclass
class CallResult:
    data: Any
    request_id: Optional[str]
    credits: float
    cached: bool
    path: str
    key: str
    retrieved_at: str


def mock_mode() -> bool:
    return os.environ.get("MOCK", "0").strip() in ("1", "true", "yes")


def cache_key(path: str, body: dict | None) -> str:
    canon = json.dumps(body or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(f"{path}|{canon}|{API_VERSION}".encode("utf-8")).hexdigest()


def _load_key() -> Optional[str]:
    key = os.environ.get("CRUSTDATA_API_KEY")
    if not key:
        env = ROOT / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("CRUSTDATA_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
    return key or None


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class _RateLimiter:
    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.calls: deque[float] = deque()
        self.lock = threading.Lock()

    def wait(self, max_wait: float = 65.0) -> None:
        deadline = time.monotonic() + max_wait
        while True:
            with self.lock:
                now = time.monotonic()
                while self.calls and now - self.calls[0] >= 60.0:
                    self.calls.popleft()
                if len(self.calls) < self.per_minute:
                    self.calls.append(now)
                    return
                sleep_for = 60.0 - (now - self.calls[0]) + 0.05
            if time.monotonic() + sleep_for > deadline:
                raise CrustdataRateLimited("local rate limit: no slot within the wait limit")
            time.sleep(min(sleep_for, 5.0))


_LIMITER = _RateLimiter(RATE_LIMIT_PER_MIN)
_DB_LOCK = threading.Lock()

# transport(method, url, body, headers, timeout) -> (status, headers_dict, body_bytes). Tests replace it.
Transport = Callable[[str, str, Optional[bytes], dict, float], tuple[int, dict, bytes]]


def urllib_transport(method: str, url: str, body: Optional[bytes], headers: dict, timeout: float):
    req = urllib.request.Request(url, method=method, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read() or b""


class Crustdata:
    def __init__(self, api_key: str | None = None, transport: Transport | None = None,
                 cache_dir: Path | None = None, use_cache: bool = True, limiter: _RateLimiter | None = None):
        self.api_key = api_key or _load_key()
        self.transport = transport or urllib_transport
        self.use_cache = use_cache
        self.cache_dir = Path(cache_dir or CACHE_DIR)
        self.limiter = limiter or _LIMITER
        self.last_credits_used = None
        self._db_path = self.cache_dir / "crustdata.sqlite"

    # ------------------------------------------------------------------ cache
    def _db(self) -> sqlite3.Connection:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self._db_path, timeout=30)
        con.execute("create table if not exists cache(key text primary key, path text, body text, state text,"
                    " response text, credits real, request_id text, at text)")
        return con

    def _cache_get(self, key: str) -> Optional[tuple]:
        if not self.use_cache:
            return None
        with _DB_LOCK:
            con = self._db()
            try:
                return con.execute("select response, request_id, at, state from cache where key=? "
                                   "and state in ('done', 'error')", (key,)).fetchone()
            finally:
                con.close()

    def _cache_put(self, key: str, path: str, body: dict | None, state: str, response: Any = None,
                   credits: float = 0.0, request_id: str | None = None) -> None:
        if not self.use_cache:
            return
        with _DB_LOCK:
            con = self._db()
            try:
                con.execute("insert or replace into cache values(?,?,?,?,?,?,?,?)",
                            (key, path, json.dumps(body or {}, sort_keys=True), state,
                             json.dumps(response) if response is not None else None, credits, request_id, _now_iso()))
                con.commit()
            finally:
                con.close()

    # ------------------------------------------------------------------ main entry
    def call(self, path: str, body: dict | None = None, budget=None, method: str = "POST",
             max_retries: int = 3) -> CallResult:
        key = cache_key(path, body)
        hit = self._cache_get(key)
        if hit:
            data = json.loads(hit[0])
            if budget is not None:
                budget.charge("crustdata", path, 0.0, request_id=hit[1], cached=True,
                              note="cached error" if hit[3] == "error" else "")
            if hit[3] == "error":  # a 4xx is deterministic: replay it instead of re-asking
                raise CrustdataError(f"{data.get('status')} {path} (cached): {data.get('body', '')[:300]}")
            return CallResult(data, hit[1], 0.0, True, path, key, hit[2])

        if mock_mode():
            fx = FIXTURE_DIR / f"{key}.json"
            if not fx.exists():
                raise CrustdataUnavailable(f"MOCK=1 and no fixture for {path} (key {key[:12]})")
            data = json.loads(fx.read_text(encoding="utf-8"))
            if budget is not None:
                budget.charge("crustdata", path, 0.0, cached=True, note="mock fixture")
            return CallResult(data, "mock", 0.0, True, path, key, _now_iso())

        if not self.api_key:
            raise CrustdataUnavailable("CRUSTDATA_API_KEY not set (env var or .env)")
        if budget is not None:
            budget.ensure(EXPECTED_CREDITS.get(path, 1.0))

        self._cache_put(key, path, body, "inflight")
        headers = {"Authorization": f"Bearer {self.api_key}", "x-api-version": API_VERSION,
                   "Content-Type": "application/json", "Accept": "application/json"}
        payload = json.dumps(body).encode("utf-8") if body is not None and method == "POST" else None
        attempt = 0
        while True:
            self.limiter.wait()
            try:
                status, hdrs, raw = self.transport(method, BASE_URL + path, payload, headers, TIMEOUT_S)
            except (TimeoutError, OSError) as e:  # socket.timeout and URLError are OSError subclasses
                raise CrustdataTimeout(f"{path}: {type(e).__name__}: {e}") from None
            if status == 429 and attempt < max_retries:
                attempt += 1
                retry_after = hdrs.get("retry-after")
                time.sleep(float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt)
                continue
            break

        request_id = hdrs.get("x-request-id")
        credits = float(hdrs.get("x-credits-used") or 0.0)
        self.last_credits_used = credits
        if budget is not None:
            budget.charge("crustdata", path, credits, request_id=request_id,
                          note="" if status < 400 else f"http {status}")
        if status == 429:
            raise CrustdataRateLimited(f"{path}: 429 after {max_retries} retries")
        if status >= 400:
            body_txt = raw[:300].decode("utf-8", "replace")
            if status < 500:  # 4xx (bad filter, no access) repeats identically: cache it. 5xx is retried next run.
                self._cache_put(key, path, body, "error", {"status": status, "body": body_txt}, credits, request_id)
            raise CrustdataError(f"{status} {path}: {body_txt}")
        try:
            data = json.loads(raw)
        except ValueError:
            raise CrustdataError(f"{path}: response is not JSON") from None
        self._cache_put(key, path, body, "done", data, credits, request_id)
        return CallResult(data, request_id, credits, False, path, key, _now_iso())

    # ------------------------------------------------------------------ old interface
    def get(self, path: str):
        return self.call(path, None, method="GET").data

    def post(self, path: str, body: dict):
        return self.call(path, body).data

    def credits(self) -> float:
        """Free call: current credit balance (never cached)."""
        old, self.use_cache = self.use_cache, False
        try:
            return self.get("/account/credits")["account"]["credits"]
        finally:
            self.use_cache = old


_DEFAULT: Optional[Crustdata] = None


def default_client() -> Crustdata:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = Crustdata()
    return _DEFAULT


def set_default_client(client: Optional[Crustdata]) -> None:
    """Tests and scripts swap the shared client."""
    global _DEFAULT
    _DEFAULT = client


if __name__ == "__main__":
    cd = Crustdata()
    print("Credits:", cd.credits())
