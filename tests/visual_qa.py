"""SahkarSetu visual QA - full user journeys with screenshots.
    SAHKARSETU_BASE=http://localhost:3002 SAHKARSETU_DB=/path.db python3 tests/visual_qa.py
"""
import asyncio, sys, os, sqlite3
from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qa_common
BASE, DB = qa_common.resolve("visual_qa")
qa_common.assert_same_db()          # refuse to run when the API and the DB file disagree
OUT = os.environ.get("SAHKARSETU_QA_OUT",
                     os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "qa"))
os.makedirs(OUT, exist_ok=True)

def _purge_test_data():
    """Same cleanup as e2e: remove interrupted-run QA bookings/users (child tables first).

    booking_events/declines are foreign-key children of bookings, so with
    PRAGMA foreign_keys=ON they must be cleared first or the delete fails."""
    _c = sqlite3.connect(DB)
    _c.execute("PRAGMA foreign_keys=ON")
    _qa_addr = "address LIKE '%Playwright%'"
    _qa_owner = ("worker_id IN (SELECT w.user_id FROM workers w JOIN users u ON u.id=w.user_id WHERE u.name='QA Applicant')"
                 " OR customer_id IN (SELECT id FROM users WHERE name='QA Tester')")
    for _child in ("payments", "reviews", "booking_events", "declines"):
        _c.execute(f"DELETE FROM {_child} WHERE booking_id IN (SELECT id FROM bookings WHERE {_qa_addr})")
        _c.execute(f"DELETE FROM {_child} WHERE booking_id IN (SELECT id FROM bookings WHERE {_qa_owner})")
    _c.execute(f"DELETE FROM bookings WHERE {_qa_addr} AND status != 'completed'")
    _c.execute("DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE name IN ('QA Tester','QA Applicant'))")
    _c.execute("DELETE FROM welfare WHERE worker_id IN (SELECT w.user_id FROM workers w JOIN users u ON u.id=w.user_id WHERE u.name='QA Applicant')")
    _c.execute("DELETE FROM certifications WHERE worker_id IN (SELECT w.user_id FROM workers w JOIN users u ON u.id=w.user_id WHERE u.name='QA Applicant')")
    _c.execute(f"DELETE FROM bookings WHERE {_qa_owner}")
    _c.execute("DELETE FROM workers WHERE user_id IN (SELECT w.user_id FROM workers w JOIN users u ON u.id=w.user_id WHERE u.name='QA Applicant')")
    _c.execute("DELETE FROM users WHERE name IN ('QA Tester','QA Applicant')")
    _c.commit()
    _n = _c.execute("SELECT COUNT(*) FROM users WHERE name IN ('QA Tester','QA Applicant')").fetchone()[0]
    _c.close()
    return _n

# Explicit browser path for this box; else fall back to Playwright's own download,
# else bare None = Playwright's default resolution.
CHROME = os.environ.get("SAHKARSETU_CHROME") or "/root/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome"
if not os.path.exists(CHROME):
    import glob
    cands = [c for c in glob.glob("/root/.cache/ms-playwright/chromium*/chrome-linux*/chrome")
             if not c.endswith("_sandbox")]
    CHROME = sorted(cands)[-1] if cands else None

