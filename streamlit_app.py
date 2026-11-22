"""Entry point for the hosted demo (Streamlit Community Cloud).

Runs the approval app (app/approvals.py) in a safe, self-contained mode for public visitors:
  - MOCK=1: stored claims and check results from fixtures/ (no model or Crustdata calls, no keys needed);
  - PAYMENTS_MODE=mock: the mock payout provider (no money, no RazorpayX keys);
  - its own database under runs/ (synthetic data only; fixtures/private/ is not in the repository).
Locally, run the full app with `streamlit run app/approvals.py`.
"""
import os
import runpy
from pathlib import Path

for key in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "CRUSTDATA_API_KEY", "RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET"):
    os.environ.pop(key, None)  # the hosted demo never calls a paid or keyed service
os.environ["MOCK"] = "1"
os.environ["PAYMENTS_MODE"] = "mock"
os.environ.setdefault("GATE_DB", str(Path(__file__).resolve().parent / "runs" / "hosted.sqlite"))
(Path(__file__).resolve().parent / "runs").mkdir(exist_ok=True)

runpy.run_path(str(Path(__file__).resolve().parent / "app" / "approvals.py"), run_name="__main__")
