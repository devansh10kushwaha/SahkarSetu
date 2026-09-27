"""Fresh-clone bootstrap test.

Copies the app into a scratch directory with NO data/ dir and NO database, then
boots it exactly the way the README tells a judge to (`uvicorn main:app`) and
checks it self-seeds and serves. This path used to be broken three ways:
missing data/ dir crashed seeding, plain uvicorn never seeded at all, and the
process that DID seed closed its own connection.

    python3 tests/boot_check.py
"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
PORT = os.environ.get("SAHKARSETU_BOOT_PORT", "3097")
WORK = os.path.join(tempfile.gettempdir(), "sahkarsetu_boot_check")
BASE = f"http://127.0.0.1:{PORT}"

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=5) as r:
        return r.status, json.loads(r.read())

def main():
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    for f in ["main.py", "db.py", "forecast.py"]:
        shutil.copy(os.path.join(SRC, f), WORK)
    shutil.copytree(os.path.join(SRC, "static"), os.path.join(WORK, "static"))
    # deliberately: no data/ directory, no sqlite file, no env vars
    proc = subprocess.Popen([PY, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", PORT],
                            cwd=WORK, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    results = []
    try:
        healthy = False
        for _ in range(60):
            time.sleep(0.5)
            if proc.poll() is not None:
                break
            try:
                s, body = get("/api/health")
                healthy = s == 200 and body.get("ok") is True and body.get("users", 0) > 0
                break
            except Exception:
                continue
        results.append(("server boots on a fresh clone and self-seeds", healthy))
        try:
            s, cat = get("/api/catalog")
            results.append(("catalog served", s == 200 and len(cat.get("trades", [])) == 11))
        except Exception as e:
            results.append(("catalog served", False))
        results.append(("data/sahkarsetu.db created on demand",
                        os.path.exists(os.path.join(WORK, "data", "sahkarsetu.db"))))
        # a real query after seeding (the old closed-connection bug made every request 500)
        try:
            req = urllib.request.Request(BASE + "/api/login", method="POST",
                                         data=json.dumps({"phone": "9000000001", "password": "demo123"}).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=8) as r:
                tok = json.loads(r.read()).get("token")
            results.append(("demo login works straight after seeding", bool(tok)))
        except Exception as e:
            results.append(("demo login works straight after seeding", False))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log = proc.stdout.read() if proc.stdout else ""
        shutil.rmtree(WORK, ignore_errors=True)

    bad = [n for n, ok in results if not ok]
    for n, ok in results:
        print(("  ✓ " if ok else "  ✗ ") + n)
    print(f"BOOT CHECK: {len(results) - len(bad)}/{len(results)} passed")
    if bad:
        print("server log tail:\n" + (log or "")[-800:])
        sys.exit(1)

if __name__ == "__main__":
    main()
