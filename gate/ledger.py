"""Append-only, hash-chained audit ledger. OWNER: Ayush.

Every request, check, decision, approval and payout event is appended. verify() replays the chain.

Row:   id, prev_hash, hash, event_type, body, at
body:  canonical_json({"event_type", "at", "payload"})
hash:  sha256(prev_hash + body)          (the first row's prev_hash is 64 zeros)

SQLite triggers RAISE(ABORT) on any UPDATE or DELETE of a ledger row, so the application cannot edit
history; a row changed behind SQLite's back (a raw copy of the file with the triggers dropped) is
caught by verify(), because its hash, or the next row's prev_hash, no longer matches.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Optional

from gate.contracts import canonical_json, now_iso

GENESIS = "0" * 64


def _hash(prev_hash: str, body: str) -> str:
    return hashlib.sha256((prev_hash + body).encode("utf-8")).hexdigest()


def append(event_type: str, payload: dict, con: Optional[sqlite3.Connection] = None) -> str:
    """Append an event; returns its hash. Body hashed with contracts.canonical_json.
    Pass `con` (inside an open BEGIN IMMEDIATE transaction) to append atomically with a store write."""
    from gate import store
    if con is None:
        with store.tx() as c:
            return append(event_type, payload, con=c)
    at = now_iso()
    body = canonical_json({"event_type": event_type, "at": at, "payload": payload})
    row = con.execute("SELECT hash FROM ledger ORDER BY id DESC LIMIT 1").fetchone()
    prev = row[0] if row else GENESIS
    h = _hash(prev, body)
    con.execute("INSERT INTO ledger(prev_hash, hash, event_type, body, at) VALUES(?,?,?,?,?)",
                (prev, h, event_type, body, at))
    return h


def verify(path: Optional[str] = None) -> dict:
    """Replay the chain. Returns {"ok": bool, "rows": n, "first_bad_row": id_or_None, "reason": str}.
    `path` verifies another copy of the database (e.g. an auditor's copy)."""
    from gate import store
    if path:
        con = sqlite3.connect(path)
    else:
        con = store.connect()
    try:
        rows = con.execute("SELECT id, prev_hash, hash, event_type, body, at FROM ledger ORDER BY id").fetchall()
    finally:
        con.close()
    prev = GENESIS
    for n, (rid, prev_hash, h, event_type, body, at) in enumerate(rows, 1):
        reason = None
        if prev_hash != prev:
            reason = "prev_hash does not match the previous row's hash (a row was removed or reordered)"
        elif _hash(prev_hash, body) != h:
            reason = "body does not match its hash (the row was edited)"
        else:
            try:
                b = json.loads(body)
                if b.get("event_type") != event_type or b.get("at") != at:
                    reason = "event_type or timestamp column differs from the hashed body"
            except ValueError:
                reason = "body is not valid JSON"
        if reason:
            return {"ok": False, "rows": len(rows), "first_bad_row": rid, "checked": n - 1, "reason": reason}
        prev = h
    return {"ok": True, "rows": len(rows), "first_bad_row": None, "checked": len(rows), "reason": "",
            "head": prev}


def events(limit: int = 200, event_type: Optional[str] = None) -> list[dict]:
    """Latest ledger rows, newest first, with the payload decoded (for the UI)."""
    from gate import store
    con = store.connect()
    try:
        q = "SELECT id, prev_hash, hash, event_type, body, at FROM ledger"
        args: tuple = ()
        if event_type:
            q += " WHERE event_type=?"
            args = (event_type,)
        rows = con.execute(q + " ORDER BY id DESC LIMIT ?", args + (limit,)).fetchall()
    finally:
        con.close()
    return [{"id": r[0], "prev_hash": r[1], "hash": r[2], "event_type": r[3],
             "payload": json.loads(r[4]).get("payload"), "at": r[5]} for r in rows]
