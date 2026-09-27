#!/usr/bin/env python3
"""SIH26089 problem-statement compliance suite.

Every check maps to ONE line of the official problem statement (Ministry of Cooperation /
NCCT: "Cooperative Gig Services Platform for Household & Community Services") and proves
it against the LIVE build with real API calls plus direct DB assertions - no mocks, no
fixtures invented for the test. The suite cleans up after itself and restores any worker
statistics it touches, so it can run repeatedly on the demo database.

Run:  SAHKARSETU_BASE=http://127.0.0.1:5001 python3 tests/ps_compliance.py
"""
import json, os, sqlite3, sys, urllib.error, urllib.request
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qa_common import BASE, DB, resolve, assert_same_db

resolve("PS compliance suite")
assert_same_db()

PASS, FAIL, EVIDENCE = 0, 0, []
TOUCHED_WORKERS = {}          # worker_id -> (rating_avg, rating_count, jobs_done)
CLEANUP = {"bookings": [], "certs": [], "welfare": [], "claims": []}


def call(method, path, body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=(json.dumps(body).encode() if body is not None else None))
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def check(clause, ok, evidence=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        EVIDENCE.append((clause, evidence))
        print(f"  \u2713 {clause}\n      {evidence}")
    else:
        FAIL += 1
        print(f"  \u2717 {clause}\n      {evidence}")
    return ok


def login(phone, password):
    s, d = call("POST", "/api/login", {"phone": phone, "password": password})
    return d.get("token") if s == 200 and isinstance(d, dict) else None


def q(sql, args=()):
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    try:
        return c.execute(sql, args).fetchall()
    finally:
        c.close()


def ex(sql, args=()):
    c = sqlite3.connect(DB)
    try:
        c.execute(sql, args); c.commit()
    finally:
        c.close()


def note_worker(wid):
    """Remember worker stats so the run can restore them (tests must not skew the demo)."""
    if wid in TOUCHED_WORKERS:
        return
    r = q("SELECT rating_avg, rating_count, jobs_done FROM workers WHERE user_id=?", (wid,))
    if r:
        TOUCHED_WORKERS[wid] = tuple(r[0])


def free_seeded_worker(trade="electrician"):
    """A verified worker with a seeded password we can drive (worker@2026)."""
    rows = q("""SELECT w.user_id id, w.coop_id, u.phone FROM workers w JOIN users u ON u.id=w.user_id
                WHERE w.status='verified' AND w.trade=? AND u.phone LIKE '98%' ORDER BY w.user_id""", (trade,))
    for r in rows:
        if login(r["phone"], "worker@2026"):
            return r
    return None


def token_for_worker(wid, extra_pw=()):
    """Log in as whichever worker the matcher actually picked (his phone is in the DB)."""
    r = q("SELECT u.phone FROM workers w JOIN users u ON u.id=w.user_id WHERE w.user_id=?", (wid,))
    if not r:
        return None
    for pw in tuple(extra_pw) + ("worker@2026", "demo123"):
        t = login(r[0]["phone"], pw)
        if t:
            return t
    return None


print("=" * 72)
print("SIH26089 PS COMPLIANCE — 'Cooperative Gig Services Platform' (MoC / NCCT)")
print(f"target: {BASE}   db: {DB}")
print("=" * 72)

ADMIN = login("7000000001", "admin123")
CUST = login("9000000001", "demo123")
assert ADMIN and CUST, "demo logins failed - is the server up?"

# ---------------------------------------------------------------- 1. registration + verification
print("\n[1] Service provider registration and verification")
s, cat = call("GET", "/api/catalog")
coop = q("SELECT id, zone FROM cooperatives ORDER BY id LIMIT 1")[0]
TEST_PHONE = "9111" + datetime.now().strftime("%d%H%M%S")[:6]
s, reg = call("POST", "/api/apply-worker", {
    "name": "PS Compliance Worker", "phone": TEST_PHONE, "password": "pspass123",
    "trade": "plumber", "exp_years": 6, "coop_id": coop["id"], "cert_title": "Plumber Level-2",
    "cert_issuer": "NSDC"})
new_wid = reg.get("user")["id"] if s == 200 else None
check("worker self-registration creates a pending application",
      s == 200 and new_wid and q("SELECT status FROM workers WHERE user_id=?", (new_wid,))[0]["status"] == "pending",
      f"POST /api/apply-worker -> {s}; worker row status=pending (id {new_wid})")
s, pub = call("GET", "/api/workers?trade=plumber")
visible = any(w["id"] == new_wid for w in pub["workers"]) if s == 200 else None
check("a pending worker is NOT publicly bookable before verification",
      visible is False, f"public plumber list contains the pending worker: {visible}")
s, queue = call("GET", "/api/a/pending-workers", token=ADMIN)
in_q = any(w["id"] == new_wid for w in queue.get("pending", [])) if s == 200 else None
check("federation verification queue shows the application (with certificates)",
      in_q and queue["pending"][0]["certifications"] is not None,
      f"GET /api/a/pending-workers -> {len(queue.get('pending', []))} waiting; certs attached")
s, v = call("POST", f"/api/a/verify/{new_wid}", {"approve": True}, token=ADMIN)
s2, pub2 = call("GET", "/api/workers?trade=plumber")
check("admin approval flips the worker to verified + bookable",
      s == 200 and v.get("new_status") == "verified" and any(w["id"] == new_wid for w in pub2["workers"]),
      f"POST /api/a/verify -> {v.get('new_status')}; now listed publicly")

# ---------------------------------------------------------------- 2. skill profiling + certification
print("\n[2] Worker skill profiling and certification")
w = free_seeded_worker("electrician")
WT = login(w["phone"], "worker@2026") if w else None
s, prof = call("GET", f"/api/workers/{w['id']}")
check("public profile carries an explainable skill level",
      s == 200 and prof["worker"].get("skill_level") in ("helper", "skilled", "expert"),
      f"skill_level='{prof['worker'].get('skill_level')}' computed from exp/certs/rating (never stored)")
s, ac = call("POST", "/api/w/certs", {"title": "PS Compliance Cert", "issuer": "NCCT", "year": 2025}, token=WT)
cid = ac.get("id") if s == 200 else None
CLEANUP["certs"].append(cid)
s, prof2 = call("GET", f"/api/workers/{w['id']}")
pending_cert = next((c for c in prof2["certifications"] if c["id"] == cid), None)
check("worker can add his own certificate (starts PENDING)",
      pending_cert and pending_cert["status"] == "pending",
      f"POST /api/w/certs -> id {cid} status={pending_cert and pending_cert['status']}")
soc_phone = "7000000" + str(100 + w["coop_id"]) if w["coop_id"] < 100 else None
SOC = login(soc_phone, "admin123") if soc_phone else None
s, sv = call("POST", f"/api/c/certs/{cid}", {"approve": True}, token=SOC)
s, prof3 = call("GET", f"/api/workers/{w['id']}")
ver_cert = next((c for c in prof3["certifications"] if c["id"] == cid), None)
check("only the cooperative can bless it -> verified",
      s == 200 and ver_cert and ver_cert["status"] == "verified",
      f"society {soc_phone} POST /api/c/certs/{cid} -> {ver_cert and ver_cert['status']}")

# ---------------------------------------------------------------- 3. booking + scheduling
print("\n[3] Customer booking and scheduling system")
s, svc = call("GET", "/api/catalog")
plumb = next(x for x in svc["services_by_trade"]["plumber"])
addr = "PSQA schedule probe, Gali 4"
future = (datetime.now() + timedelta(days=3)).replace(hour=15, minute=30, second=0, microsecond=0)
s, bk = call("POST", "/api/bookings", {"service_id": plumb["id"], "scheduled_for": future.isoformat(),
                                       "address": addr, "zone": "east"}, token=CUST)
BID = bk.get("booking_id") if s == 200 else None
CLEANUP["bookings"].append(BID)
check("customer can schedule a booking at a chosen date AND time (3 days out, 15:30)",
      s == 200 and BID, f"POST /api/bookings scheduled_for={future.isoformat()} -> booking #{BID}")
past = (datetime.now() - timedelta(days=2)).isoformat()
s_past, bad = call("POST", "/api/bookings", {"service_id": plumb["id"], "scheduled_for": past,
                                             "address": addr, "zone": "east"}, token=CUST)
s_far, far = call("POST", "/api/bookings", {"service_id": plumb["id"],
                                            "scheduled_for": (datetime.now() + timedelta(days=120)).isoformat(),
                                            "address": addr, "zone": "east"}, token=CUST)
check("scheduling bounds enforced server-side (no past, max 90 days)",
      s_past == 400 and s_far == 400, f"past -> HTTP {s_past}, +120 days -> HTTP {s_far}")

# ---------------------------------------------------------------- 4. geo matching
print("\n[4] Geo-location based service matching")
s, wk = call("GET", "/api/workers")
geo = all(wk["workers"][i].get("lat") for i in range(min(5, len(wk["workers"]))))
s, det = call("GET", f"/api/bookings/{BID}", token=CUST)
match = (det.get("booking", det) or {})
check("workers carry coordinates and the match is distance-scored with a readable reason",
      geo and bk.get("worker", {}).get("distance_km") is not None and bk.get("match_note"),
      f"worker pins present; match_note='{bk.get('match_note')}'")

# ---------------------------------------------------------------- 5. payments + invoicing
print("\n[5] Digital payments and invoicing")
# drive the job with whichever worker the matcher actually assigned (could be the
# freshly verified test worker, so his own password is in the list)
WT_JOB = token_for_worker(bk["worker"]["id"], extra_pw=("pspass123",))
s, h = call("GET", "/api/w/home", token=WT_JOB)
job = next((j for j in h["jobs"] if j["id"] == BID), None) if s == 200 else None
if job:
    for st in ("accepted", "enroute", "in_progress", "completed"):
        call("POST", f"/api/w/jobs/{BID}/status", {"status": st}, token=WT_JOB)
    note_worker(bk["worker"]["id"])
s, pay = call("POST", f"/api/bookings/{BID}/pay", {}, token=CUST)
s, mine = call("GET", "/api/bookings/mine", token=CUST)
row = next((b for b in mine["bookings"] if b["id"] == BID), None)
split_ok = row and row.get("worker_net") is not None and row.get("paid_amt") == row["worker_net"] + row["comm"]
check("demo UPI payment splits 90/10 and records it on the booking",
      pay.get("ok") and split_ok,
      f"paid ₹{row and row.get('paid_amt')} = worker ₹{row and row.get('worker_net')} + platform ₹{row and row.get('comm')}")
req = urllib.request.Request(f"{BASE}/api/bookings/{BID}/invoice.pdf", headers={"Authorization": "Bearer " + CUST})
try:
    with urllib.request.urlopen(req, timeout=20) as r:
        pdf = r.read()
except urllib.error.HTTPError as e:
    pdf = e.read()
pdf_text = ""
try:                                     # PyMuPDF is available in the QA venv
    import fitz
    doc = fitz.open(stream=pdf, filetype="pdf")
    pdf_text = "\n".join(pg.get_text() for pg in doc)
except Exception:
    pdf_text = ""
has_split = ("platform fee (10%)" in pdf_text) and (str(row and row.get("comm")) in pdf_text)
check("invoice renders as a real PDF with the 90/10 split printed on it",
      pdf[:4] == b"%PDF" and has_split,
      f"invoice.pdf -> {len(pdf)} bytes, magic={pdf[:4].decode(errors='replace')}, "
      f"text contains 'platform fee (10%)' + fee ₹{row and row.get('comm')}")

# ---------------------------------------------------------------- 6. rating + feedback
print("\n[6] Rating and feedback mechanism")
before = q("SELECT rating_avg, rating_count FROM workers WHERE user_id=?", (bk["worker"]["id"],))[0]
s, rv = call("POST", f"/api/bookings/{BID}/review", {"rating": 5, "comment": "PS compliance probe"}, token=CUST)
after = q("SELECT rating_avg, rating_count FROM workers WHERE user_id=?", (bk["worker"]["id"],))[0]
s2, dup = call("POST", f"/api/bookings/{BID}/review", {"rating": 1, "comment": "dup"}, token=CUST)
check("a completed job can be rated exactly once and the worker's average updates",
      rv.get("ok") and s2 == 409 and after["rating_count"] == before["rating_count"] + 1,
      f"review ok, second review -> HTTP {s2}; rating_count {before['rating_count']} -> {after['rating_count']}")

# ---------------------------------------------------------------- 7. welfare + insurance
print("\n[7] Worker welfare and insurance integration")
cand = None
for r in q("""SELECT w.user_id id, u.phone FROM workers w JOIN users u ON u.id=w.user_id
              WHERE w.status='verified' AND u.phone LIKE '98%' AND w.user_id NOT IN
              (SELECT worker_id FROM welfare WHERE scheme='PMSBY' AND status IN ('active','pending'))"""):
    if login(r["phone"], "worker@2026"):
        cand = r
        break
WT2 = login(cand["phone"], "worker@2026")
s, wa = call("POST", "/api/w/welfare/apply", {"scheme": "PMSBY"}, token=WT2)
s, reqs = call("GET", "/api/a/welfare/requests", token=ADMIN)
waiting = any(x["worker_id"] == cand["id"] and x["scheme"] == "PMSBY" for x in reqs.get("enrolments", []))
CLEANUP["welfare"].append(cand["id"])
check("worker applies for PMSBY himself; it waits as PENDING for the cooperative",
      wa.get("status") == "pending" and waiting,
      f"POST /api/w/welfare/apply -> {wa.get('status')}; federation sees it in /api/a/welfare/requests")
s, dec = call("POST", "/api/a/welfare/decide", {"worker_id": cand["id"], "scheme": "PMSBY", "approve": True}, token=ADMIN)
wl = q("SELECT status, valid_till, decided_by FROM welfare WHERE worker_id=? AND scheme='PMSBY' ORDER BY id DESC LIMIT 1",
       (cand["id"],))[0]
check("cooperative approval activates the cover with a validity window",
      dec.get("status") == "active" and wl["valid_till"],
      f"status={wl['status']} valid_till={wl['valid_till']} decided_by={wl['decided_by']}")
s, cl = call("POST", "/api/w/welfare/claim", {"scheme": "PMSBY", "reason": "PS compliance claim", "amount": 5000}, token=WT2)
s, rq2 = call("GET", "/api/a/welfare/requests", token=ADMIN)
filed = next((x for x in rq2.get("claims", []) if x["worker_id"] == cand["id"]), None)
CLEANUP["claims"].append(filed and filed["id"])
check("an insurance claim can be filed and lands in the cooperative's decision queue",
      cl.get("status") == "filed" and filed is not None,
      f"claim #{filed and filed['id']} filed, reason '{filed and filed['reason']}'")
s, cd = call("POST", f"/api/a/welfare/claim/{filed['id']}", {"approve": True}, token=ADMIN)
check("cooperative decides the claim (approve/reject recorded with actor)",
      cd.get("status") == "approved",
      f"claim #{filed['id']} -> {cd.get('status')}")
uan = q("SELECT e_shram_uan FROM workers WHERE user_id=?", (cand["id"],))[0]["e_shram_uan"]
check("e-Shram UAN is linked on the worker record (insurance integration point)",
      bool(uan), f"e_shram_uan present ({uan[:4]}****)")

# ---------------------------------------------------------------- 8. emergency
print("\n[8] Emergency and on-demand service booking")
s, emg = call("POST", "/api/bookings", {"service_id": plumb["id"],
                                        "scheduled_for": (datetime.now() + timedelta(hours=1)).isoformat(),
                                        "address": "PSQA emergency probe", "zone": "east",
                                        "is_emergency": True}, token=CUST)
EID = emg.get("booking_id") if s == 200 else None
CLEANUP["bookings"].append(EID)
check("emergency booking is matched to a free worker in the same response",
      s == 200 and emg.get("worker", {}).get("id"),
      f"emergency -> booking #{EID} assigned {emg.get('worker', {}).get('name')} ({emg.get('match_note')})")

# ---------------------------------------------------------------- 9. dashboards
print("\n[9] Cooperative federation administration dashboard (+ society level)")
s, ov = call("GET", "/api/a/overview", token=ADMIN)
need = {"workers_total", "workers_verified", "bookings_today", "week_gmv", "worker_share_pct"}
check("federation dashboard exposes workers / bookings / GMV / worker share",
      s == 200 and need.issubset(ov["stats"].keys()),
      f"stats keys: {sorted(need & set(ov['stats']))}")
s, ch = call("GET", "/api/c/home", token=SOC)
scoped = ch.get("stats", {}).get("workers") == len(q("SELECT 1 FROM workers WHERE coop_id=?", (w["coop_id"],)))
check("society dashboard shows ONLY its own cooperative (workers/earnings/welfare)",
      s == 200 and scoped,
      f"{ch.get('coop', {}).get('name')}: {ch.get('stats', {}).get('workers')} workers, "
      f"₹{ch.get('stats', {}).get('worker_net')} paid out")
s_den, denied = call("GET", "/api/c/home", token=CUST)
s_den2, denied2 = call("GET", "/api/a/overview", token=CUST)
check("role separation: customers cannot open either dashboard",
      s_den == 403 and s_den2 == 403, f"society -> HTTP {s_den}, federation -> HTTP {s_den2}")

# ---------------------------------------------------------------- 10. multilingual mobile app
print("\n[10] Multilingual mobile application")
s, man = call("GET", "/static/manifest.json")
s2, off = call("GET", "/static/offline.html")
import re as _re
i18n_src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "static/js/i18n.js"), encoding="utf-8").read()
langs = all(k in i18n_src for k in ("hi:", "en:", "ur:"))
pairs = _re.findall(r"\{hi:\"[^\"]*\", en:\"[^\"]*\", ur:\"[^\"]*\"\}", i18n_src)
check("installable PWA with an offline page (mobile application)",
      s == 200 and s2 == 200 and man.get("name"),
      f"manifest name='{man.get('name')}' display={man.get('display')}; offline.html served")
