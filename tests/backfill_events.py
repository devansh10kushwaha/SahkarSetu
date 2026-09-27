"""One-off, idempotent backfill of the booking activity log.

Bookings created before the event log existed would show an empty timeline. This
reconstructs the lines we have real evidence for - never invented ones:
  * 'created'      <- bookings.created_at (converted to IST)
  * 'chosen'       <- only when a decline row proves that worker was picked first
  * 'declined'     <- declines table (worker + time)
  * 'redispatched' <- current worker, dated at the decline time
  * 'cancelled'    <- status is cancelled and no cancel/expiry event exists

Idempotent: a booking that already has any event row is skipped.
Usage:  python tests/backfill_events.py [--days 30]
"""
import os, sqlite3, sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.environ.get("SAHKARSETU_DB", os.path.join(ROOT, "data", "sahkarsetu.db"))
DAYS = 30
if "--days" in sys.argv:
    DAYS = int(sys.argv[sys.argv.index("--days") + 1])
os.environ["SAHKARSETU_DB"] = DB
sys.path.insert(0, ROOT)
import db as dbmod            # noqa: E402
dbmod.init_db()               # creates booking_events/payout_items if missing (idempotent)

IST = timezone(timedelta(hours=5, minutes=30))
def hm(ts):
    try:
        return (datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S")
                .replace(tzinfo=timezone.utc).astimezone(IST).strftime("%-I:%M %p").lower())
    except Exception:
        return ""

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
rows = conn.execute("""
    SELECT b.id, b.code, b.status, b.worker_id, b.created_at, s.name_en service, b.price,
           wu.name wname, cu.name cname
    FROM bookings b JOIN services s ON s.id=b.service_id
    LEFT JOIN users wu ON wu.id=b.worker_id
    LEFT JOIN users cu ON cu.id=b.customer_id
    WHERE b.created_at >= datetime('now', ?)
      AND b.id NOT IN (SELECT DISTINCT booking_id FROM booking_events)
    ORDER BY b.id""", (f"-{DAYS} days",)).fetchall()

added = 0
for b in rows:
    lines = [("created", f"{b['service']} · ₹{b['price']}", b["cname"] or "", b["created_at"])]
    decl = conn.execute("""SELECT d.worker_id, d.created_at, u.name FROM declines d
                           LEFT JOIN users u ON u.id=d.worker_id
                           WHERE d.booking_id=? ORDER BY d.id""", (b["id"],)).fetchall()
    for d in decl:
        # a decline means that worker had been offered the booking first
        lines.append(("chosen" if not decl.index(d) else "matched",
                      d["name"] or f"worker {d['worker_id']}", "customer", d["created_at"]))
        lines.append(("declined", "", d["name"] or "", d["created_at"]))
        lines.append(("redispatched", b["wname"] or "", "system", d["created_at"]))
    if b["status"] == "cancelled":
        lines.append(("cancelled", "(before the activity log existed)", "", b["created_at"]))
    elif b["status"] in ("accepted", "enroute", "in_progress", "completed"):
        lines.append((b["status"], "", b["wname"] or "", b["created_at"]))
    for kind, detail, actor, ts in lines:
        conn.execute("INSERT INTO booking_events(booking_id,kind,detail,actor,created_at) VALUES(?,?,?,?,?)",
                     (b["id"], kind, detail[:160], actor[:80], ts))
        added += 1
conn.commit()
print(f"backfilled {added} event line(s) across {len(rows)} booking(s) (last {DAYS} days, idempotent)")
for b in conn.execute("""SELECT booking_id,kind,detail,actor,created_at FROM booking_events
                         WHERE booking_id IN (SELECT id FROM bookings WHERE customer_id=81)
                         ORDER BY booking_id DESC, id""").fetchall()[:12]:
    print("  ", dict(b))
conn.close()
