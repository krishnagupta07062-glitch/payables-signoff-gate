import os
import shutil
import sqlite3

import pytest

from gate import ledger, store
from gate.contracts import Claims, Request, RequestKind, Verdict

from tests.pay.conftest import make_decision, make_vendor


def test_vendor_round_trip_and_no_full_account(db):
    v = make_vendor()
    store.upsert_vendor(v)
    got = store.get_vendor("V-ACME")
    got.created_at = v.created_at
    assert got == v
    raw = b"".join(open(f, "rb").read() for f in (db, db + "-wal") if os.path.exists(f))
    assert b"50100012345678" not in raw


def test_claims_account_is_redacted(db):
    req = Request("R1", RequestKind.INVOICE, "pay 50100012345678 now", sender_email="a@acme-test.example",
                  vendor_id="V-ACME")
    store.save_request(req)
    d = make_decision(request_id="R1")
    d.claims = Claims(invoice_number="INV-42", amount_inr=12500.0, pay_to_account="50100012345678")
    store.save_decision(d)
    row = store.get_request_row("R1")
    assert "50100012345678" not in row["claims"]
    assert "pay 50100012345678" not in str(row)
    back = store.get_decision("R1")
    assert back.claims.pay_to_account is None and back.verdict == Verdict.ALLOW
    h = store.history_for("V-ACME")
    assert h[0]["invoice_number"] == "INV-42" and h[0]["account_hash"] == d.action.account_hash
    assert h[0]["paid"] is False


def test_escalate_queue_and_double_click(db):
    d = make_decision(Verdict.ESCALATE, request_id="R2")
    store.save_decision(d)
    assert [p["request_id"] for p in store.pending_escalations()] == ["R2"]
    assert store.record_approval("R2", "alice", True) is True
    assert store.record_approval("R2", "alice", True) is False   # double click
    assert store.record_approval("R2", "bob", False) is False    # late reject
    assert store.get_decision_row("R2")["state"] == store.APPROVED
    assert store.pending_escalations() == []
    assert len(store.approvals_for("R2")) == 1
    store.save_decision(d)                                         # a re-run never reopens it
    assert store.get_decision_row("R2")["state"] == store.APPROVED


def test_load_fixtures_hashes_accounts(db, tmp_path):
    p = tmp_path / "vendors.json"
    p.write_text('[{"vendor_id":"V9","legal_name":"Nine Ltd","domains":["nine.example"],'
                 '"bank_accounts":[{"ifsc":"ICIC0000001","account_number":"000111222333","holder_name":"Nine"}]}]')
    assert store.load_fixtures(str(p)) == 1
    v = store.get_vendor("V9")
    assert v.bank_accounts[0].account_last4 == "2333"
    assert v.bank_accounts[0].account_hash == store.hash_account("000111222333")
    assert store.find_vendor_by_domain("NINE.example").vendor_id == "V9"


def test_ledger_chain_and_triggers(db):
    for i in range(3):
        ledger.append("test", {"i": i})
    store.save_decision(make_decision())
    assert ledger.verify()["ok"] is True
    con = store.connect()
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("UPDATE ledger SET body='{}' WHERE id=1")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("DELETE FROM ledger WHERE id=2")
    con.close()
    assert ledger.verify()["ok"] is True


def test_tampered_copy_is_caught(db, tmp_path):
    for i in range(4):
        ledger.append("test", {"amount": 100 * i})
    con = store.connect()
    con.execute("PRAGMA wal_checkpoint(FULL)")
    con.close()
    copy = str(tmp_path / "copy.sqlite")
    shutil.copy(db, copy)
    raw = sqlite3.connect(copy)
    raw.execute("DROP TRIGGER ledger_no_update")
    raw.execute("UPDATE ledger SET body=replace(body, '200', '999') WHERE id=3")
    raw.commit()
    raw.close()
    res = ledger.verify(copy)
    assert res["ok"] is False and res["first_bad_row"] == 3
    assert ledger.verify()["ok"] is True                     # the original is intact


def test_deleted_row_in_copy_is_caught(db, tmp_path):
    for i in range(3):
        ledger.append("test", {"i": i})
    con = store.connect(); con.execute("PRAGMA wal_checkpoint(FULL)"); con.close()
    copy = str(tmp_path / "copy2.sqlite")
    shutil.copy(db, copy)
    raw = sqlite3.connect(copy)
    raw.execute("DROP TRIGGER ledger_no_delete")
    raw.execute("DELETE FROM ledger WHERE id=2")
    raw.commit(); raw.close()
    res = ledger.verify(copy)
    assert res["ok"] is False and res["first_bad_row"] == 3
