"""Optional real-browser smoke check against the locally running dashboard."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:8512")
parser.add_argument(
    "--chrome", default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
)
parser.add_argument("--output", type=Path, default=Path("reports/browser"))
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=args.chrome, headless=True)
    for name, viewport in (
        ("desktop", {"width": 1440, "height": 1000}),
        ("mobile", {"width": 390, "height": 844}),
    ):
        page = browser.new_page(viewport=viewport)
        errors = []
        page.on("pageerror", lambda error, target=errors: target.append(str(error)))
        page.goto(args.url)
        page.get_by_text("No action authorized", exact=False).wait_for(timeout=60000)
        page.locator(".js-plotly-plot").first.wait_for(timeout=60000)
        is_desk = page.get_by_role("heading", name="Market Interpretation Desk", exact=True).count()
        if is_desk:
            page.get_by_role("heading", name="Conditions that would change the view", exact=True).wait_for(timeout=60000)
        page.wait_for_function("!document.querySelector('[data-testid=\"stStatusWidget\"] button[title=\"Stop\"]')", timeout=90000)
        assert page.locator("[data-testid='stException']").count() == 0
        assert page.locator(".js-plotly-plot .scatterlayer path.js-line").count() >= 4
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 2")
        page.screenshot(path=str(args.output / f"{name}.png"), full_page=True)
        if page.get_by_role("heading", name="Market Interpretation Desk", exact=True).count():
            headings = {"Macro & cross-asset": "Cross-asset risk map", "News & events": "Financial News and Events", "Signals & bots": "Target-risk timeline", "Event research": "Fundamental Event Trader",
                        "Replay scorecard": "Did the stress flag distinguish subsequent damage?",
                        "Evidence": "Evidence ledger", "Portfolio research": "Portfolio Lab"}
            for view in ("Macro & cross-asset", "News & events", "Signals & bots", "Event research", "Replay scorecard", "Evidence", "Portfolio research"):
                toggle = page.get_by_role("button", name="Expand sidebar", exact=True)
                if toggle.is_visible():
                    toggle.click()
                page.get_by_text(view, exact=True).click()
                page.get_by_role("heading", name=headings[view], exact=True).wait_for(timeout=90000)
                page.wait_for_function("!document.querySelector('[data-testid=\"stStatusWidget\"] button[title=\"Stop\"]')", timeout=90000)
                page.wait_for_timeout(500)
                collapse = page.get_by_role("button", name="Collapse sidebar", exact=True)
                if name == "mobile" and collapse.is_visible():
                    collapse.click()
                    page.get_by_role("button", name="Expand sidebar", exact=True).wait_for(timeout=10000)
                    page.wait_for_timeout(600)
                assert page.locator("[data-testid='stException']").count() == 0
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 2")
                if view == "News & events":
                    page.get_by_role("heading", name="News source health", exact=True).wait_for(timeout=30000)
                    page.get_by_role("textbox", name="Search news", exact=True).fill("zz_no_story_matches_this_fixture_zz")
                    page.get_by_role("textbox", name="Search news", exact=True).press("Enter")
                    page.get_by_text("No stories match these filters.", exact=True).wait_for(timeout=30000)
                    page.get_by_role("textbox", name="Search news", exact=True).fill("")
                    page.get_by_role("textbox", name="Search news", exact=True).press("Enter")
                    page.get_by_text("Article body read", exact=False).first.wait_for(timeout=30000)
                    page.get_by_text("Article bodies read only", exact=True).click()
                    page.wait_for_function("!document.querySelector('[data-testid=\"stStatusWidget\"] button[title=\"Stop\"]')", timeout=30000)
                    page.get_by_text("Headline / feed summary only", exact=False).first.wait_for(state="hidden", timeout=30000)
                    assert page.get_by_text("Article body read", exact=False).count() > 0
                    page.get_by_text("Article bodies read only", exact=True).click()
                    page.get_by_role("heading", name="Financial News and Events", exact=True).evaluate("node => node.scrollIntoView({block: 'center'})")
                    page.screenshot(path=str(args.output / f"{name}-news-reader.png"))
                    toggle = page.get_by_role("button", name="Expand sidebar", exact=True)
                    if toggle.is_visible():
                        toggle.click()
                    session = page.get_by_role("combobox", name="Session close", exact=True)
                    session.click()
                    page.keyboard.press("End")
                    page.keyboard.press("Enter")
                    page.get_by_text("Current news is withheld from historical sessions.", exact=False).wait_for(timeout=30000)
                    assert page.get_by_role("heading", name="News source health", exact=True).count() == 0
                    session.click()
                    page.keyboard.press("Home")
                    page.keyboard.press("Enter")
                    page.get_by_role("heading", name="News source health", exact=True).wait_for(timeout=30000)
                    collapse = page.get_by_role("button", name="Collapse sidebar", exact=True)
                    if name == "mobile" and collapse.is_visible():
                        collapse.click()
                        page.wait_for_timeout(600)
                    page.get_by_role("heading", name="News source health", exact=True).evaluate("node => node.scrollIntoView({block: 'center'})")
                    page.screenshot(path=str(args.output / f"{name}-news-sources.png"))
                if view == "Macro & cross-asset":
                    page.get_by_text("CURRENT VINTAGE ONLY.", exact=False).wait_for(timeout=60000)
                    assert page.locator(".js-plotly-plot .heatmaplayer image").count() == 2
                    page.get_by_role("heading", name="Economic read-through", exact=True).scroll_into_view_if_needed()
                    page.screenshot(path=str(args.output / f"{name}-macro-cycles.png"))
                    if name == "mobile":
                        page.get_by_role("button", name="Expand sidebar", exact=True).click()
                    session = page.get_by_role("combobox", name="Session close", exact=True)
                    session.click()
                    page.keyboard.press("End")
                    page.keyboard.press("Enter")
                    page.get_by_text("Current-vintage macro is withheld", exact=False).wait_for(timeout=90000)
                    assert page.get_by_text("CURRENT VINTAGE ONLY.", exact=False).count() == 0
                    session.click()
                    page.keyboard.press("Home")
                    page.keyboard.press("Enter")
                    page.get_by_text("CURRENT VINTAGE ONLY.", exact=False).wait_for(timeout=90000)
                    if name == "mobile":
                        page.get_by_role("button", name="Collapse sidebar", exact=True).click()
                        page.get_by_role("button", name="Expand sidebar", exact=True).wait_for(timeout=10000)
                        page.wait_for_timeout(600)
                    page.get_by_role("heading", name="Cross-asset risk map", exact=True).scroll_into_view_if_needed()
                if view == "Evidence":
                    with page.expect_download() as received:
                        page.get_by_role("button", name="Download fact pack", exact=True).click()
                    destination = args.output / f"{name}-facts.json"
                    received.value.save_as(destination)
                    pack = json.loads(destination.read_text())
                    assert pack["authority"] == "interpretation_only" and pack["facts"]
                if view == "Replay scorecard":
                    with page.expect_download() as received:
                        page.get_by_role("button", name="Download research readout", exact=True).click()
                    destination = args.output / f"{name}-readout.md"
                    received.value.save_as(destination)
                    text = destination.read_text()
                    assert "Market close:" in text and "## Model positioning" in text
                    assert "## Current Financial News" in text
                    if (args.output / f"{name}-event.png").exists():
                        assert "| Content family |" in text and "Prospective evidence:" in text
                if view == "Event research":
                    page.get_by_role("heading", name="What has actually been tested", exact=True).wait_for(timeout=30000)
                    page.get_by_role("heading", name="Prospective evidence", exact=True).wait_for(timeout=30000)
                    assert page.locator("[data-testid='stMetricValue']").evaluate_all("nodes => nodes.every(n => {const r = document.createRange(); r.selectNodeContents(n); return r.getBoundingClientRect().width <= n.getBoundingClientRect().width + 2;})")
                    toggle = page.get_by_role("button", name="Expand sidebar", exact=True)
                    if toggle.is_visible():
                        toggle.click()
                    session = page.get_by_role("combobox", name="Session close", exact=True)
                    session.click()
                    page.keyboard.press("End")
                    page.keyboard.press("Enter")
                    page.get_by_text("Current event research targets and completed research outcomes are withheld", exact=False).wait_for(timeout=30000)
                    assert not page.get_by_role("heading", name="Prospective evidence", exact=True).count()
                    session.click()
                    page.keyboard.press("Home")
                    page.keyboard.press("Enter")
                    page.get_by_role("heading", name="Prospective evidence", exact=True).wait_for(timeout=30000)
                    collapse = page.get_by_role("button", name="Collapse sidebar", exact=True)
                    if name == "mobile" and collapse.is_visible():
                        collapse.click()
                        page.wait_for_timeout(600)
                    page.get_by_role("heading", name="What has actually been tested", exact=True).evaluate("node => node.scrollIntoView({block: 'center'})")
                    page.screenshot(path=str(args.output / f"{name}-event-families.png"))
                    page.get_by_role("heading", name="Prospective evidence", exact=True).evaluate("node => node.scrollIntoView({block: 'center'})")
                    page.screenshot(path=str(args.output / f"{name}-event-prospective.png"))
                page.screenshot(path=str(args.output / f"{name}-{view.split()[0].lower()}.png"), full_page=True)
        for tab in ("Allocation", "Overlap", "Execution", "Evidence"):
            page.get_by_role("tab", name=tab, exact=True).click()
            assert page.locator("[data-testid='stException']").count() == 0
        assert not errors, errors
        page.close()
    browser.close()
print("Desktop/mobile charts and all evidence tabs passed")
