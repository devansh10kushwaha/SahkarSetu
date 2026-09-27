"""SahkarSetu end-to-end API test suite.

Run against any instance:
    SAHKARSETU_BASE=http://localhost:3002 SAHKARSETU_DB=/path/to.db python3 tests/e2e.py
Defaults match the standard deployment (localhost:3001, ./data/sahkarsetu.db).
"""
import json, os, random, sqlite3 as _sq, sys, urllib.request, urllib.error
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qa_common
BASE, DB = qa_common.resolve("e2e")

PASS, FAIL = [], []
qa_common.assert_same_db()          # refuse to run when the API and the DB file disagree

# bookings must be in the future now -> never hardcode a calendar date again
SOON = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
SOON2 = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S")
PAST = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")

def call(method, path, body=None, token=None, raw=False):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token: req.add_header("Authorization", "Bearer " + token)
    data = json.dumps(body).encode() if body is not None else None
    try:
        r = urllib.request.urlopen(req, data=data, timeout=20)
        content = r.read()
        if raw: return r.status, content, dict(r.headers)
        return r.status, json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        content = e.read()
        if raw: return e.code, content, dict(e.headers)
        try: return e.code, json.loads(content)
        except Exception: return e.code, {"detail": content.decode()[:200]}

def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name + (f" [{extra}]" if extra and not cond else ""))
    print(("  ✓ " if cond else "  ✗ ") + name + (" — " + str(extra) if not cond else ""))

print("== 0. Clean slate (purge leftover test data from prior runs) ==")

_PURGE = [
    # one pattern list for every suite-owned booking, applied to every child table -
    # a missing child here is how orphan payments appeared (booking deleted, payment left)
    """DELETE FROM payments WHERE booking_id IN (SELECT id FROM bookings WHERE
       (address LIKE '%Emergency Gali%' OR address LIKE '%Test Colony%' OR address LIKE '%Playwright%' OR address LIKE 'STRESS-%'
        OR address LIKE 'Decline probe%' OR address LIKE 'QA Payout Probe' OR address LIKE '%Busy probe%'
        OR address LIKE 'Past probe' OR address LIKE 'V-probe%' OR address LIKE 'QA schedule probe%'))
       OR booking_id NOT IN (SELECT id FROM bookings)""",
    """DELETE FROM reviews WHERE booking_id IN (SELECT id FROM bookings WHERE
       (address LIKE '%Emergency Gali%' OR address LIKE '%Test Colony%' OR address LIKE '%Playwright%' OR address LIKE 'STRESS-%'
        OR address LIKE 'Decline probe%' OR address LIKE 'QA Payout Probe' OR address LIKE '%Busy probe%'
        OR address LIKE 'Past probe' OR address LIKE 'V-probe%' OR address LIKE 'QA schedule probe%'))""",
    """DELETE FROM booking_events WHERE booking_id IN (SELECT id FROM bookings WHERE
       (address LIKE '%Emergency Gali%' OR address LIKE '%Test Colony%' OR address LIKE '%Playwright%' OR address LIKE 'STRESS-%'
        OR address LIKE 'Decline probe%' OR address LIKE 'QA Payout Probe' OR address LIKE '%Busy probe%'
        OR address LIKE 'Past probe' OR address LIKE 'V-probe%' OR address LIKE 'QA schedule probe%'))
       OR booking_id NOT IN (SELECT id FROM bookings)""",
    """DELETE FROM declines WHERE booking_id IN (SELECT id FROM bookings WHERE
       (address LIKE '%Emergency Gali%' OR address LIKE '%Test Colony%' OR address LIKE '%Playwright%' OR address LIKE 'STRESS-%'
        OR address LIKE 'Decline probe%' OR address LIKE 'QA Payout Probe' OR address LIKE '%Busy probe%'
        OR address LIKE 'Past probe' OR address LIKE 'V-probe%' OR address LIKE 'QA schedule probe%'))""",
    """DELETE FROM bookings WHERE
       (address LIKE '%Emergency Gali%' OR address LIKE '%Test Colony%' OR address LIKE '%Playwright%' OR address LIKE 'STRESS-%'
        OR address LIKE 'Decline probe%' OR address LIKE 'QA Payout Probe' OR address LIKE '%Busy probe%'
        OR address LIKE 'Past probe' OR address LIKE 'V-probe%' OR address LIKE 'QA schedule probe%')""",
    # purge test USERS entirely (customers + QA worker applicants) so the live
    # directory never shows fake entries, even if a previous run crashed mid-test
    """DELETE FROM sessions WHERE user_id IN (
         SELECT id FROM users WHERE name IN ('QA Tester','Stress Tester','QA Applicant'))""",
    """DELETE FROM welfare WHERE worker_id IN (
         SELECT w.user_id FROM workers w JOIN users u ON u.id=w.user_id WHERE u.name='QA Applicant')""",
    """DELETE FROM certifications WHERE worker_id IN (
         SELECT w.user_id FROM workers w JOIN users u ON u.id=w.user_id WHERE u.name='QA Applicant')""",
    """DELETE FROM payments WHERE booking_id IN (SELECT id FROM bookings WHERE
         worker_id IN (SELECT w.user_id FROM workers w JOIN users u ON u.id=w.user_id WHERE u.name='QA Applicant')
         OR customer_id IN (SELECT id FROM users WHERE name IN ('QA Tester','Stress Tester')))""",
    """DELETE FROM reviews WHERE booking_id IN (SELECT id FROM bookings WHERE
         worker_id IN (SELECT w.user_id FROM workers w JOIN users u ON u.id=w.user_id WHERE u.name='QA Applicant')
         OR customer_id IN (SELECT id FROM users WHERE name IN ('QA Tester','Stress Tester')))""",
    """DELETE FROM booking_events WHERE booking_id IN (SELECT id FROM bookings WHERE
         worker_id IN (SELECT w.user_id FROM workers w JOIN users u ON u.id=w.user_id WHERE u.name='QA Applicant')
         OR customer_id IN (SELECT id FROM users WHERE name IN ('QA Tester','Stress Tester')))""",
    """DELETE FROM declines WHERE booking_id IN (SELECT id FROM bookings WHERE
         worker_id IN (SELECT w.user_id FROM workers w JOIN users u ON u.id=w.user_id WHERE u.name='QA Applicant')
         OR customer_id IN (SELECT id FROM users WHERE name IN ('QA Tester','Stress Tester')))""",
    """DELETE FROM bookings WHERE
         worker_id IN (SELECT w.user_id FROM workers w JOIN users u ON u.id=w.user_id WHERE u.name='QA Applicant')
         OR customer_id IN (SELECT id FROM users WHERE name IN ('QA Tester','Stress Tester'))""",
    """DELETE FROM workers WHERE user_id IN (
         SELECT w.user_id FROM workers w JOIN users u ON u.id=w.user_id WHERE u.name='QA Applicant')""",
    """DELETE FROM users WHERE name IN ('QA Tester','Stress Tester','QA Applicant')""",
]

