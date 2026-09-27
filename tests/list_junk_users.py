"""List non-seed users so QA leftovers are visible (and can be purged)."""
import os, sqlite3, sys

DB = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sahkarsetu.db")
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row
seed_names = {"Priya Sharma", "Ramesh Kumar", "Sh. O.P. Meena (IFS)", "QA Tester", "Stress Tester", "QA Applicant"}
rows = c.execute("SELECT id, name, phone, role, created_at FROM users ORDER BY id").fetchall()
print(f"total users: {len(rows)}")
sus = [r for r in rows if r["name"] in ("Brute Bait",) or r["name"].startswith(("QA", "Stress", "Brute", "Probe"))]
print("QA/leftover accounts:")
for r in sus:
    print(f"  #{r['id']:3} {r['name']:20} {r['phone']:12} {r['role']:16} created {r['created_at']}")
c.close()
