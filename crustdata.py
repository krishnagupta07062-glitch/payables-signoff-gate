"""Shim: `python crustdata.py` prints the credit balance and enabled endpoints."""
from gate.verifiers.crustdata_client import Crustdata

if __name__ == "__main__":
    cd = Crustdata()
    print("Credits:", cd.credits())
    eps = cd.get("/account/endpoints?status=enabled")["endpoints"]
    print("Enabled endpoints:", ", ".join(e["path"] for e in eps))