def _purge_test_data():
    _c = _sq.connect(DB)
    for _sql in _PURGE:
        _c.execute(_sql)
    _c.commit()
    _n = _c.execute("SELECT COUNT(*) FROM users WHERE name IN ('QA Tester','Stress Tester','QA Applicant')").fetchone()[0]
    _c.close()
    return _n

check("stale test data purged", _purge_test_data() == 0)

print("== 1. Public catalog & workers ==")
s, d = call("GET", "/api/catalog")
check("catalog loads", s==200 and len(d.get("trades",[]))==11)
check("stats sane", d["stats"]["workers"]>=40 and d["stats"]["jobs"]>1000, d.get("stats"))
s, d = call("GET", "/api/workers?trade=electrician")
check("worker list filters by trade", s==200 and len(d["workers"])>0)
wid = d["workers"][0]["id"]
s, d = call("GET", f"/api/workers/{wid}")
check("profile has certs+reviews+welfare", s==200 and "certifications" in d and "welfare" in d)
check("UAN not exposed", "e_shram_uan" not in json.dumps(d).lower())
check("worker phone masked in public profile", "*" in str(d["worker"].get("phone","")), d["worker"].get("phone"))
# regression: the profile payload must expose the SAME id key as the list endpoint.
# When it only had user_id, the profile's Book button sent worker_id=null and the
# booking was silently auto-matched to a different worker.
check("profile exposes the list-compatible worker id",
      d["worker"].get("id") is not None and d["worker"]["id"] == d["worker"]["user_id"],
      d["worker"].get("id"))

