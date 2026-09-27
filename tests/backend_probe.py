"""Isolated backend probe - runs against a COPY of the live DB, never the live file.

Covers the checks that would corrupt real data if run on the live database:
  1. payout double-settle guard (overlapping periods must not pay a job twice)
  2. stale-offer expiry sweep (unaccepted 'requested' bookings auto-cancel)
  3. decline -> re-dispatch, including the activity log the customer reads

Usage:  python tests/backend_probe.py
"""
import os, shutil, sqlite3, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE = os.environ.get("SAHKARSETU_LIVE_DB", os.path.join(ROOT, "data", "sahkarsetu.db"))
S = tempfile.mkdtemp(prefix="ss_probe_")
DB = os.path.join(S, "probe.db")
shutil.copy(LIVE, DB)
# SQLite WAL: recent commits live in the -wal sidecar, so a plain file copy would
# silently test a stale snapshot (it did - the copy was missing the newest bookings).
for side in ("-wal", "-shm"):
    if os.path.exists(LIVE + side):
        shutil.copy(LIVE + side, DB + side)
os.environ["SAHKARSETU_DB"] = DB
sys.path.insert(0, ROOT)
import main  # noqa: E402  (must import after SAHKARSETU_DB points at the copy)

PASS, FAIL = [], []
def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  \u2713 " if cond else "  \u2717 ") + name + (f"  -> {extra}" if extra and not cond else ""))

def c():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

print(f"probe DB: {DB}  (copy of {LIVE})")

# ---------------------------------------------------------------- 1. payout guard
print("\n== payout runs: a job must never be settled twice ==")
conn = c()
row = conn.execute("""SELECT b.id, b.worker_id, p.net FROM bookings b
                      JOIN payments p ON p.booking_id=b.id
                      WHERE b.status='completed' AND b.worker_id IS NOT NULL
                        AND p.net IS NOT NULL AND p.net > 0
                        AND b.id NOT IN (SELECT booking_id FROM payout_items)
                        AND b.worker_id NOT IN (
                            SELECT b2.worker_id FROM bookings b2 JOIN payments p2 ON p2.booking_id=b2.id
                            WHERE date(b2.scheduled_for)=date('now','+45 days'))
                      ORDER BY b.id DESC LIMIT 1""").fetchone()
check("found a completed+paid booking to probe with", row is not None)
if row:
    bid, wid, net = row["id"], row["worker_id"], row["net"]
    day = conn.execute("SELECT date('now','+45 days') d").fetchone()["d"]
    others = conn.execute("""SELECT COUNT(*) n FROM bookings b JOIN payments p ON p.booking_id=b.id
                             WHERE date(b.scheduled_for)=? AND b.id!=?""", (day, bid)).fetchone()["n"]
    check("probe date is clear of other paid bookings", others == 0, f"{others} others on {day}")
    conn.execute("UPDATE bookings SET scheduled_for=? WHERE id=?", (day + "T10:00:00", bid))
    conn.commit()
    conn.close()

    r1 = main.payout_run(main.PayoutRunIn(period_start=day, period_end=day),
                         {"name": "probe"})
    check("run #1 settles exactly the probe job", r1["jobs"] == 1 and r1["total_net"] == net,
          f'jobs={r1["jobs"]} net={r1["total_net"]} expected={net}')

    nxt = conn2 = sqlite3.connect(DB)
    nxt.row_factory = sqlite3.Row
    nxt_day = nxt.execute(f"SELECT date('{day}','+1 day') d").fetchone()["d"]
    nxt.close()
    r2 = main.payout_run(main.PayoutRunIn(period_start=day, period_end=nxt_day,
                                          confirm_duplicate=True), {"name": "probe"})
    check("run #2 (overlapping period) pays NOTHING again",
          r2["jobs"] == 0 and r2["total_net"] == 0,
          f'jobs={r2["jobs"]} net={r2["total_net"]}')
    check("run #2 reports the job as already settled", r2["already_settled_skipped"] >= 1,
          r2["already_settled_skipped"])

    conn = c()
    items = conn.execute("SELECT run_id FROM payout_items WHERE booking_id=?", (bid,)).fetchall()
    check("payout_items holds exactly one settlement for the job",
          len(items) == 1 and items[0]["run_id"] == r1["run_id"], [dict(i) for i in items])
    conn.close()
    # CSVs are written next to the app: remove the probe's own files
    for rid_ in (r1["run_id"], r2["run_id"]):
        try:
            os.remove(os.path.join(ROOT, "data", f"payout_{rid_}.csv"))
        except OSError:
            pass

# ---------------------------------------------------------------- 2. expiry sweep
print("\n== stale offers: unaccepted requests must not linger forever ==")
conn = c()
cust = conn.execute("SELECT id FROM users WHERE role='customer' LIMIT 1").fetchone()["id"]
srv = conn.execute("SELECT id, trade FROM services LIMIT 1").fetchone()
wk = conn.execute("SELECT user_id FROM workers WHERE trade=? AND status='verified' LIMIT 1",
                  (srv["trade"],)).fetchone()
zc = conn.execute("SELECT zone FROM workers WHERE user_id=?", (wk["user_id"],)).fetchone()["zone"]
old = conn.execute("""INSERT INTO bookings(code,customer_id,worker_id,service_id,scheduled_for,address,
                      zone,status,price,created_at)
                      VALUES('PROBE-OLD',?,?,?,datetime('now'),'probe addr',?,'requested',100,
                             datetime('now','-3 days'))""",
                   (cust, wk["user_id"], srv["id"], zc)).lastrowid
