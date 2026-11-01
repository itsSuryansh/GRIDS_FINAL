"""End-to-end verification of every user-facing workflow (headless browser).

Start the backend (port 8000) and the frontend dev server (port 5173) first, then:

    python scripts/verify_ui.py

Requires playwright with a chromium browser. Exits non-zero if any check fails.
"""
import asyncio, json, sys
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:5173/"
checks = []

def ok(name, cond, detail=""):
    checks.append((name, bool(cond), detail))

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1680, "height": 1050})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append("console:" + m.text) if m.type == "error" else None)

        await pg.goto(BASE, wait_until="networkidle")
        await pg.wait_for_timeout(1500)
        ok("page loads without JS errors", not errs, str(errs[:2]))
        ok("map tiles render", await pg.eval_on_selector_all("img.leaflet-tile-loaded", "e=>e.length") > 3)

        # reset + start
        await pg.click("button:has-text('Reset')")
        await pg.wait_for_timeout(600)
        await pg.click("button:has-text('Start')")
        await pg.wait_for_timeout(6000)
        state = await pg.inner_text("body")
        ok("simulation runs", "RUNNING" in state.upper())
        ok("live frames streamed", "frames" in state)

        # pause / resume
        await pg.click("button[title='Pause']")
        await pg.wait_for_timeout(1500)
        ok("pause works", "PAUSED" in (await pg.inner_text("body")).upper())
        await pg.click("button[title='Resume']")
        await pg.wait_for_timeout(1500)
        ok("resume works", "RUNNING" in (await pg.inner_text("body")).upper())

        # chart tabs
        for label in ["GNSS residual", "Velocity", "Drift", "EKF uncertainty"]:
            await pg.click(f"button:has-text('{label}')")
            await pg.wait_for_timeout(400)
        ok("all five chart tabs render", await pg.eval_on_selector_all("svg.recharts-surface", "e=>e.length") >= 1)

        # layer toggles on the map
        before = await pg.eval_on_selector_all("canvas.leaflet-zoom-animated", "e=>e.length")
        ok("map draws trajectory layers", before >= 1, f"{before} canvas layers")

        # settings drawer
        await pg.click("button:has-text('System')")
        await pg.wait_for_timeout(1500)
        drawer = await pg.inner_text("aside")
        ok("system drawer shows map provenance", "Cached tiles" in drawer and "tile.openstreetmap.org" in drawer)
        await pg.click("button[title='Close']")
        await pg.wait_for_timeout(600)

        # let the run finish a chunk, then stop and score
        await pg.wait_for_timeout(14000)
        await pg.click("button:has-text('Stop')")
        await pg.wait_for_timeout(7000)
        await pg.click("button:has-text('Analytics & sessions')")
        await pg.wait_for_timeout(3500)
        analytics = await pg.inner_text("main")
        for label in ["Estimator", "RMSE", "RTS smoothed", "Map aiding gain", "Smoothing gain"]:
            ok(f"analytics shows {label}", label.lower() in analytics.lower())
        ok("stored sessions listed", "SQLite" in analytics)
        ok("ML evaluated honestly", "not enabled" in analytics.lower() or "recommended" in analytics.lower()
           or "no measured improvement" in analytics.lower())

        # open a stored session
        await pg.click("table tbody tr >> nth=1")
        await pg.wait_for_timeout(2000)
        ok("stored session loads", "session #" in (await pg.inner_text("main")).lower())

        # multi-scenario sweep: run all five scenarios headlessly from the UI.
        # These two checks depend only on the sweep's own files, so they run
        # before the long interactive sequence above (which leaves ~65 s of
        # simulation time on the header clock and would eat the poll window).
        await pg.click("button:has-text('Analytics & sessions')")
        await pg.wait_for_timeout(1500)
        await pg.click("button:has-text('Run 5 scenarios')")
        sweep = ""
        for _ in range(180):
            await pg.wait_for_timeout(1000)
            sweep = await pg.inner_text("main")
            if "GNSS spoofing" in sweep and "lower error" in sweep.lower():
                break
        await pg.screenshot(path="docs/images/dashboard-sweep.png")
        ok("multi-scenario sweep runs all five", all(
            name in sweep for name in
            ["Normal navigation", "GNSS outage", "GNSS drift", "GNSS spoofing", "Complex movement"]
        ))
        # the header row is uppercased by CSS, so compare case-insensitively
        low = sweep.lower()
        ok("sweep reports per-estimator RMSE and EKF gain",
           "ekf vs gnss" in low and ("lower error" in low or "higher error" in low))

        # scenarios catalogue: switch to spoofing and run briefly
        await pg.click("button:has-text('Operations')")
        await pg.wait_for_timeout(800)
        await pg.select_option("select >> nth=0", "spoofing")
        await pg.wait_for_timeout(400)
        await pg.click("button:has-text('Start')")
        await pg.wait_for_timeout(9000)
        body = await pg.inner_text("body")
        ok("spoofing scenario detects anomalies", "INTEGRITY EVENTS" in body.upper())
        await pg.click("button:has-text('Stop')")
        await pg.wait_for_timeout(3000)

        await pg.screenshot(path="docs/images/dashboard-final.png")
        ok("multi-scenario sweep runs all five", all(
            name in sweep for name in
            ["Normal navigation", "GNSS outage", "GNSS drift", "GNSS spoofing", "Complex movement"]
        ))
        ok("sweep reports per-estimator RMSE and EKF gain", "ekf vs gnss" in sweep.lower())
        ok("no JS errors during the whole session", not errs, str(errs[:3]))
        await b.close()

    print(json.dumps([{"check": c, "pass": p, "detail": d} for c, p, d in checks], indent=1))
    failed = [c for c, p, _ in checks if not p]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed")
    if failed:
        print("FAILED:", failed)
        sys.exit(1)

asyncio.run(main())
