"""Real-browser check of dynamic allocation controls and nonblank charts."""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

OUTPUT = Path("reports/browser-dynamic-20261126")
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--url", default="http://[::1]:8513/?workspace=dynamic")
URL = parser.parse_args().url


def settled(page):
    page.wait_for_function("!document.querySelector('[data-testid=\"stStatusWidget\"] button[title=\"Stop\"]')", timeout=90000)
    page.wait_for_timeout(400)
    assert not page.locator("[data-testid='stException']").count()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")


def select_value(page, label, value):
    combo = page.get_by_role("combobox", name=label, exact=True)
    combo.click()
    combo.fill(value)
    page.get_by_test_id("stSelectboxVirtualDropdown").get_by_text(value, exact=True).click()
    settled(page)
    assert page.get_by_role("combobox", name=label, exact=True).input_value() == value


OUTPUT.mkdir(parents=True, exist_ok=True)
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless=True)
    evidence = []
    for name, viewport in (("desktop", {"width": 1440, "height": 1000}), ("mobile", {"width": 390, "height": 844})):
        page = browser.new_page(viewport=viewport)
        errors = []
        page.on("pageerror", lambda error, target=errors: target.append(str(error)))
        page.goto(URL)
        page.get_by_role("heading", name="Dynamic Allocation Research", exact=True).wait_for(timeout=60000)
        page.locator(".js-plotly-plot .scatterlayer path.js-line").first.wait_for(timeout=90000)
        settled(page)
        assert page.locator(".js-plotly-plot .scatterlayer path.js-line").count() >= 8
        page.screenshot(path=str(OUTPUT / f"{name}-overview.png"))
        page.locator(".js-plotly-plot").first.scroll_into_view_if_needed()
        page.screenshot(path=str(OUTPUT / f"{name}-core-chart.png"))
        select_value(page, "Research policy", "r3_defensive_union")
        page.get_by_role("tab", name="Budgets & exposure", exact=True).click()
        settled(page)
        assert page.locator(".js-plotly-plot").count() >= 2
        page.screenshot(path=str(OUTPUT / f"{name}-budgets.png"))
        for tab in ("Crises & execution", "Selection & evidence"):
            page.get_by_role("tab", name=tab, exact=True).click()
            settled(page)
        page.get_by_role("tab", name="Performance", exact=True).click()
        page.get_by_text("Conditional event allocation", exact=True).click()
        settled(page)
        page.wait_for_function("document.querySelector('input[aria-label=\"Research policy\"]').value.includes('__')", timeout=30000)
        select_value(page, "Research policy", "event_conditioned_router__50__structural__liquidity_repair_h126")
        select_value(page, "Execution case", "5-session close fill / 50 bps per traded side")
        assert page.locator(".js-plotly-plot .scatterlayer path.js-line").count() >= 8
        page.locator(".js-plotly-plot").first.scroll_into_view_if_needed()
        page.screenshot(path=str(OUTPUT / f"{name}-event-stress.png"))
        page.get_by_role("tab", name="Selection & evidence", exact=True).click()
        with page.expect_download() as received:
            page.get_by_role("button", name="Download performance", exact=True).click()
        received.value.save_as(OUTPUT / f"{name}-performance.csv")
        assert not errors, errors
        evidence.append({"viewport": name, "errors": errors, "nonblank_equity_drawdown_and_budget_charts": True,
                         "controls_and_download": True, "no_document_overflow": True})
        page.close()
    browser.close()
(OUTPUT / "checks.json").write_text(json.dumps(evidence, indent=2) + "\n")
print(json.dumps(evidence, indent=2))
