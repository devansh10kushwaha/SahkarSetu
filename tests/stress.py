"""Stress-test SahkarSetu invariants under concurrency + adversarial inputs.
Hammers the live API from multiple threads, then walks DB state for violations.

    SAHKARSETU_BASE=http://localhost:3002 SAHKARSETU_DB=/path.db python3 tests/stress.py
"""
import json, os, random, sqlite3, sys, threading, time, urllib.request, urllib.error
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qa_common
BASE, DB = qa_common.resolve("stress")
SOON = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")

def call(method, path, body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token: req.add_header("Authorization", "Bearer " + token)
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}

# --- setup tokens ---
_, cust = call("POST", "/api/login", {"phone":"9000000001","password":"demo123"})
CT = cust["token"]
_, cat = call("GET", "/api/catalog")
svc_ids = [s["id"] for lst in cat["services_by_trade"].values() for s in lst]
zones = [z[0] if isinstance(z,(list,tuple)) else z for z in cat["zones"]]
print(f"setup ok: {len(svc_ids)} services, {len(zones)} zones")

violations = []
lock = threading.Lock()

def worker_thread(tid):
    local = []
    for i in range(12):
        sid = random.choice(svc_ids)
        zone = random.choice(zones)
        emg = random.random() < 0.3
        s, r = call("POST", "/api/bookings", {
            "service_id": sid, "scheduled_for": SOON,
            "address": f"STRESS-{tid}-{i}", "zone": zone, "is_emergency": emg}, token=CT)
        if s != 200:
            if "free nahi" not in str(r): local.append(("create-fail", s, r))
            continue
        bid = r.get("booking_id")
        # half get cancelled immediately (race with nothing), half left live
        if bid and random.random() < 0.5:
            s2, _ = call("POST", f"/api/bookings/{bid}/cancel", token=CT)
            if s2 != 200: local.append(("cancel-fail", s2, bid))
        elif bid:
            # try illegal transition jump: requested -> in_progress directly
            s3, r3 = call("POST", f"/api/w/jobs/{bid}/status",
                          {"status":"in_progress"}, token=cust.get("token"))
            # customer shouldn't be able to move worker jobs at all
            if s3 == 200: local.append(("PRIV-ESCALATION", "customer moved job status", bid))
    with lock:
        violations.extend(local)

threads = [threading.Thread(target=worker_thread, args=(t,)) for t in range(8)]
t0 = time.time()
for t in threads: t.start()
for t in threads: t.join()
print(f"stress phase done in {time.time()-t0:.1f}s")

# --- adversarial probes ---
print("\n== adversarial probes ==")
s, r = call("POST", "/api/login", {"phone":"9000000001","password":"wrong"})
print(f"wrong-password login -> {s} (expect 401)")
brute_target = "917" + str(random.randrange(1000000, 9999999))  # throwaway acct, keep demo users clean
call("POST", "/api/register-customer", {"name":"Brute Bait","phone":brute_target,"password":"test123"})
brute = [call("POST", "/api/login", {"phone":brute_target,"password":f"guess{i}"})[0] for i in range(25)]
blocked = any(x == 429 for x in brute)
print(f"25 bad logins -> any 429 rate-limit: {blocked} (finding if False)")
s, r = call("GET", "/api/workers/999999")
print(f"nonexistent worker -> {s} (expect 404)")
s, r = call("GET", "/api/bookings/999999/invoice.pdf", token=CT)
print(f"invoice of others'/missing booking -> {s}")
# IDOR: new customer tries to see someone else's invoice
_, nu = call("POST", "/api/register-customer", {"name":"Stress Tester","phone":"918"+str(random.randrange(1000000,9999999)),"password":"test123"})
NT = nu.get("token")
if NT:
    conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row
    other_paid = conn.execute("SELECT b.id FROM bookings b WHERE b.payment_status='paid' AND b.customer_id != (SELECT id FROM users WHERE phone='918'||'') LIMIT 1").fetchone()
    conn.close()
    if other_paid:
        s, _ = call("GET", f"/api/bookings/{other_paid['id']}/invoice.pdf", token=NT)
        print(f"IDOR invoice access by stranger -> {s} {'*** VULNERABILITY ***' if s==200 else '(blocked, good)'}")