print("== 2. Auth ==")
s, cust = call("POST", "/api/login", {"phone":"9000000001","password":"demo123"})
check("customer login", s==200); CT = cust.get("token")
s, work = call("POST", "/api/login", {"phone":"8000000001","password":"demo123"})
check("worker login", s==200); WT = work.get("token")
s, adm = call("POST", "/api/login", {"phone":"7000000001","password":"admin123"})
check("admin login", s==200); AT = adm.get("token")
s, _ = call("POST", "/api/login", {"phone":"9000000001","password":"wrong"})
check("wrong password rejected", s==401)
s, _ = call("GET", "/api/a/overview", token=CT)
check("customer blocked from admin API", s==403)
# session tokens are header-only outside the two browser-download endpoints
s, _ = call("GET", f"/api/me?t={CT}")
check("token in query string rejected on normal endpoints", s==401, s)
# password storage: legacy SHA-256 rows must upgrade to PBKDF2 on first login
_c = _sq.connect(DB)
_hashes = [r[0] for r in _c.execute(
    "SELECT password_hash FROM users WHERE phone IN ('9000000001','8000000001','7000000001')")]
_c.close()
check("password hashes upgraded to PBKDF2", all(h.startswith("pbkdf2_sha256$") for h in _hashes),
      [h[:14] for h in _hashes])

print("== 3. Full booking lifecycle ==")
s, cat = call("GET", "/api/catalog")
svc = None
for t_, lst in cat["services_by_trade"].items():
    for x in lst:
        if x["slug"]=="tap-leak-fix": svc = x
assert svc, "tap-leak-fix missing"
zone = cat["zones"][0]["key"]
s, bk = call("POST", "/api/bookings", {
    "service_id": svc["id"], "scheduled_for": SOON,
    "address": "C-12, Test Colony", "zone": zone, "notes": "test job"}, token=CT)
check("booking created + matched worker", s==200 and bk.get("worker",{}).get("id"), bk)
check("booking response explains the match", bk.get("match_note") is not None or bk.get("worker",{}).get("distance_km") is not None)
BID = bk["booking_id"]; WID2 = bk["worker"]["id"]
s, _ = call("POST", f"/api/bookings/{BID}/cancel", token=CT)
check("cancel works pre-acceptance", s==200)

svc_e = None
for x in cat["services_by_trade"]["electrician"]:
    if x["slug"]=="mcb-switchboard": svc_e = x
assert svc_e, "mcb-switchboard missing"

def login_as_worker(wid):
    """Seeded workers use the seed password; the two demo accounts use demo123.
    Returns (token, phone) - token None for an account a person created by hand."""
    _c = _sq.connect(DB); _c.row_factory = _sq.Row
    _r = _c.execute("SELECT phone FROM users WHERE id=?", (wid,)).fetchone(); _c.close()
    if not _r: return None, None
    for _pw in ("worker@2026", "demo123"):
        _s, _d = call("POST", "/api/login", {"phone": _r["phone"], "password": _pw})
        if _s == 200 and _d.get("token"):
            return _d["token"], _r["phone"]
    return None, _r["phone"]

def pick_drivable_worker(trade="electrician", zone="east"):
    """First FREE verified worker of the trade whose account the suite can log into."""
    _s, _lst = call("GET", f"/api/workers?trade={trade}&zone={zone}")
    for _w in _lst.get("workers", []):
        if _w.get("busy"): continue
        _t, _ph = login_as_worker(_w["id"])
        if _t: return _w, _t
    return None, None

# The demo DB is a working product, not a fixture: whoever the matcher picks must be a
# FREE worker, and the suite then drives that worker's own account.
EID, WT2, WID_M = None, None, None
for _zone in ("east", "central", "south", "west", "north", "east"):
    s, emg = call("POST", "/api/bookings", {
        "service_id": svc_e["id"], "scheduled_for": SOON,
        "address": "A-9, Emergency Gali", "zone": _zone, "is_emergency": True}, token=CT)
    check(f"emergency booking created ({_zone})", s==200 and emg.get("booking_id"), emg)
    if s != 200: break
    EID, WID_M = emg["booking_id"], (emg.get("worker") or {}).get("id")
    _busy = (_sq.connect(DB).execute("""SELECT 1 FROM bookings WHERE worker_id=? AND status IN
             ('accepted','enroute','in_progress') LIMIT 1""", (WID_M,)).fetchone() if WID_M else True)
    T, _ph = login_as_worker(WID_M) if WID_M else (None, None)
    if T and not _busy:
        WT2 = T
        break
    call("POST", f"/api/bookings/{EID}/cancel", token=CT)
    EID = None
