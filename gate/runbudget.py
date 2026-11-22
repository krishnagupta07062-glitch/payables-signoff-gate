"""Per-run ceiling on credits and time, and a ledger line for every external call.

Every Crustdata call and every model call goes through RunBudget.charge(). Lines go to
runs/<run_id>/calls.jsonl. (Ayush may mirror them into SQLite; the interface stays the same.)
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

from gate.contracts import now_iso

RUNS_DIR = Path(os.environ.get("GATE_RUNS_DIR", Path(__file__).resolve().parent.parent / "runs"))


class BudgetExceeded(RuntimeError):
    """Raised before a call that would break the run's credit or time ceiling."""


class RunBudget:
    def __init__(self, max_credits: float = 25.0, max_seconds: float = 300.0, run_id: str | None = None):
        self.run_id = run_id or time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        self.max_credits = max_credits
        self.max_seconds = max_seconds
        self.started = time.monotonic()
        self.credits = 0.0
        self.calls: list[dict] = []
        self.dir = RUNS_DIR / self.run_id
        self.dir.mkdir(parents=True, exist_ok=True)

    # --- checks before a call ---------------------------------------------------------------
    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def remaining_credits(self) -> float:
        return self.max_credits - self.credits

    def ensure(self, expected_credits: float = 0.0) -> None:
        """Call before an external request. Raises BudgetExceeded instead of overspending."""
        if self.elapsed > self.max_seconds:
            raise BudgetExceeded(f"time ceiling {self.max_seconds}s reached")
        if self.credits + expected_credits > self.max_credits:
            raise BudgetExceeded(f"credit ceiling {self.max_credits} reached ({self.credits:.2f} spent)")

    def lower_ceiling(self, max_credits: float) -> None:
        """The owner can cut the ceiling mid-run."""
        self.max_credits = min(self.max_credits, max_credits)

    # --- after a call -------------------------------------------------------------------------
    def charge(self, provider: str, endpoint: str, credits: float = 0.0, request_id: str | None = None,
               cached: bool = False, tokens_in: int = 0, tokens_out: int = 0, note: str = "") -> dict:
        line = {
            "ts": now_iso(), "run_id": self.run_id, "provider": provider, "endpoint": endpoint,
            "credits": 0.0 if cached else float(credits), "cached": cached, "request_id": request_id,
            "tokens_in": tokens_in, "tokens_out": tokens_out, "note": note,
        }
        self.credits += line["credits"]
        self.calls.append(line)
        with open(self.dir / "calls.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
        return line

    def summary(self) -> dict:
        return {"run_id": self.run_id, "credits": round(self.credits, 3), "calls": len(self.calls),
                "cached_calls": sum(c["cached"] for c in self.calls), "seconds": round(self.elapsed, 1)}
