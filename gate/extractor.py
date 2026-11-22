"""Untrusted text -> typed Claims. OWNER: Krishna. The model only extracts; it never decides."""
from __future__ import annotations

from gate.contracts import Claims, Request
from gate.runbudget import RunBudget


def extract(request: Request, budget: RunBudget) -> Claims:
    raise NotImplementedError("Krishna: in progress")