check("match lands on a free worker the suite can drive", EID is not None and WT2 is not None,
      f"booking={EID} worker={WID_M}")
if EID and WT2:
    s, wh = call("GET", "/api/w/home", token=WT2)
    check("emergency visible in worker hub", any(j["id"]==EID for j in wh["jobs"]))
    for st in ["accepted","enroute","in_progress","completed"]:
        s, r = call("POST", f"/api/w/jobs/{EID}/status", {"status":st}, token=WT2)
        check(f"status -> {st}", s==200, r)
        if st == "accepted":
            # while the job is live the worker must be reported busy AND a customer who
            # picks him by name must be refused with a nearest-free alternative (never a
            # silent reroute - that is the whole point of the fix)
            s, lst = call("GET", "/api/workers?trade=electrician")
            brow = [x for x in lst["workers"] if x["id"]==WID_M]
            check("busy worker flagged in the list", bool(brow) and brow[0]["busy"] is True,
                  brow[0] if brow else None)
            s, busy = call("POST", "/api/bookings", {
                "service_id": svc_e["id"], "scheduled_for": SOON2, "address": "Busy probe",
                "zone": "east", "worker_id": WID_M}, token=CT)
            _bd = busy.get("detail") if isinstance(busy, dict) else {}
            check("picking a busy worker is refused with an alternative",
                  s==409 and isinstance(_bd, dict) and _bd.get("busy") is True
                  and (_bd.get("alternative") or {}).get("id") not in (None, WID_M), busy)
    s, bad = call("POST", f"/api/w/jobs/{EID}/status", {"status":"accepted"}, token=WT2)
    check("invalid transition rejected", s==400)
if EID:
    s, pay = call("POST", f"/api/bookings/{EID}/pay", token=CT)
    check("demo payment: split correct", s==200 and pay["commission"]==round(pay["amount"]*0.10)
          and pay["amount"]-pay["commission"]==pay["worker_gets"], pay)
    s, inv, _ = call("GET", f"/api/bookings/{EID}/invoice.pdf", token=CT, raw=True)
    check("invoice PDF generated", s==200 and inv[:4]==b"%PDF", f"{len(inv)} bytes")
else:
    inv = b""
    check("demo payment: split correct", False, "no booking to pay")
    check("invoice PDF generated", False, "no booking to invoice")
# the 90/10 breakdown must actually be ON the page (regression: it used to be drawn off-page)
try:
    import fitz
    if inv[:4] == b"%PDF":                     # only parse when the endpoint really returned a PDF
        _doc = fitz.open(stream=inv, filetype="pdf")
        _txt = "\n".join(p.get_text() for p in _doc)
        _onpage = all(k in _txt for k in ["Job charge", "platform fee", "Worker receives directly"])
        _blocks = _doc[0].get_text("blocks")
        _offpage = any(b[3] < 0 for b in _blocks)
        check("invoice shows the full 90/10 breakdown on the page", _onpage and not _offpage,
              f"breakdown={_onpage} offpage_text={_offpage}")
    else:
        check("invoice shows the full 90/10 breakdown on the page", False,
              f"not a PDF: {inv[:80]!r}")      # fail loudly instead of crashing the suite
except ImportError:
    print("  (skipping PDF text check - PyMuPDF not installed)")
s, inv2, _ = call("GET", f"/api/bookings/{EID}/invoice.pdf?t={CT}", raw=True)  # browser-style link click
check("invoice via query-param token (real browser click)", isinstance(inv2,(bytes,bytearray)) and inv2[:4]==b"%PDF")
s, _ = call("GET", f"/api/bookings/{EID}/invoice.pdf")  # fully anonymous
check("invoice blocked without any token", s==401)
s, _ = call("POST", f"/api/bookings/{EID}/review", {"rating":5,"comment":"badhiya"}, token=CT)
check("review accepted", s==200)
s, r2 = call("POST", f"/api/bookings/{EID}/review", {"rating":4,"comment":""}, token=CT)
check("double review blocked", s==409)
s, _ = call("POST", f"/api/bookings/{EID}/pay", token=CT)
check("double payment blocked", s==409)

