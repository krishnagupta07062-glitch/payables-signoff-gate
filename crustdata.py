"""Minimal Crustdata API client (API version 2025-11-01).

Usage:
    from crustdata import cd
    cd.post("/company/search", {"filters": {...}, "limit": 10})
    cd.get("/account/endpoints")
"""
import json
import os
import urllib.request
from pathlib import Path

BASE_URL = "https://api.crustdata.com"
API_VERSION = "2025-11-01"


def _load_key() -> str:
    key = os.environ.get("CRUSTDATA_API_KEY")
    if not key:
        env = Path(__file__).with_name(".env")
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("CRUSTDATA_API_KEY="):
                    key = line.split("=", 1)[1].strip()
    if not key:
        raise RuntimeError("CRUSTDATA_API_KEY not set (env var or .env)")
    return key


class Crustdata:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or _load_key()
        self.last_credits_used = None

    def _request(self, method: str, path: str, body: dict | None = None):
        req = urllib.request.Request(
            BASE_URL + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "x-api-version": API_VERSION,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                self.last_credits_used = resp.headers.get("X-Credits-Used")
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{e.code} {path}: {e.read().decode()}") from None

    def get(self, path: str):
        return self._request("GET", path)

    def post(self, path: str, body: dict):
        return self._request("POST", path, body)

    def credits(self) -> float:
        """Free call: current credit balance."""
        return self.get("/account/credits")["account"]["credits"]



cd = Crustdata()

if __name__ == "__main__":
    print("Credits:", cd.credits())
    eps = cd.get("/account/endpoints?status=enabled")["endpoints"]
    print("Enabled endpoints:", ", ".join(e["path"] for e in eps))