fresh = conn.execute("""INSERT INTO bookings(code,customer_id,worker_id,service_id,scheduled_for,address,
                        zone,status,price) VALUES('PROBE-FRESH',?,?,?,datetime('now'),'probe addr',?,
                        'requested',100)""",
                     (cust, wk["user_id"], srv["id"], zc)).lastrowid
conn.commit()
conn.close()

expired = main.expire_stale_requests()
st = {r["id"]: r["status"] for r in c().execute(
    "SELECT id,status FROM bookings WHERE id IN (?,?)", (old, fresh))}
check("3-day-old request was expired", old in expired and st[old] == "cancelled",
      f"expired={expired} status={st.get(old)}")
check("fresh request untouched", fresh not in expired and st[fresh] == "requested", st.get(fresh))
evs = [r["kind"] for r in c().execute(
    "SELECT kind FROM booking_events WHERE booking_id=? ORDER BY id", (old,))]
check("expiry is explained in the activity log", "expired" in evs, evs)

# ---------------------------------------------------------------- 3. decline trail
print("\n== decline -> re-dispatch, with the log the customer reads ==")
conn = c()
wk2 = conn.execute("SELECT user_id FROM workers WHERE trade=? AND status='verified' LIMIT 1",
                   (srv["trade"],)).fetchone()["user_id"]
bid = conn.execute("""INSERT INTO bookings(code,customer_id,worker_id,service_id,scheduled_for,address,
                      zone,status,price) VALUES('PROBE-DECLINE',?,?,?,datetime('now','+1 day'),
                      'probe addr',?,'requested',100)""",
                   (cust, wk2, srv["id"], zc)).lastrowid
conn.commit()
conn.close()
res = main.decline_job(bid, {"id": wk2, "name": "Probe Worker", "role": "worker"})
kinds = [r["kind"] for r in c().execute(
    "SELECT kind FROM booking_events WHERE booking_id=? ORDER BY id", (bid,))]
new_worker = c().execute("SELECT worker_id FROM bookings WHERE id=?", (bid,)).fetchone()["worker_id"]
check("decline is logged", "declined" in kinds, kinds)
check("booking moved to a different worker", new_worker != wk2, f"{wk2} -> {new_worker}")
check("re-dispatch is logged", "redispatched" in kinds, kinds)
check("response reports the new worker", bool(res.get("reassigned")), res)

# ---------------------------------------------------------------- 4. matcher ranking robustness
# Regression: ranking used to put the candidate DICT inside the sort tuple, so two
# workers with equal score/rating crashed the booking path with
# "TypeError: '<' not supported between instances of 'dict' and 'dict'".
print("\n== matcher: every trade x zone ranks without blowing up (tie regression) ==")
conn = c()
trades = [r[0] for r in conn.execute("SELECT DISTINCT trade FROM workers")]
zones = [r[0] for r in conn.execute("SELECT DISTINCT zone FROM workers WHERE zone IS NOT NULL")]
calls, errors, empty = 0, 0, 0
for t in trades:
    svc = {"trade": t, "pmin": 200, "pmax": 500}
    for z in zones:
        calls += 1
        try:
            got = main.find_matches(svc, z, limit=3)
            if not got:
                empty += 1
            for cand in got:
                if not ({"id", "why", "score", "skill_level"} <= set(cand)):
                    errors += 1
        except Exception as e:                       # noqa: BLE001 - the whole point
            errors += 1
            print("    crash:", t, z, type(e).__name__, e)
check(f"find_matches ran for all {calls} trade x zone combinations without a crash",
      errors == 0, f"{errors} errors")
check("every candidate carries the explanation fields (why/score/skill_level)",
      errors == 0 and calls > 20, f"{calls} calls, {empty} zones legitimately empty")
# equal-score tie: two identical workers must still produce a stable, crash-free order
conn.execute("""INSERT INTO users(phone,password_hash,name,role) VALUES('9111000001','x','Tie A','worker')""")
conn.execute("""INSERT INTO users(phone,password_hash,name,role) VALUES('9111000002','x','Tie B','worker')""")
aid = conn.execute("SELECT id FROM users WHERE phone='9111000001'").fetchone()[0]
bid = conn.execute("SELECT id FROM users WHERE phone='9111000002'").fetchone()[0]
for wid in (aid, bid):
    conn.execute("""INSERT INTO workers(user_id,coop_id,trade,exp_years,status,zone,lat,lng,rating_avg,jobs_done)
                    VALUES(?,1,'electrician',5,'verified','east',28.6702,77.2674,4.5,10)""", (wid,))
conn.commit()
try:
    tied = main.find_matches({"trade": "electrician"}, "east", limit=3)
    check("two identical workers (exact score tie) rank without a TypeError",
          isinstance(tied, list) and len(tied) >= 2, tied)
finally:
    conn.execute("DELETE FROM workers WHERE user_id IN (?,?)", (aid, bid))
    conn.execute("DELETE FROM users WHERE id IN (?,?)", (aid, bid))
    conn.commit()

print(f"\nPROBE RESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("failed:", FAIL)
shutil.rmtree(S, ignore_errors=True)
sys.exit(1 if FAIL else 0)