print("== 3b. Worker can decline an offer; it is re-routed, never stalled ==")
_pw, WT3 = pick_drivable_worker()
check("found a free worker for the decline probe", _pw is not None, "no drivable free worker")
if _pw and WT3:
    s, dbk = call("POST", "/api/bookings", {
        "service_id": svc_e["id"], "scheduled_for": SOON2, "address": "Decline probe, Gali 9",
        "zone": "east", "worker_id": _pw["id"]}, token=CT)
    check("booking targeted at the chosen worker", s==200 and dbk["worker"]["id"]==_pw["id"], dbk)
    check("response says it used the chosen worker", s==200 and dbk.get("match_note")=="Your chosen worker", dbk.get("match_note"))
    if s==200:
        DID = dbk["booking_id"]
        s, dec = call("POST", f"/api/w/jobs/{DID}/decline", token=WT3)
        check("worker decline accepted", s==200, dec)
        s, det = call("GET", f"/api/bookings/{DID}", token=AT)
        moved = det["booking"]["worker_id"] != _pw["id"] or det["booking"]["status"]=="cancelled"
        check("declined booking re-routed or cancelled (never stuck on the decliner)",
              s==200 and moved, det.get("booking",{}).get("status"))
        s, dec2 = call("POST", f"/api/w/jobs/{DID}/decline", token=WT3)
        check("second decline by same worker rejected", s in (400,403,404), s)
        # the customer must be able to SEE what happened, not just find a different name
        s, det = call("GET", f"/api/bookings/{DID}", token=AT)
        evs = det.get("booking", {}).get("events", []) if s == 200 else []
        kinds = [e["kind"] for e in evs]
        check("activity log records the decline", "declined" in kinds, kinds)
        redis = [e for e in evs if e["kind"] == "redispatched"]
        check("activity log records the re-dispatch with the new worker",
              (bool(redis) and bool(redis[0]["detail"])) or "no_worker" in kinds, kinds)
        check("activity log lines carry IST times", all(e.get("at_ist") for e in evs), evs)
        s, mine = call("GET", "/api/bookings/mine", token=CT)
        mb = next((x for x in mine.get("bookings", []) if x["id"] == DID), {})
        check("customer's list carries the same activity log", len(mb.get("events") or []) >= 2,
              mb.get("events"))
        call("POST", f"/api/bookings/{DID}/cancel", token=CT)

print("== 3c. stale / past bookings are refused, not stored ==")
from datetime import datetime as _dt, timedelta as _td
past = (_dt.now() - _td(days=3)).isoformat(timespec="minutes")
s, r = call("POST", "/api/bookings", {
    "service_id": svc_e["id"], "scheduled_for": past, "address": "Past probe",
    "zone": "east"}, token=CT)
check("booking in the past rejected", s == 400, f"{s} {r}")

print("== 3d. Input validation ==")
s, _ = call("POST", "/api/bookings", {"service_id": svc["id"], "scheduled_for": SOON,
                                      "address": "V-probe 1", "zone": "atlantis"}, token=CT)
check("unknown zone rejected", s==400, s)
s, _ = call("POST", "/api/bookings", {"service_id": svc["id"], "scheduled_for": PAST,
                                      "address": "V-probe 2", "zone": "south"}, token=CT)
check("past-dated booking rejected", s==400, s)
s, _ = call("POST", "/api/bookings", {"service_id": svc["id"], "scheduled_for": SOON,
                                      "address": "V-probe 3", "zone": "south",
                                      "notes": "x"*200000}, token=CT)
check("oversized payload rejected (413)", s==413, s)
s, _ = call("POST", "/api/bookings", {"service_id": svc["id"], "scheduled_for": SOON,
                                      "address": "V-probe 4", "zone": "south",
                                      "notes": "x"*5000}, token=CT)
check("over-long notes rejected (422)", s==422, s)
s, _ = call("POST", "/api/apply-worker", {"name":"QA Applicant","phone":"9130000001",
                                          "password":"a","trade":"plumber","coop_id":1})
check("worker signup rejects a 1-character password", s==422, s)
s, _ = call("POST", "/api/login", {"phone":"9000000001","password":"demo123","extra":"ignored"})
check("login tolerates extra fields", s==200, s)

print("== 4. New customer registration flow ==")
uniq = str(random.randrange(1000, 9999))
s, nu = call("POST", "/api/register-customer", {"name":"QA Tester","phone":"911"+uniq.zfill(7),"password":"test123"})
check("signup works", s==200)
NT = nu.get("token")
s, dup = call("POST", "/api/register-customer", {"name":"X","phone":"911"+uniq.zfill(7),"password":"test123"})
check("duplicate phone blocked", s==409)

