import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

OUTPUT_PATH = Path("secrets/workday_state.json")
OUTPUT_PATH.parent.mkdir(exist_ok=True)


def parse_args() -> str:
    parser = argparse.ArgumentParser(description="Capture Workday authenticated session state")
    parser.add_argument(
        "--url",
        help="Workday URL to open (prefer the job posting or homepage that prompts login)",
        required=True,
    )
    args = parser.parse_args()
    return args.url


def main() -> None:
    target = parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto(target, wait_until="domcontentloaded", timeout=120000)
        except Exception as exc:
            print(f"Warning: navigation timeout ({exc}); please check the browser window.")
        print("Playwright opened the target page. Complete login/MFA and then press Enter...")
        input("Press Enter when the Workday dashboard or job form is visible")

        context.storage_state(path=str(OUTPUT_PATH))
        print(f"Authenticated storage state saved to {OUTPUT_PATH}")
        browser.close()


if __name__ == "__main__":
    main()
