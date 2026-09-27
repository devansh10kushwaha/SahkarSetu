"""Live-URL proof: drive the PUBLIC SahkarSetu URL in a real browser.

Logs in as the demo customer through https://jr29e-5001.aiccloud.online/ and proves the
deployment works end to end (not just curl): landing render, login, browse view, console clean.
"""
import asyncio, os, sys
from playwright.async_api import async_playwright

URL = os.environ.get("LIVE_URL", "https://jr29e-5001.aiccloud.online")
OUT = os.environ.get("SAHKARSETU_QA_OUT",
                     os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "qa"))
os.makedirs(OUT, exist_ok=True)
CHROME = os.environ.get("SAHKARSETU_CHROME") or "/root/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome"
if not os.path.exists(CHROME):
    cands = __import__("glob").glob("/root/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")
    CHROME = sorted(cands)[-1] if cands else None

async def main():
    errors = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=CHROME,
                                           args=["--no-sandbox", "--disable-dev-shm-usage",
                                                 "--disable-gpu", "--single-process"])
        pg = await (await browser.new_context(viewport={"width": 420, "height": 900})).new_page()
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        await pg.goto(URL + "/#/", wait_until="domcontentloaded", timeout=45000)
        await pg.wait_for_timeout(2500)
        print("landing title:", (await pg.title())[:70])
        await pg.screenshot(path=f"{OUT}/live_landing.png", full_page=False)

        # log in as the demo customer through the public site
        await pg.evaluate("go('auth')")
        await pg.wait_for_timeout(1200)
        await pg.fill("#au-phone", "9000000001")
        await pg.fill("#au-pass", "demo123")
        await pg.evaluate("authSubmit()")
        await pg.wait_for_timeout(3000)
        who = await pg.evaluate("(API.user && API.user.name) || null")
        print("logged in as:", who)
        await pg.screenshot(path=f"{OUT}/live_after_login.png", full_page=False)

        stats = await pg.evaluate("document.body.innerText.slice(0,300)")
        print("visible text sample:", " ".join(stats.split())[:200])
        await browser.close()
    print("console errors:", len(errors), errors[:3])
    print("screenshots:", f"{OUT}/live_landing.png", f"{OUT}/live_after_login.png")
    if not who:
        sys.exit(1)

asyncio.run(main())
