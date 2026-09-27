"""Post-migration check for the live DB (run after the fixed app boots against it)."""
import os, sqlite3, sys

DB = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sahkarsetu.db")
c = sqlite3.connect(DB)
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
idx = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'")]
print("declines table auto-created:", "declines" in tables)
print("indexes auto-created:", idx)
print("users:", c.execute("SELECT COUNT(*) FROM users").fetchone()[0],
      "| bookings:", c.execute("SELECT COUNT(*) FROM bookings").fetchone()[0],
      "| payments:", c.execute("SELECT COUNT(*) FROM payments").fetchone()[0])
print("integrity:", c.execute("PRAGMA integrity_check").fetchone()[0])
c.close()
