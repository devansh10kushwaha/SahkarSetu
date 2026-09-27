"""Shared helpers for the SahkarSetu QA suites.

Why this file exists: the suites write through two channels at the same time -
the HTTP API (which writes to whatever database the *server* has open) and direct
SQLite (`SAHKARSETU_DB`, used for purge + invariant checks). If those two point at
different files, the suites create rows in the live database and then "clean up"
a different file, reporting success while leaving junk in the demo directory.
`assert_same_db()` compares the server's user count (from /api/health) with the
database file's count and refuses to start when they disagree.
"""
import json, os, sqlite3, sys, urllib.request

BASE = os.environ.get("SAHKARSETU_BASE", "http://localhost:3001")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.environ.get("SAHKARSETU_DB", os.path.join(REPO, "data", "sahkarsetu.db"))

def resolve(label="QA suite"):
    """Announce the resolved environment so a misconfiguration is visible up front."""
    print(f"[env] {label}: BASE={BASE}  DB={DB}")
    if "SAHKARSETU_DB" in os.environ or "SAHKARSETU_BASE" in os.environ:
        print("[env] (overridden via environment variables)")
    return BASE, DB

def assert_same_db(strict=True):
    """Abort when the API's database and SAHKARSETU_DB are different files."""
    try:
        with urllib.request.urlopen(BASE + "/api/health", timeout=10) as r:
            api = json.loads(r.read())
        api_n = api.get("users")
    except Exception as e:                                    # server down?
        print(f"[env] WARNING: cannot reach {BASE}/api/health ({type(e).__name__}) - "
              f"skipping database identity check")
        return
    if api_n is None:
        print("[env] WARNING: /api/health has no user count - skipping database identity check")
        return
    c = sqlite3.connect(DB)
    try:
        local_n = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        c.close()
    if api_n != local_n:
        msg = (f"[env] DATABASE MISMATCH: the server at {BASE} reports {api_n} users but {DB} holds {local_n}. "
               f"Run data would land in one file and cleanup in the other. Fix SAHKARSETU_DB (or unset it) and re-run.")
        print(msg)
        if strict:
            sys.exit(2)
    else:
        print(f"[env] database identity OK - both sides see {api_n} users")
