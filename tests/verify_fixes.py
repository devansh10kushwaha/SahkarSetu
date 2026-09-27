"""Post-fix verification: invoice render proof + latency comparison vs baseline numbers."""
import json, os, sqlite3, time, urllib.request, urllib.error
from datetime import datetime, timedelta

# Reproduces the September audit's fix evidence (invoice render + latency table).
# Point it at any instance: SAHKARSETU_BASE=http://127.0.0.1:3002 SAHKARSETU_DB=/path.db
BASE = os.environ.get("SAHKARSETU_BASE", "http://127.0.0.1:3002")
DB = os.environ.get("SAHKARSETU_DB", "/tmp/audit_run/sahkarsetu.db")

def call(method, path, body=None, token=None, raw=False, timeout=30):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token: req.add_header("Authorization", "Bearer " + token)
    data = json.dumps(body).encode() if body is not None else None
    try:
        r = urllib.request.urlopen(req, data=data, timeout=timeout)
        c = r.read()
        return (r.status, c, dict(r.headers)) if raw else (r.status, json.loads(c) if c else {})
    except urllib.error.HTTPError as e:
        c = e.read()
        return (e.code, c, dict(e.headers)) if raw else (e.code, json.loads(c) if c else {})

# ---- pick a free verified worker, log in as them via the seeded password ----
conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row
row = conn.execute("""SELECT w.user_id, u.phone, w.trade, w.zone, u.name FROM workers w
   JOIN users u ON u.id=w.user_id
   WHERE w.status='verified' AND NOT EXISTS (SELECT 1 FROM bookings b WHERE b.worker_id=w.user_id
        AND b.status IN ('requested','accepted','enroute','in_progress'))
   ORDER BY RANDOM() LIMIT 1""").fetchone()
pw = "demo123" if row["user_id"] == 2 else "worker@2026"
trade, zone, wid, wphone = row["trade"], row["zone"], row["user_id"], row["phone"]
conn.close()
s, wl = call("POST", "/api/login", {"phone": wphone, "password": pw})
WT = wl["token"]
s, cl = call("POST", "/api/login", {"phone": "9000000001", "password": "demo123"})
CT = cl["token"]
print(f"worker #{wid} ({wl['user']['name']}, {trade} in {zone}) login: {s}")

s, cat = call("GET", "/api/catalog")
svc = [x for x in cat["services_by_trade"][trade] if x["slug"]][0]
when = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT10:00:00")
s, bk = call("POST", "/api/bookings", {"service_id": svc["id"], "scheduled_for": when,
                                       "address": "Invoice proof gali 5", "worker_id": wid, "zone": zone}, token=CT)
print("booking:", s, bk.get("code"), "| match_note:", bk.get("match_note"))
bid = bk["booking_id"]
for st in ["accepted", "enroute", "in_progress", "completed"]:
    call("POST", f"/api/w/jobs/{bid}/status", {"status": st}, token=WT)
s, pay = call("POST", f"/api/bookings/{bid}/pay", token=CT)
print("payment:", s, "| amount", pay.get("amount"), "commission", pay.get("commission"), "worker_gets", pay.get("worker_gets"))
s, pdf, hdrs = call("GET", f"/api/bookings/{bid}/invoice.pdf", token=CT, raw=True)
open("/tmp/invoice_fixed.pdf", "wb").write(pdf)
print("invoice:", s, len(pdf), "bytes | cache-control:", {k.lower(): v for k, v in hdrs.items()}.get("cache-control"))

import fitz
doc = fitz.open("/tmp/invoice_fixed.pdf")
page = doc[0]
txt = page.get_text()
blocks = page.get_text("blocks")
offpage = [b for b in blocks if b[3] < 0]
print("\n--- invoice text ---")
print(txt.strip())
print("--- off-page text blocks:", len(offpage), "(must be 0)")
pix = page.get_pixmap(dpi=110); pix.save("/tmp/invoice_fixed.png")
print("rendered -> /tmp/invoice_fixed.png")

# ---- latency comparison ----
print("\n--- latency (fixed build) vs baseline ---")
def bench(path, token=None, n=5):
    ts = []
    for _ in range(n):
        req = urllib.request.Request(BASE + path)
        if token: req.add_header("Authorization", "Bearer " + token)
        t0 = time.perf_counter(); r = urllib.request.urlopen(req, timeout=30); r.read()
        ts.append((time.perf_counter() - t0) * 1000)
    return min(ts), sum(ts) / len(ts)

_, adm = call("POST", "/api/login", {"phone": "7000000001", "password": "admin123"})
AT = adm["token"]
# login latency itself (PBKDF2 cost)
t0 = time.perf_counter(); call("POST", "/api/login", {"phone": "9000000001", "password": "demo123"}); login_ms = (time.perf_counter() - t0) * 1000
prev = {"/api/catalog": 4.9, "/api/workers": 6.8, "/api/a/overview": 15.3,
        "/api/a/forecast": 31.5, "/api/a/forecast/summary": 18.7, "/api/a/welfare": 4.6}
for p, tok in [("/api/catalog", None), ("/api/workers", None), ("/api/a/overview", AT),
               ("/api/a/forecast", AT), ("/api/a/forecast/summary", AT), ("/api/a/welfare", AT)]:
    lo, avg = bench(p, tok)
    print(f"  {p:26} avg {avg:6.1f} ms   (before: {prev[p]:5.1f} ms)")
print(f"  login (PBKDF2 210k rounds): {login_ms:.0f} ms end-to-end")