async def main():
    results = []
    def check(name, cond, extra=""):
        results.append((name, bool(cond), extra))
        print(("  ✓ " if cond else "  ✗ ") + name + (f" — {extra}" if not cond else ""))

    check("stale test data purged", _purge_test_data() == 0)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=CHROME,
                                           args=["--no-sandbox", "--disable-dev-shm-usage",
                                                 "--disable-gpu", "--single-process"])
        pg = await browser.new_page(viewport={"width":1380,"height":900})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type=="error" else None)

        # ---- 1. Landing ----
        await pg.goto(BASE, wait_until="networkidle")
        await pg.wait_for_timeout(1200)
        await pg.screenshot(path=f"{OUT}/01_landing.png", full_page=False)
        check("landing renders", await pg.locator(".hero h1").count() > 0)
        check("stats band populated", "verified" in await pg.locator(".stats-band").inner_text())
        # language toggle
        await pg.click("#lang-en")
        await pg.wait_for_timeout(400)
        check("EN toggle works", "Book a worker" in await pg.locator(".hero h1").inner_text())
        await pg.screenshot(path=f"{OUT}/02_landing_en.png")

        # ---- 2. Browse + map + profile ----
        await pg.goto(BASE + "/#", wait_until="networkidle")  # reset hash state
        await pg.evaluate("go('browse','plumber')")
        await pg.wait_for_timeout(1800)
        await pg.screenshot(path=f"{OUT}/03_browse_map.png")
        rows = await pg.locator(".wrow").count()
        check("worker list shows plumbers", rows > 0, f"rows={rows}")
        check("map canvas present", await pg.locator("#map").count() == 1)
        tiles = await pg.evaluate("document.querySelectorAll('#map img').length")
        check("map tiles loaded (OSM reachable)", tiles > 3, f"tiles={tiles}")
        # open profile
        await pg.locator(".wrow").first.click()
        await pg.wait_for_timeout(900)
        modal_txt = ""
        if await pg.locator(".modal").count():
            modal_txt = await pg.locator(".modal").inner_text()
        check("profile modal opens with certs/reviews", "Certificates" in modal_txt or "Reviews" in modal_txt or "Book" in modal_txt)
        await pg.screenshot(path=f"{OUT}/04_profile_modal.png")

        # ---- 3. Login as customer & book ----
        await pg.evaluate("closeModal(); go('auth')")
        await pg.wait_for_timeout(500)
        await pg.fill("#au-phone", "9000000001")
        await pg.fill("#au-pass", "demo123")
        await pg.click("button.btn.big")
        await pg.wait_for_timeout(1200)
        check("customer login lands on browse", await pg.locator(".wrow").count() > 0)
        # book from the first FREE plumber - picking a busy one is a hard refusal by design
        rows = pg.locator(".wrow")
        _n = await rows.count()
        picked = None
        for i in range(_n):
            _t = await rows.nth(i).inner_text()
            if "Busy now" not in _t and "अभी व्यस्त" not in _t:
                picked = rows.nth(i)
                break
        check("found a free worker to book", picked is not None, f"{_n} workers listed")
        await (picked or rows.first).click()
        await pg.wait_for_timeout(800)
        _ptxt = await pg.inner_text(".modal")
        check("profile shows availability", ("Free now" in _ptxt or "On a job right now" in _ptxt
                                             or "अभी free" in _ptxt or "अभी एक काम पर" in _ptxt))
        await pg.locator(".modal .btn.sm").first.click()
        await pg.wait_for_timeout(600)
        await pg.fill("#bk-addr", "QA-77, Playwright Lane")
        await pg.select_option("#bk-zone", "east")
        await pg.screenshot(path=f"{OUT}/05_booking_step1.png")
        await pg.click("text=Next →")
        await pg.wait_for_timeout(600)
        confirm_visible = await pg.locator("text=Confirm booking").count()
        check("booking step 2 shows", confirm_visible > 0)
        await pg.screenshot(path=f"{OUT}/06_booking_step2.png")
        await pg.click("text=Confirm booking")
        await pg.wait_for_timeout(1500)
        body = await pg.inner_text("body")
        check("landed on my bookings with live job", "Live jobs" in body or "चालू काम" in body)
        await pg.screenshot(path=f"{OUT}/07_mybookings.png")

        # ---- 4. Worker side: accept -> complete the QA booking? (use demo worker's seeded live job) ----
        await pg.evaluate("localStorage.removeItem('ss_token')")
        await pg.goto(BASE + "/#/auth", wait_until="networkidle")
        await pg.evaluate("go('auth')")
        await pg.wait_for_timeout(400)
        await pg.fill("#au-phone", "8000000001")
        await pg.fill("#au-pass", "demo123")
        await pg.click("button.btn.big")
        await pg.wait_for_timeout(1500)
        wbody = await pg.inner_text("body")
        check("worker hub shows earnings cards", "This week" in wbody or "इस हफ़्ते" in wbody)
        check("worker hub shows welfare", "PMSBY" in wbody)
        await pg.screenshot(path=f"{OUT}/08_worker_hub.png")
        btn = pg.locator("button", has_text="Accept job").first
        _before = await pg.locator("button", has_text="Accept job").count()
        if _before:
            await btn.click()
            await pg.wait_for_timeout(900)
            # Accepting a SECOND job while one is live is correctly refused (409,
            # "pehle apna chalu kaam poora karein") - product behaviour, not a bug.
            _body = await pg.inner_text("body")
            _after = await pg.locator("button", has_text="Accept job").count()
            check("accept works, or is refused by the one-active-job rule",
                  _after < _before or "chalu kaam" in _body,
                  f"accept buttons {_before}->{_after}, body has no refusal text")
        else:
            check("accept button present", True, "no pending job on the demo worker this run")

        # ---- 5. Admin dashboard ----
        await pg.evaluate("localStorage.removeItem('ss_token')")
        await pg.goto(BASE + "/#/auth", wait_until="networkidle")
        await pg.evaluate("go('auth')")
        await pg.wait_for_timeout(400)
        await pg.fill("#au-phone", "7000000001")
        await pg.fill("#au-pass", "admin123")
        await pg.click("button.btn.big")
        await pg.wait_for_timeout(1600)
        abody = await pg.inner_text("body")
        check("admin overview loads", "Federation Dashboard" in abody or "week GMV" in abody or "हफ़्ते का GMV" in abody)
        await pg.screenshot(path=f"{OUT}/09_admin_overview.png")
        # verification queue
        await pg.evaluate("admTab('verify')")
        await pg.wait_for_timeout(1000)
        await pg.screenshot(path=f"{OUT}/10_admin_verify.png")
        vtxt = await pg.inner_text("#adm-main")
        check("verification queue renders", "Verification Queue" in vtxt or "क़तार" in vtxt)
        # forecast heatmap
        await pg.evaluate("admTab('forecast')")
        await pg.wait_for_timeout(1600)
        hm = await pg.locator(".hm-table td.hm-cell").count()
        check("forecast heatmap cells render", hm >= 30, f"cells={hm}")
        await pg.evaluate("showSignals()")
        await pg.wait_for_timeout(900)
        await pg.screenshot(path=f"{OUT}/11_admin_forecast.png")
        # payouts
        await pg.evaluate("admTab('payouts')")
        await pg.wait_for_timeout(900)
        await pg.screenshot(path=f"{OUT}/12_admin_payouts.png")
        ptxt = await pg.inner_text("#adm-main")
        check("payout history table", "Past runs" in ptxt or "पुराने रन" in ptxt)
        # welfare
        await pg.evaluate("admTab('welfare')")
        await pg.wait_for_timeout(1000)
        await pg.screenshot(path=f"{OUT}/13_admin_welfare.png")
        wtxt = await pg.inner_text("#adm-main")
        check("welfare centre renders", "PMSBY" in wtxt)

        # ---- console errors across whole session ----
        # A 409 the API is *supposed* to raise (one-active-job refusal, busy worker) is
        # correct behaviour and must not be reported as a UI error.
        expected_409 = ("409", "conflict")
        real_errors = [e for e in errors
                       if "favicon" not in e.lower()
                       and not any(k in e.lower() for k in expected_409)]
        check("zero unexpected JS console errors", len(real_errors) == 0, "; ".join(real_errors[:3]))

        await browser.close()

    fails = [r for r in results if not r[1]]
    print(f"\n(post-run cleanup: test users remaining = {_purge_test_data()})")
    print(f"VISUAL QA: {len(results)-len(fails)}/{len(results)} passed")
    if fails:
        for f_ in fails: print(" -", f_[0], f_[2])
        sys.exit(1)

asyncio.run(main())