# --- walk DB state for invariant violations ---
print("\n== DB invariant sweep ==")
conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row
checks = [
 ("bookings with >1 successful payment",
  """SELECT booking_id, COUNT(*) c FROM payments WHERE status='success' GROUP BY booking_id HAVING c>1"""),
 ("paid bookings not completed",
  """SELECT b.id, b.code, b.status FROM bookings b JOIN payments p ON p.booking_id=b.id
     WHERE p.status='success' AND b.payment_status='paid' AND b.status NOT IN ('completed')"""),
 ("worker with 2+ simultaneous non-terminal jobs",
  """SELECT worker_id, COUNT(*) c FROM bookings WHERE worker_id IS NOT NULL AND
     status IN ('accepted','enroute','in_progress') GROUP BY worker_id HAVING c>1"""),
 ("commission math wrong (net+comm != amount)",
  """SELECT id FROM payments WHERE status='success' AND (net + commission != amount)"""),
 ("review on non-completed booking",
  """SELECT r.id FROM reviews r JOIN bookings b ON b.id=r.booking_id WHERE b.status!='completed'"""),
 ("duplicate review per booking",
  """SELECT booking_id, COUNT(*) c FROM reviews GROUP BY booking_id HAVING c>1"""),
 ("cancelled bookings that still got paid",
  """SELECT b.id FROM bookings b JOIN payments p ON p.booking_id=b.id
     WHERE b.status='cancelled' AND p.status='success'"""),
]
for name, sql in checks:
    rows = conn.execute(sql).fetchall()
    mark = "✗ VIOLATION" if rows else "✓ clean"
    print(f"  {mark}: {name}" + (f" ({len(rows)} rows)" if rows else ""))

# stress bookings still live? clean them up so demo data stays tidy
n = conn.execute("""DELETE FROM payments WHERE booking_id IN
   (SELECT id FROM bookings WHERE address LIKE 'STRESS-%' AND status != 'completed')""").rowcount
n2 = conn.execute("""DELETE FROM reviews WHERE booking_id IN
   (SELECT id FROM bookings WHERE address LIKE 'STRESS-%' AND status != 'completed')""").rowcount
n3 = conn.execute("""DELETE FROM bookings WHERE address LIKE 'STRESS-%' AND status != 'completed'""").rowcount
conn.commit()
# also remove the Stress Tester user accounts themselves
try:
    conn.execute("DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE name IN ('Stress Tester','Brute Bait'))")
    conn.execute("""DELETE FROM payments WHERE booking_id IN (SELECT id FROM bookings WHERE
        customer_id IN (SELECT id FROM users WHERE name IN ('Stress Tester','Brute Bait')))""")
    conn.execute("""DELETE FROM reviews WHERE booking_id IN (SELECT id FROM bookings WHERE
        customer_id IN (SELECT id FROM users WHERE name IN ('Stress Tester','Brute Bait')))""")
    conn.execute("""DELETE FROM bookings WHERE
        customer_id IN (SELECT id FROM users WHERE name IN ('Stress Tester','Brute Bait'))""")
    conn.execute("DELETE FROM users WHERE name IN ('Stress Tester','Brute Bait')")
    conn.commit()
except Exception as e:
    print("stress user cleanup warn:", e)
leftover = conn.execute("SELECT COUNT(*) FROM bookings WHERE address LIKE 'STRESS-%' AND status IN ('requested','accepted','enroute','in_progress')").fetchone()[0]
conn.close()
print(f"\ncleaned stress actives: {n3} (payments {n}, reviews {n2}) | leftover live: {leftover}")

real_violations = [v for v in violations if v[0] != "create-fail"]
print(f"\nSTRESS RESULT: api-anomalies={len(real_violations)} {real_violations[:5]}")
sys.exit(1 if real_violations else 0)