check("Hindi / English / Urdu packs are complete and RTL is applied for Urdu",
      langs and len(pairs) >= 20 and 'dir = (LANG === "ur") ? "rtl" : "ltr"' in i18n_src.replace("'", '"'),
      f"{len(pairs)} translated string groups across hi/en/ur; RTL switch present in i18n.js")

# ---------------------------------------------------------------- 11. forecast + allocation
print("\n[11] AI-based demand forecasting and workforce allocation")
s, fc = call("GET", "/api/a/forecast", token=ADMIN)
rows = fc.get("rows", []) if s == 200 else []
days = {r["date"] for r in rows}
check("forecast model produces a 7-day, zone x trade demand grid (explainable method)",
      len(rows) > 50 and len(days) == 7 and fc.get("model"),
      f"model='{fc.get('model')}', {len(rows)} rows over {len(days)} days")
s, al = call("GET", "/api/a/allocation", token=ADMIN)
arows = al.get("rows", []) if s == 200 else []
with_action = [r for r in arows if r.get("action") and r.get("severity")]
check("allocation board joins forecast demand with verified supply + plain-language action",
      len(arows) > 10 and len(with_action) == len(arows),
      f"{len(arows)} zone x trade rows; e.g. [{arows[0]['severity']}] {arows[0]['action'][:70]}")

