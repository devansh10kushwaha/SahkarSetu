"""Purge leftover QA/test accounts from a SahkarSetu database.

Suites are self-cleaning now, but older runs (before the 21 Sep 2026 audit)
leaked accounts like "Brute Bait" into the demo directory. Run this once
against a database that predates the fix:

    python3 tests/purge_junk.py [/path/to/sahkarsetu.db]
"""
import os, sqlite3, sys

DB = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sahkarsetu.db")
JUNK_NAMES = ("Brute Bait", "QA Tester", "QA Applicant", "Stress Tester", "Probe Tester")

c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row
found = c.execute(f"SELECT id, name, phone, created_at FROM users WHERE name IN ({','.join('?'*len(JUNK_NAMES))})",
                  JUNK_NAMES).fetchall()
if not found:
    print("nothing to purge - directory is clean")
    sys.exit(0)
for r in found:
    print(f"remove #{r['id']} {r['name']} ({r['phone']}) created {r['created_at']}")
    ids = [r["id"]]
    c.execute(f"DELETE FROM sessions WHERE user_id IN ({','.join('?'*len(ids))})", ids)
    c.execute(f"""DELETE FROM payments WHERE booking_id IN (SELECT id FROM bookings
                  WHERE customer_id IN ({','.join('?'*len(ids))}))""", ids)
    c.execute(f"""DELETE FROM reviews WHERE booking_id IN (SELECT id FROM bookings
                  WHERE customer_id IN ({','.join('?'*len(ids))}))""", ids)
    c.execute(f"DELETE FROM bookings WHERE customer_id IN ({','.join('?'*len(ids))})", ids)
    c.execute(f"DELETE FROM users WHERE id IN ({','.join('?'*len(ids))})", ids)
c.commit()
total = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
print(f"purged {len(found)} account(s); users now {total} | integrity: {c.execute('PRAGMA integrity_check').fetchone()[0]}")
c.close()
