import hashlib, json, re, uuid, unicodedata, urllib.request, urllib.error, datetime as dt, sqlite3
# --- idempotency key from invoice fingerprint ---
NS = uuid.UUID("6f1c2a4e-9b1d-4c33-8e0a-5a7d2b9c0f11")
def norm_inv(s):
    s = unicodedata.normalize("NFKC", s).upper()
    s = re.sub(r"[^A-Z0-9]", "", s)
    s = s.translate(str.maketrans("OIL", "011"))
    s = re.sub(r"^(INV|INVOICE|BILL|TAXINV|TI)", "", s)
    return re.sub(r"0+(\d)", r"\1", s)  # strip zero padding in numeric runs
def fy(d):  # Indian FY string
    return f"{d.year}-{d.year+1}" if d.month >= 4 else f"{d.year-1}-{d.year}"
def fingerprint(gstin, inv_no, inv_date, amount_paise):
    return f"{gstin.upper()}|{norm_inv(inv_no)}|{fy(inv_date)}|{amount_paise}"
def idem_key(fp, attempt=0):
    return str(uuid.uuid5(NS, f"{fp}|attempt{attempt}"))  # 36 chars: fits Razorpay 4-36
fp = fingerprint("27AAACR5055K1Z7", "INV/2026-27/0042", dt.date(2026,11,20), 1250000)
print(fp, idem_key(fp), len(idem_key(fp)))
print(norm_inv("INV-2026/27-00042"), norm_inv("inv 2026 27 42"), norm_inv("INV/2O26-27/0042"))
# --- lookalike domain ---
CONF = str.maketrans({"0":"o","1":"l","3":"e","5":"s","а":"a","е":"e","о":"o","р":"p","с":"c","і":"i","ԁ":"d"})
def skeleton(d):
    d = d.lower().strip(".")
    try: d = d.encode().decode("idna") if "xn--" in d else d
    except Exception: pass
    d = unicodedata.normalize("NFKC", d).translate(CONF)
    return d.replace("rn","m").replace("vv","w")
def lev(a,b):
    p=list(range(len(b)+1))
    for i,ca in enumerate(a,1):
        c=[i]
        for j,cb in enumerate(b,1): c.append(min(p[j]+1,c[j-1]+1,p[j-1]+(ca!=cb)))
        p=c
    return p[-1]
known="razorpay.com"
for cand in ["razorpay.com","rnzorpay.com","razorpaay.com","raz0rpay.com","xn--rzorpay-3ya.com","razorpay-payments.com"]:
    sk=skeleton(cand); print(cand, sk, "dist", lev(sk,known), "LOOKALIKE" if cand!=known and (sk==known or lev(sk,known)<=2) else "")
# --- RDAP age ---
BOOT={"com":"https://rdap.verisign.com/com/v1/","net":"https://rdap.verisign.com/net/v1/","in":"https://rdap.nixiregistry.in/rdap/"}
def domain_age_days(domain, timeout=8):
    tld=domain.rsplit(".",1)[-1]; base=BOOT.get(tld,"https://rdap.org/")
    try:
        with urllib.request.urlopen(urllib.request.Request(base+"domain/"+domain, headers={"Accept":"application/rdap+json"}), timeout=timeout) as r:
            j=json.load(r)
    except urllib.error.HTTPError as e:
        return ("NOT_REGISTERED", None) if e.code==404 else ("UNKNOWN", f"http {e.code}")
    except Exception as e:
        return ("UNKNOWN", repr(e)[:60])   # timeout => UNKNOWN, never 'ok'
    reg=[e["eventDate"] for e in j.get("events",[]) if e["eventAction"]=="registration"]  # top-level only
    if not reg: return ("UNKNOWN","no registration event")
    d=dt.datetime.fromisoformat(reg[0].replace("Z","+00:00"))
    return ("OK", (dt.datetime.now(dt.timezone.utc)-d).days)
for d in ["razorpay.com","razorpay.in","irctc.co.in","razorpaay.in"]: print(d, domain_age_days(d))
# --- hash chained ledger ---
con=sqlite3.connect(":memory:")
con.execute("create table ledger(seq integer primary key, ts text, kind text, body text, prev text, hash text)")
def canon(o): return json.dumps(o, sort_keys=True, separators=(",",":"), ensure_ascii=False)
def append(kind, body):
    row=con.execute("select seq,hash from ledger order by seq desc limit 1").fetchone()
    seq,prev=(row[0]+1,row[1]) if row else (1,"0"*64)
    ts=dt.datetime.now(dt.timezone.utc).isoformat()
    h=hashlib.sha256(canon({"seq":seq,"ts":ts,"kind":kind,"body":body,"prev":prev}).encode()).hexdigest()
    con.execute("insert into ledger values(?,?,?,?,?,?)",(seq,ts,kind,canon(body),prev,h)); con.commit(); return h
def verify():
    prev="0"*64
    for seq,ts,kind,body,p,h in con.execute("select * from ledger order by seq"):
        if p!=prev or hashlib.sha256(canon({"seq":seq,"ts":ts,"kind":kind,"body":json.loads(body),"prev":p}).encode()).hexdigest()!=h: return f"BROKEN at {seq}"
        prev=h
    return "OK"
append("decision",{"inv":fp,"verdict":"ESCALATE"}); append("approval",{"inv":fp,"by":"alice"})
print("verify", verify()); con.execute("update ledger set body=? where seq=1",(canon({"inv":fp,"verdict":"ALLOW"}),)); print("after tamper", verify())