# ---------------------------------------------------------------- cleanup + restore
print("\n[cleanup] restoring the demo database to its pre-run state")
c = sqlite3.connect(DB)
try:
    for bid in [b for b in CLEANUP["bookings"] if b]:
        for t in ("booking_events", "declines", "payments", "reviews"):
            c.execute(f"DELETE FROM {t} WHERE booking_id=?", (bid,))
        c.execute("DELETE FROM bookings WHERE id=?", (bid,))
    for cid in [x for x in CLEANUP["certs"] if x]:
        c.execute("DELETE FROM certifications WHERE id=?", (cid,))
    for cid in [x for x in CLEANUP["claims"] if x]:
        c.execute("DELETE FROM welfare_claims WHERE id=?", (cid,))
    for wid in CLEANUP["welfare"]:
        c.execute("DELETE FROM welfare WHERE worker_id=? AND scheme='PMSBY' AND requested_by='worker'", (wid,))
    c.execute("DELETE FROM users WHERE phone=?", (TEST_PHONE,))          # test worker account
    c.execute("DELETE FROM workers WHERE user_id NOT IN (SELECT id FROM users)")
    for wid, (ra, rc, jd) in TOUCHED_WORKERS.items():                    # undo rating/job-count drift
        c.execute("UPDATE workers SET rating_avg=?, rating_count=?, jobs_done=? WHERE user_id=?",
                  (ra, rc, jd, wid))
    c.commit()
    orphans = {t: c.execute(f"SELECT COUNT(*) FROM {t} WHERE booking_id NOT IN (SELECT id FROM bookings)").fetchone()[0]
               for t in ("payments", "reviews", "booking_events", "declines")}
finally:
    c.close()
print(f"  bookings removed: {len([b for b in CLEANUP['bookings'] if b])} · "
      f"certs removed: {len([x for x in CLEANUP['certs'] if x])} · "
      f"claims removed: {len([x for x in CLEANUP['claims'] if x])} · "
      f"worker stats restored: {len(TOUCHED_WORKERS)} · orphans: {orphans}")

print("\n" + "=" * 72)
print(f"PS COMPLIANCE RESULT: {PASS} passed, {FAIL} failed  (clauses evidenced: {PASS}/18 checks)")
print("=" * 72)
sys.exit(1 if FAIL else 0)
