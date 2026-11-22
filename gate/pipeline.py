"""The only module that calls all three parts. OWNER: Krishna."""
from __future__ import annotations

from gate.contracts import Decision, Request
from gate.runbudget import RunBudget


def run(request: Request, budget: RunBudget) -> Decision:
    """Load the trusted vendor record -> extract -> verifiers.run_all -> policy.decide
    -> store.save_decision -> executor (ALLOW only)."""
    raise NotImplementedError("Krishna: in progress")
