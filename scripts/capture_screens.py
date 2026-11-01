"""Regenerate the docs screenshots from the live app (headless Chromium).

Start the backend (port 8000) and the frontend dev server (port 5173) first, then:

    python scripts/capture_screens.py

Writes docs/images/{dashboard-idle,dashboard-operations,dashboard-analytics,
map-fullscreen,settings,dashboard-final}.png at 1680x1050.
"""
import asyncio, os
import urllib.request
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:5173/"
API = "http://127.0.0.1:8000/api"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "images")


def post(path):
    try:
        urllib.request.urlopen(urllib.request.Request(f"{API}/{path}", method="POST"), timeout=10).read()
    except Exception as exc:  # the backend may already be in that state
        print(f"  (POST {path}: {exc})")


async def main():
    os.makedirs(OUT, exist_ok=True)
    post("simulation/stop")
    post("simulation/reset")

    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1680, "height": 1050}, device_scale_factor=1)
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))

        await pg.goto(BASE, wait_until="networkidle")
        await pg.wait_for_timeout(2000)
        await pg.screenshot(path=f"{OUT}/dashboard-idle.png")
        print("idle")

        # a full 120 s normal run, then stop so the analytics report is scored
        await pg.click("button:has-text('Start')")
        await pg.wait_for_timeout(20000)
        await pg.screenshot(path=f"{OUT}/dashboard-operations.png")
        print("operations")

        # map full screen
        await pg.click("button[title='Expand map']")
        await pg.wait_for_timeout(2500)
        await pg.screenshot(path=f"{OUT}/map-fullscreen.png")
        await pg.click("button:has-text('Exit')")
        await pg.wait_for_timeout(1200)

        # system drawer
        await pg.click("button:has-text('System')")
        await pg.wait_for_timeout(1600)
        await pg.screenshot(path=f"{OUT}/settings.png")
        await pg.keyboard.press("Escape")
        await pg.wait_for_timeout(700)

        await pg.wait_for_timeout(11000)
        await pg.click("button:has-text('Stop')")
        await pg.wait_for_timeout(7000)
        await pg.click("button:has-text('Analytics')")
        await pg.wait_for_timeout(3500)
        await pg.screenshot(path=f"{OUT}/dashboard-analytics.png")
        print("analytics")
        await pg.click("button:has-text('Operations')")
        await pg.wait_for_timeout(1200)
        await pg.screenshot(path=f"{OUT}/dashboard-final.png")
        print("final")

        print("page errors:", errs[:3])
        await b.close()


asyncio.run(main())
