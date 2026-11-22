"""Cached Crustdata caller: cache keyed by sha256(path+canonical body); logs X-Credits-Used. Never prints key."""
import hashlib, json, sys, time, sqlite3, os, urllib.request, urllib.error
from pathlib import Path
ENV = Path(__file__).resolve().parent.parent / ".env"
KEY = next(l.split("=",1)[1].strip() for l in ENV.read_text().splitlines() if l.startswith("CRUSTDATA_API_KEY="))
DB = Path(__file__).with_name("cd_cache.sqlite")
CEILING = 30.0
con = sqlite3.connect(DB)
con.execute("create table if not exists cache(k text primary key, path text, body text, resp text, credits real, ts real)")
def spent(): return con.execute("select coalesce(sum(credits),0) from cache").fetchone()[0]
def call(path, body):
    canon = json.dumps(body, sort_keys=True, separators=(",",":"))
    k = hashlib.sha256((path+"\n"+canon).encode()).hexdigest()
    row = con.execute("select resp from cache where k=?", (k,)).fetchone()
    if row: return json.loads(row[0]), 0.0, True
    if spent() >= CEILING: raise RuntimeError("credit ceiling reached")
    req = urllib.request.Request("https://api.crustdata.com"+path, method="POST", data=canon.encode(),
        headers={"Authorization": f"Bearer {KEY}", "x-api-version": "2025-11-01", "Content-Type":"application/json","Accept":"application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        cr = float(r.headers.get("X-Credits-Used") or 0); data = r.read().decode()
    con.execute("insert into cache values(?,?,?,?,?,?)", (k,path,canon,data,cr,time.time())); con.commit()
    return json.loads(data), cr, False
if __name__ == "__main__":
    path, body, out = "/"+sys.argv[1].lstrip("/"), json.loads(sys.argv[2]), sys.argv[3]
    d, cr, hit = call(path, body)
    Path(out).write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"credits_used={cr} cache_hit={hit} total_spent={spent()}")
