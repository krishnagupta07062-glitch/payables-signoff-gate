"""Policy v1 as ordered rules in plain code. OWNER: Krishna. BLOCK > ESCALATE > ALLOW."""
from __future__ import annotations

from gate.contracts import Check, Claims, Decision, Request, Vendor


def decide(request: Request, claims: Claims, vendor: Vendor, checks: list[Check]) -> Decision:
    raise NotImplementedError("Krishna: in progress")