print("== 5. Worker application -> admin verification -> badge ==")
wuniq = str(random.randrange(1000, 9999))
s, appl = call("POST", "/api/apply-worker", {
    "name":"QA Applicant","phone":"912"+wuniq.zfill(7),"password":"test123",
    "trade":"plumber","coop_id":1,"exp_years":7,"cert_title":"ITI Plumbing"})
check("worker application submitted", s==200)
APT = appl.get("token")
s, pw = call("GET", "/api/a/pending-workers", token=AT)
target = [w for w in pw["pending"] if w["name"]=="QA Applicant"]
check("applicant in admin queue", len(target)==1)
if target:
    s, vr = call("POST", f"/api/a/verify/{target[0]['id']}", {"approve":True}, token=AT)
    check("admin approves -> verified", s==200 and vr["new_status"]=="verified")
    s, me = call("GET", "/api/me", token=APT)
    check("applicant sees verified badge", me.get("worker",{}).get("status")=="verified")

print("== 6. Admin dashboard APIs ==")
s, ov = call("GET", "/api/a/overview", token=AT)
check("overview stats populated", s==200 and ov["stats"]["workers_verified"]>0)

# Payout is proven on a QA booking parked on its own future date, so a test run can
# never settle the product's real history. (It once did: the old test ran a whole-year
# period, and with the new settlement ledger that would have paid out everything.)
PDAY = (datetime.now() + timedelta(days=46)).strftime("%Y-%m-%d")
PDAY2 = (datetime.now() + timedelta(days=47)).strftime("%Y-%m-%d")
_ppw, WT4 = pick_drivable_worker()
s, pb = call("POST", "/api/bookings", {
    "service_id": svc_e["id"], "scheduled_for": PDAY + "T10:00", "address": "QA Payout Probe",
    "zone": "east", "worker_id": (_ppw or {}).get("id")}, token=CT) if _ppw else (0, {})
PBID = pb.get("booking_id") if s == 200 else None
NET = None
if PBID:
    for _st in ("accepted", "enroute", "in_progress", "completed"):
        call("POST", f"/api/w/jobs/{PBID}/status", {"status": _st}, token=WT4)
    s, ppay = call("POST", f"/api/bookings/{PBID}/pay", token=CT)
    NET = ppay.get("worker_gets") if s == 200 else None
check("payout probe booking completed and paid", PBID is not None and NET is not None)
s, pr = call("POST", "/api/a/payouts/run", {"period_start": PDAY, "period_end": PDAY}, token=AT)
check("payout run settles the QA job exactly",
      s==200 and pr.get("jobs")==1 and pr.get("total_net")==NET, (pr, NET))
check("payout run returns a working CSV url", pr.get("csv","").endswith(f"/{pr.get('run_id')}"), pr.get("csv"))
s, csvf, _ = call("GET", pr.get("csv","/x"), token=AT, raw=True)
check("payout CSV downloadable from the returned url", s==200 and b"net_to_worker" in csvf, s)
s2, _ = call("POST", "/api/a/payouts/run", {"period_start": PDAY, "period_end": PDAY}, token=AT)
check("duplicate payout period blocked (409)", s2==409, s2)
s3, pr3 = call("POST", "/api/a/payouts/run",
               {"period_start": PDAY, "period_end": PDAY2, "confirm_duplicate": True}, token=AT)
check("overlapping payout run pays nothing twice",
      s3==200 and pr3.get("jobs")==0 and pr3.get("total_net")==0
      and pr3.get("already_settled_skipped", 0) >= 1, pr3)
# the probe's own payout rows are test artifacts - take them back out of history
try:
    _c = _sq.connect(DB)
    _runs = [r for r in (pr.get("run_id"), pr3.get("run_id")) if r]
    if _runs:
        _c.execute("DELETE FROM payout_items WHERE run_id IN (%s)" % ",".join("?"*len(_runs)), _runs)
        _c.execute("DELETE FROM payout_runs WHERE id IN (%s)" % ",".join("?"*len(_runs)), _runs)
        _c.commit()
    for _r in _runs:
        try: os.remove(os.path.join(os.path.dirname(DB), f"payout_{_r}.csv"))
        except OSError: pass
    _c.close()
except Exception as e:
    print("  (payout probe cleanup skipped:", e, ")")
