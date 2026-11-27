"""Real-browser control-room and specialist-link regression checks."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://[::1]:8515")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless=True)
        for mode, viewport in (("desktop", {"width": 1440, "height": 1000}), ("mobile", {"width": 390, "height": 844})):
            page = browser.new_page(viewport=viewport)
            errors = []
            page.on("pageerror", lambda e, collected=errors: collected.append(str(e)))
            for view, heading in (("operations", "Daily Operations"), ("position", "Positioning Research"), ("event", "Fundamental Event Trader"), ("desk", "Market Interpretation Desk")):
                page.goto(args.url + "?workspace=" + view)
                page.get_by_role("heading", name=heading, exact=True).wait_for(timeout=90000)
                page.wait_for_function("!document.querySelector('[data-testid=\"stStatusWidget\"] button[title=\"Stop\"]')", timeout=90000)
                assert page.locator("[data-testid='stException']").count() == 0
                expand = page.get_by_role("button", name="Expand sidebar", exact=True)
                if expand.is_visible():
                    expand.click()
                assert page.get_by_role("button", name="Update all & publish", exact=True).count() == 1
                assert page.get_by_role("link", name="Trade Bot deep dive", exact=True).get_attribute("href") == "http://[::1]:8522"
                assert page.get_by_role("link", name="Position Bot", exact=True).get_attribute("href") == "http://[::1]:8516"
                collapse = page.get_by_role("button", name="Collapse sidebar", exact=True)
                if mode == "mobile" and collapse.is_visible():
                    collapse.click()
                    page.wait_for_timeout(400)
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 2")
                if view in {"position", "desk"}:
                    page.locator("canvas, .js-plotly-plot").first.wait_for(timeout=60000)
                page.screenshot(path=str(args.output / f"{mode}-{view}.png"), full_page=True)
                results.append({"viewport": mode, "workspace": view, "passed": True})
            assert not errors, errors
            page.close()
        for url, heading in (("http://[::1]:8522", ""), ("http://[::1]:8523", ""), ("http://[::1]:8524", ""), ("http://[::1]:8516", "Position Bot")):
            page = browser.new_page()
            page.goto(url)
            if heading:
                page.get_by_role("heading", name=heading, exact=True).wait_for(timeout=90000)
            page.wait_for_function("document.body.innerText.length > 100 || !!document.querySelector('[data-testid=\"stException\"]')", timeout=120000)
            page.wait_for_function("!document.querySelector('[data-testid=\"stStatusWidget\"] button[title=\"Stop\"]')", timeout=120000)
            page.wait_for_timeout(1500)
            assert page.locator("[data-testid='stException']").count() == 0, url
            assert len(page.locator("body").inner_text()) > 100, url
            page.screenshot(path=str(args.output / f"native-{url.rsplit(':', 1)[-1]}.png"))
            results.append({"native": url, "passed": True})
            page.close()
        browser.close()
    (args.output / "checks.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
