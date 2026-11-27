"""Real-browser system scorecard and market desk checks at desktop/mobile sizes."""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--url", required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)


def settled(page):
    page.wait_for_function("!document.querySelector('[data-testid=\"stStatusWidget\"] button[title=\"Stop\"]')", timeout=120000)
    page.wait_for_timeout(500)
    assert not page.locator("[data-testid='stException']").count()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")


def select(page, label, value):
    control = page.get_by_role("combobox", name=label, exact=True)
    control.click()
    control.fill(value)
    page.get_by_test_id("stSelectboxVirtualDropdown").get_by_text(value, exact=True).click()
    settled(page)
    assert control.input_value() == value


results = []
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless=True)
    for name, size in (("desktop", {"width": 1440, "height": 1000}), ("mobile", {"width": 390, "height": 844})):
        page = browser.new_page(viewport=size)
        errors = []
        page.on("pageerror", lambda e, output=errors: output.append(str(e)))
        page.goto(args.url + "/?workspace=system")
        page.get_by_role("heading", name="System Scorecard", exact=True).wait_for(timeout=60000)
        page.locator(".js-plotly-plot .scatterlayer path.js-line").first.wait_for(timeout=120000)
        settled(page)
        assert page.locator(".js-plotly-plot .scatterlayer path.js-line").count() >= 10
        page.screenshot(path=str(args.output / f"{name}-overview.png"))
        page.locator(".js-plotly-plot").first.scroll_into_view_if_needed()
        page.screenshot(path=str(args.output / f"{name}-growth.png"))
        select(page, "Parent strategy", "Native risk-repair challenger")
        select(page, "Risk rule", "Confirmed / 252 sessions / guard replaced")
        select(page, "Trading cost per side", "50 bp")
        select(page, "Fill delay", "3 sessions")
        select(page, "Historical window", "2019 onward")
        for tab in ("Specialists", "Forecast Record", "Release Health", "Performance"):
            page.get_by_role("tab", name=tab, exact=True).click()
            settled(page)
        with page.expect_download() as download:
            page.get_by_role("button", name="Performance data", exact=True).click()
        download.value.save_as(args.output / f"{name}-performance.csv")
        page.goto(args.url + "/")
        page.get_by_role("heading", name="Market Interpretation Desk", exact=True).wait_for(timeout=90000)
        page.locator(".js-plotly-plot .scatterlayer path.js-line").first.wait_for(timeout=90000)
        settled(page)
        page.screenshot(path=str(args.output / f"{name}-desk.png"))
        assert not errors, errors
        results.append({"viewport": name, "nonblank_data_charts": True, "all_scorecard_tabs": True,
            "cost_delay_parent_rule_controls": True, "download": True,
            "fresh_market_desk": True, "horizontal_overflow": False, "page_errors": errors})
        page.close()
    browser.close()
(args.output / "checks.json").write_text(json.dumps(results, indent=2) + "\n")
print(json.dumps(results, indent=2))