s, wf = call("GET", "/api/a/welfare", token=AT)
uncovered = [w for w in wf["workers"] if not w["schemes"]]
if uncovered:
    s, enr = call("POST", "/api/a/welfare/enroll",
                  {"worker_id":uncovered[0]["id"], "scheme":"PMSBY"}, token=AT)
    check("welfare enrollment works", s==200)
    s, dup2 = call("POST", "/api/a/welfare/enroll", {"worker_id":uncovered[0]["id"],"scheme":"PMSBY"}, token=AT)
    check("double enroll blocked", s==409)
else:
    check("welfare enrollment (no uncovered worker found)", False, "seed should have uncovered workers")
s, fc = call("GET", "/api/a/forecast", token=AT)
check("forecast grid generated", s==200 and len(fc["rows"])>50)
s, fs = call("GET", "/api/a/forecast/summary", token=AT)
check("forecast summary signals", s==200 and "top" in fs)

print("== 7. Static frontend & ops surface ==")
for p in ["/", "/static/js/app.js", "/static/css/base.css", "/static/vendor/leaflet.js", "/static/img/w1.jpg"]:
    sc, _, hdrs = call("GET", p, raw=True)
    check(f"serves {p}", sc==200)
sc, _, _ = call("GET", "/", raw=True)
req = urllib.request.Request(BASE + "/", method="HEAD")
try:
    r = urllib.request.urlopen(req, timeout=10)
    check("HEAD / supported", r.status==200)
except Exception as e:
    check("HEAD / supported", False, str(e)[:60])
s, h = call("GET", "/api/health")
check("health endpoint", s==200 and h.get("ok") is True, h)
sc, _, hdrs = call("GET", "/static/js/app.js", raw=True)
_hdrs = {k.lower(): v for k, v in hdrs.items()}      # uvicorn lowercases header names
check("static assets cacheable, HTML revalidates",
      "max-age=604800" in _hdrs.get("cache-control", ""), _hdrs.get("cache-control"))
sc, _, hdrs = call("GET", "/", raw=True)
_hdrs = {k.lower(): v for k, v in hdrs.items()}
check("HTML revalidates (no-cache)", "no-cache" in _hdrs.get("cache-control", ""), _hdrs.get("cache-control"))
sc, _, hdrs = call("GET", "/static/sw.js", raw=True)
_hdrs = {k.lower(): v for k, v in hdrs.items()}
check("service worker never cached", "no-cache" in _hdrs.get("cache-control", ""), _hdrs.get("cache-control"))

print("== 8. Cooperative society dashboard, certifications, welfare workflow, allocation ==")
# society admin for cooperative 1 (created by the schema migration / seed)
s, sd = call("POST", "/api/login", {"phone":"7000000101","password":"admin123"})
ST = sd.get("token") if s==200 else None
check("society admin can log in and is scoped to one cooperative",
      s==200 and (sd.get("user",{}).get("coop") or {}).get("id")==1, sd if s!=200 else sd.get("user",{}).get("coop"))
s, ch = call("GET", "/api/c/home", token=ST)
check("society home returns its own workers + earnings + queues",
      s==200 and ch["stats"]["workers"]>0 and "zone_demand_7d" in ch,
      ch.get("stats") if s==200 else ch)
_sql = _sq.connect(DB)
_coop_workers = _sql.execute("SELECT COUNT(*) FROM workers WHERE coop_id=1").fetchone()[0]
_sql.close()
check("society stats count only its own cooperative's workers",
      s==200 and ch["stats"]["workers"]==_coop_workers, f"api={ch['stats']['workers'] if s==200 else '?'} db={_coop_workers}")
s, dch = call("GET", "/api/c/home", token=CT)
check("customer token refused on the society dashboard", s==403, s)

# certification trail: worker adds -> society verifies -> public profile shows it verified.
# Runs as the QA Applicant worker, so the existing purge rules (by user name) clean it up.
_sql = _sq.connect(DB); _sql.row_factory = _sq.Row
_me = _sql.execute("""SELECT w.user_id id FROM workers w JOIN users u ON u.id=w.user_id
                      WHERE u.name='QA Applicant'""").fetchone()
_sql.close()
QAW = _me["id"] if _me else None
s, nc = call("POST", "/api/w/certs", {"title":"QA Cert", "issuer":"NCCT", "year":2025}, token=APT)
CID = nc.get("id") if s==200 else None
check("worker-added certificate starts pending", s==200 and nc.get("status")=="pending", nc)
s, pv = call("GET", f"/api/workers/{QAW}")
_selfcert = next((c for c in pv["certifications"] if c["id"]==CID), None)
check("it is visible on the profile as pending (not counted yet)",
      _selfcert and _selfcert["status"]=="pending", _selfcert)
