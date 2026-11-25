"""Optional real-browser smoke check against the locally running dashboard."""

import argparse
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
        page.goto(args.url)
        page.get_by_text("No action authorized", exact=False).wait_for(timeout=60000)
        page.locator(".js-plotly-plot").first.wait_for(timeout=60000)
        assert page.locator("[data-testid='stException']").count() == 0
        assert page.locator(".js-plotly-plot .scatterlayer path.js-line").count() >= 4
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 2")
        page.screenshot(path=str(args.output / f"{name}.png"), full_page=True)
        for tab in ("Allocation", "Overlap", "Execution", "Evidence"):
            page.get_by_role("tab", name=tab, exact=True).click()
            assert page.locator("[data-testid='stException']").count() == 0
        page.close()
    browser.close()
print("Desktop/mobile charts and all evidence tabs passed")
