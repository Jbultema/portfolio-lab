"""Exercise completed research in a real browser, including mobile controls."""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://[::1]:8513/?workspace=combination")
parser.add_argument("--output", type=Path, default=Path("reports/browser-combination-20261126"))
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)


def settled(page):
    page.wait_for_function("!document.querySelector('[data-testid=\"stStatusWidget\"] button[title=\"Stop\"]')", timeout=90000)
    page.wait_for_timeout(300)
    assert not page.locator("[data-testid='stException']").count()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless=True)
    results = []
    for name, viewport in (("desktop", {"width": 1440, "height": 1000}), ("mobile", {"width": 390, "height": 844})):
        page = browser.new_page(viewport=viewport)
        errors = []
        page.on("pageerror", lambda error, target=errors: target.append(str(error)))
        page.goto(args.url)
        page.get_by_role("heading", name="Combination Lab", exact=True).wait_for(timeout=60000)
        page.locator(".js-plotly-plot .scatterlayer path.js-line").first.wait_for(timeout=60000)
        settled(page)
        assert page.locator(".js-plotly-plot .scatterlayer path.js-line").count() >= 10
        assert page.locator("[data-testid='stMetricValue']").evaluate_all("nodes => nodes.every(n => {const r=document.createRange();r.selectNodeContents(n);return r.getBoundingClientRect().width<=n.getBoundingClientRect().width+2;})")
        page.screenshot(path=str(args.output / f"{name}-core.png"), full_page=True)
        page.locator(".js-plotly-plot").first.scroll_into_view_if_needed()
        page.screenshot(path=str(args.output / f"{name}-core-chart.png"))
        for tab in ("Crisis & concentration", "Execution & outages", "Evidence"):
            page.get_by_role("tab", name=tab, exact=True).click()
            settled(page)
        page.get_by_role("tab", name="Performance", exact=True).click()
        window = page.get_by_role("combobox", name="Measurement window", exact=True)
        window.click()
        page.keyboard.press("Home")
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        settled(page)
        page.get_by_text("Conditional event probes", exact=True).click()
        page.get_by_role("combobox", name="Event policy", exact=True).wait_for(timeout=30000)
        settled(page)
        assert page.locator(".js-plotly-plot .scatterlayer path.js-line").count() >= 8
        page.screenshot(path=str(args.output / f"{name}-events.png"), full_page=True)
        page.locator(".js-plotly-plot").first.scroll_into_view_if_needed()
        page.screenshot(path=str(args.output / f"{name}-event-chart.png"))
        parent = page.get_by_role("combobox", name="Parent portfolio", exact=True)
        parent.click()
        page.keyboard.press("End")
        page.keyboard.press("Enter")
        settled(page)
        execution = page.get_by_role("combobox", name="Execution case", exact=True)
        execution.click()
        page.keyboard.press("End")
        page.keyboard.press("Enter")
        settled(page)
        assert page.locator(".js-plotly-plot .scatterlayer path.js-line").count() >= 8
        page.get_by_role("tab", name="Crisis & concentration", exact=True).click()
        settled(page)
        page.screenshot(path=str(args.output / f"{name}-event-stress.png"), full_page=True)
        page.get_by_role("tab", name="Evidence", exact=True).click()
        with page.expect_download() as received:
            page.get_by_role("button", name="Download performance", exact=True).click()
        received.value.save_as(args.output / f"{name}-performance.csv")
        assert not errors, errors
        results.append({"viewport": name, "errors": errors, "nonblank_equity_and_drawdown": True,
                        "scope_parent_window_stress_and_download": True, "no_document_overflow": True})
        page.close()
    browser.close()
    (args.output / "checks.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))