s, vc = call("POST", f"/api/c/certs/{CID}", {"approve":True}, token=ST)
s, pv2 = call("GET", f"/api/workers/{QAW}")
_vcert = next((c for c in pv2["certifications"] if c["id"]==CID), None)
check("society verification flips it to verified", vc.get("status")=="verified" and _vcert["status"]=="verified", _vcert)
s, prof = call("GET", f"/api/workers/{QAW}")
check("profile carries a computed skill level + insured flag",
      prof["worker"].get("skill_level") in ("helper","skilled","expert") and "insured" in prof["worker"],
      f"skill_level={prof['worker'].get('skill_level')} insured={prof['worker'].get('insured')}")

# welfare: apply -> society approves -> claim -> society decides (all as the QA worker)
s, wa = call("POST", "/api/w/welfare/apply", {"scheme":"PMJJBY"}, token=APT)
check("worker can apply for PMJJBY himself", s==200 and wa.get("status")=="pending", wa)
s, sq = call("GET", "/api/c/home", token=ST)
check("society sees the pending application in its own queue",
      any(x["worker_id"]==QAW for x in sq.get("welfare_requests",[])), sq.get("welfare_requests"))
s, wd = call("POST", "/api/c/welfare/decide", {"worker_id":QAW,"scheme":"PMJJBY","approve":True}, token=ST)
check("society approval activates the cover", s==200 and wd.get("status")=="active", wd)
s, cl = call("POST", "/api/w/welfare/claim", {"scheme":"PMJJBY","reason":"QA claim probe","amount":1000}, token=APT)
check("worker can file a claim against the active scheme", s==200 and cl.get("status")=="filed", cl)
s, sq2 = call("GET", "/api/c/home", token=ST)
_claim = next((x for x in sq2.get("claims",[]) if x["worker_id"]==QAW), None)
s, cdec = call("POST", f"/api/c/welfare/claim/{_claim['id']}", {"approve":True}, token=ST)
check("society decides the claim", s==200 and cdec.get("status")=="approved", cdec)
s, cdup = call("POST", "/api/w/welfare/apply", {"scheme":"PMJJBY"}, token=APT)
check("duplicate welfare application refused", s==409, s)

# allocation board
s, al = call("GET", "/api/a/allocation", token=AT)
check("allocation board joins forecast demand with supply and gives an action per row",
      s==200 and len(al.get("rows",[]))>10 and all(r.get("action") for r in al["rows"]),
      al["rows"][0]["action"] if s==200 and al.get("rows") else al)
s, al2 = call("GET", "/api/a/allocation", token=CT)
check("allocation board is admin-only", s==403, s)

# scheduling bounds (the wizard now offers a real date+time picker)
_soon = (datetime.now() + timedelta(days=5)).replace(hour=11, minute=0, second=0, microsecond=0)
s, sb = call("POST", "/api/bookings", {"service_id": svc_e["id"], "scheduled_for": _soon.isoformat(),
                                       "address": "QA schedule probe", "zone": "east"}, token=CT)
SBID = sb.get("booking_id") if s==200 else None
check("a booking can be scheduled 5 days out at 11:00", s==200 and SBID, sb if s!=200 else f"#{SBID}")
s_p, _ = call("POST", "/api/bookings", {"service_id": svc_e["id"],
                                        "scheduled_for": (datetime.now()-timedelta(days=1)).isoformat(),
                                        "address": "QA schedule probe", "zone": "east"}, token=CT)
s_f, _ = call("POST", "/api/bookings", {"service_id": svc_e["id"],
                                        "scheduled_for": (datetime.now()+timedelta(days=100)).isoformat(),
                                        "address": "QA schedule probe", "zone": "east"}, token=CT)
check("scheduling bounds: past refused, +100 days refused", s_p==400 and s_f==400, f"{s_p}/{s_f}")
if SBID:
    call("POST", f"/api/bookings/{SBID}/cancel", token=CT)

print()
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")

# leave the live DB exactly as we found it — remove everything this run created
_left = _purge_test_data()
print(f"(post-run cleanup: test users remaining = {_left})")
if FAIL:
    print("FAILED:", *FAIL, sep="\n - ")
    sys.exit(1)
