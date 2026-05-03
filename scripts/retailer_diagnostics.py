from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from os import environ
from pathlib import Path
from typing import Optional

sys.path.append(str(Path(__file__).resolve().parents[1]))

import undetected_chromedriver as uc

from backend.app.scrapers.centrecom_v2_scraper import SCRAPE_TASKS as CENTRECOM_TASKS
from backend.app.scrapers.computeralliance_v2_scraper import SCRAPE_TASKS as COMPUTER_ALLIANCE_TASKS
from backend.app.scrapers.jw_v2_scraper import SCRAPE_TASKS as JW_TASKS
from backend.app.scrapers.msy_v2_scraper import SCRAPE_TASKS as MSY_TASKS
from backend.app.scrapers.pccg_v2_scraper import CATEGORY_URL_MAP as PCCG_CATEGORY_URL_MAP
from backend.app.scrapers.scorptec_v2_scraper import CATEGORY_URL_MAP as SCORPTEC_CATEGORY_URL_MAP
from backend.app.scrapers.shoppingexpress_v2_scraper import SCRAPE_TASKS as SHOPPING_EXPRESS_TASKS
from backend.app.scrapers.umart_v2_scraper import SCRAPE_TASKS as UMART_TASKS
from backend.app.scrapers.base_scraper import build_chrome_launch_kwargs
from backend.app.utils.browser_gate import (
    clean_browser_text,
    detect_browser_gate,
    summarize_browser_body_text,
)


def _task_url(tasks: list[dict], category_name: str) -> str:
    for task in tasks:
        if task["db_category"] == category_name:
            return task["url"]
    raise KeyError(f"No scrape task found for category {category_name!r}")


@dataclass(frozen=True)
class RetailerDiagnosticTarget:
    slug: str
    display_name: str
    start_url: str
    ready_selector: str
    primary_selector: str
    primary_label: str
    preview_name_selector: Optional[str] = None
    preview_link_selector: Optional[str] = None
    interaction: Optional[str] = None


RETAILER_TARGETS = {
    "computeralliance": RetailerDiagnosticTarget(
        slug="computeralliance",
        display_name="Computer Alliance",
        start_url=_task_url(COMPUTER_ALLIANCE_TASKS, "Graphics Cards"),
        ready_selector=".product",
        primary_selector=".product",
        primary_label="product_cards",
        preview_name_selector="a[data-pjax] h2.equalize",
        preview_link_selector="a[data-pjax]",
    ),
    "centrecom": RetailerDiagnosticTarget(
        slug="centrecom",
        display_name="Centre Com",
        start_url=_task_url(CENTRECOM_TASKS, "Graphics Cards"),
        ready_selector=".product-grid",
        primary_selector=".product-grid .prbox_box",
        primary_label="product_cards",
        preview_name_selector=".prbox_name",
        preview_link_selector="a.prbox_link",
    ),
    "jw": RetailerDiagnosticTarget(
        slug="jw",
        display_name="JW Computers",
        start_url=_task_url(JW_TASKS, "Graphics Cards"),
        ready_selector=".ais-InfiniteHits-list",
        primary_selector=".ais-InfiniteHits-item",
        primary_label="product_cards",
        preview_name_selector=".result-title",
        preview_link_selector="a.result",
        interaction="jw_load_more",
    ),
    "msy": RetailerDiagnosticTarget(
        slug="msy",
        display_name="MSY Technology",
        start_url=_task_url(MSY_TASKS, "Graphics Cards"),
        ready_selector=".category_section",
        primary_selector="ul#goods_sty > li.goods_info",
        primary_label="product_cards",
        preview_name_selector=".goods_name a",
        preview_link_selector=".goods_name a",
    ),
    "pccg": RetailerDiagnosticTarget(
        slug="pccg",
        display_name="PC Case Gear",
        start_url=PCCG_CATEGORY_URL_MAP["Graphics Cards"],
        ready_selector=".prdct_box_sec",
        primary_selector=".prdct_box a",
        primary_label="subcategory_links",
    ),
    "scorptec": RetailerDiagnosticTarget(
        slug="scorptec",
        display_name="Scorptec",
        start_url=SCORPTEC_CATEGORY_URL_MAP["Graphics Cards"],
        ready_selector=".category-wrapper",
        primary_selector=".grid-subcategory-title a",
        primary_label="subcategory_links",
    ),
    "shoppingexpress": RetailerDiagnosticTarget(
        slug="shoppingexpress",
        display_name="Shopping Express",
        start_url=_task_url(SHOPPING_EXPRESS_TASKS, "Graphics Cards"),
        ready_selector=".wrapper-row-thumbnail",
        primary_selector=".wrapper-thumbnail",
        primary_label="product_cards",
        preview_name_selector=".caption a",
        preview_link_selector=".caption a",
    ),
    "umart": RetailerDiagnosticTarget(
        slug="umart",
        display_name="Umart",
        start_url=_task_url(UMART_TASKS, "Graphics Cards"),
        ready_selector=".category_section",
        primary_selector="ul#goods_sty > li.goods_info",
        primary_label="product_cards",
        preview_name_selector=".goods_name a",
        preview_link_selector=".goods_name a",
    ),
}


def list_retailer_targets() -> list[RetailerDiagnosticTarget]:
    return [RETAILER_TARGETS[key] for key in sorted(RETAILER_TARGETS)]


def get_retailer_target(slug: str) -> RetailerDiagnosticTarget:
    return RETAILER_TARGETS[slug]


def _clean_text(text: str) -> str:
    return clean_browser_text(text)


def extract_preview_rows_from_html(
    html: str,
    target: RetailerDiagnosticTarget,
    *,
    preview_limit: int = 3,
) -> list[dict]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    rows = []

    for index, node in enumerate(soup.select(target.primary_selector)[:preview_limit], start=1):
        name = _clean_text(node.get_text(" ", strip=True))
        if target.preview_name_selector:
            name_element = node.select_one(target.preview_name_selector)
            if name_element is not None:
                name = _clean_text(name_element.get_text(" ", strip=True))

        href = None
        if target.preview_link_selector:
            link_element = node.select_one(target.preview_link_selector)
            if link_element is not None:
                href = link_element.get("href")
        elif getattr(node, "name", None) == "a":
            href = node.get("href")

        rows.append(
            {
                "position": index,
                "name": name,
                "href": href,
            }
        )

    return rows


def _build_output_stem(slug: str, now: datetime) -> str:
    return f"{slug}_{now.strftime('%Y%m%d_%H%M%S')}"


def summarize_body_text(html: str, *, limit: int = 240) -> str:
    return summarize_browser_body_text(html, limit=limit)


def describe_gate(blocker: str | None) -> str | None:
    if blocker == "cloudflare_challenge":
        return "The site presented a Cloudflare bot or security challenge instead of the target page."
    if blocker == "http_403":
        return "The site returned HTTP 403 Forbidden to the automated browser."
    if blocker == "access_denied":
        return "The site presented an access denied page to the automated browser."
    return None


def should_retry_with_selenium(summary: dict) -> bool:
    if summary.get("engine") != "playwright":
        return False
    return summary.get("status") in {"blocked", "timeout"}


def annotate_fallback_summary(primary_summary: dict, fallback_summary: dict) -> dict:
    combined_summary = dict(fallback_summary)
    combined_summary["attempted_engines"] = [
        primary_summary.get("engine"),
        fallback_summary.get("engine"),
    ]
    combined_summary["fallback_triggered"] = True
    combined_summary["fallback_from_engine"] = primary_summary.get("engine")
    combined_summary["fallback_from_status"] = primary_summary.get("status")
    combined_summary["fallback_from_blocker"] = primary_summary.get("blocker")
    combined_summary["fallback_from_summary_path"] = primary_summary.get("summary_path")
    return combined_summary


def resolve_selenium_browser_executable(browser_channel: Optional[str]) -> str | None:
    if browser_channel in (None, "chrome"):
        return uc.find_chrome_executable()

    if browser_channel != "msedge":
        return None

    candidates = []
    for env_var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base_dir = environ.get(env_var)
        if not base_dir:
            continue
        candidates.append(Path(base_dir) / "Microsoft" / "Edge" / "Application" / "msedge.exe")

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


async def _apply_retailer_interactions(page, target: RetailerDiagnosticTarget, *, max_interactions: int, delay_ms: int) -> int:
    if target.interaction != "jw_load_more":
        return 0

    clicks = 0
    for _ in range(max_interactions):
        button = page.locator(".ais-InfiniteHits-loadMore:not(.ais-InfiniteHits-loadMore--disabled)")
        if await button.count() == 0:
            break
        await button.first.click()
        clicks += 1
        await page.wait_for_timeout(delay_ms)
    return clicks


async def _maybe_wait_for_manual_verification(page, *, enabled: bool, settle_ms: int) -> None:
    if not enabled:
        return

    print("Manual verification mode enabled.")
    print("Complete any challenge in the open browser window, then press Enter here to continue capture.")
    await asyncio.to_thread(input)
    if settle_ms > 0:
        await page.wait_for_timeout(settle_ms)


async def _wait_for_gate_to_clear(page, target: RetailerDiagnosticTarget, *, timeout_ms: int, poll_ms: int = 1000) -> str | None:
    deadline = asyncio.get_running_loop().time() + (timeout_ms / 1000.0)

    while asyncio.get_running_loop().time() < deadline:
        title = await page.title()
        html = await page.content()
        blocker = detect_browser_gate(title, html)
        if blocker is None:
            return None

        if await page.locator(target.ready_selector).count() > 0:
            return None

        await page.wait_for_timeout(poll_ms)

    title = await page.title()
    html = await page.content()
    return detect_browser_gate(title, html)


def _maybe_wait_for_manual_verification_sync(*, enabled: bool, settle_ms: int) -> None:
    if not enabled:
        return

    print("Manual verification mode enabled.")
    print("Complete any challenge in the open browser window, then press Enter here to continue capture.")
    input()
    if settle_ms > 0:
        time.sleep(settle_ms / 1000)


def _wait_for_gate_to_clear_sync(driver, target: RetailerDiagnosticTarget, *, timeout_ms: int, poll_ms: int = 1000) -> str | None:
    from selenium.webdriver.common.by import By

    deadline = time.monotonic() + (timeout_ms / 1000.0)
    while time.monotonic() < deadline:
        blocker = detect_browser_gate(driver.title, driver.page_source)
        if blocker is None:
            return None

        if driver.find_elements(By.CSS_SELECTOR, target.ready_selector):
            return None

        time.sleep(poll_ms / 1000.0)

    return detect_browser_gate(driver.title, driver.page_source)


def _apply_retailer_interactions_sync(
    driver,
    target: RetailerDiagnosticTarget,
    *,
    max_interactions: int,
    delay_ms: int,
) -> int:
    from selenium.webdriver.common.by import By

    if target.interaction != "jw_load_more":
        return 0

    clicks = 0
    for _ in range(max_interactions):
        buttons = driver.find_elements(By.CSS_SELECTOR, ".ais-InfiniteHits-loadMore:not(.ais-InfiniteHits-loadMore--disabled)")
        if not buttons:
            break
        driver.execute_script("arguments[0].click();", buttons[0])
        clicks += 1
        time.sleep(delay_ms / 1000.0)
    return clicks


def run_retailer_diagnostic_with_selenium(
    target: RetailerDiagnosticTarget,
    *,
    output_dir: Path,
    headed: bool,
    browser_channel: Optional[str],
    user_data_dir: Optional[Path],
    manual_verification: bool,
    timeout_ms: int,
    challenge_timeout_ms: int,
    settle_ms: int,
    preview_limit: int,
    max_interactions: int,
    interaction_delay_ms: int,
) -> dict:
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC)
    stem = _build_output_stem(target.slug, started_at)
    html_path = output_dir / f"{stem}.html"
    screenshot_path = output_dir / f"{stem}.png"
    summary_path = output_dir / f"{stem}.json"

    status = "ok"
    error = None
    title = None
    primary_match_count = 0
    preview_rows: list[dict] = []
    interaction_count = 0
    final_url = target.start_url
    blocker = None
    blocker_detail = None
    body_text_snippet = ""
    browser_executable = resolve_selenium_browser_executable(browser_channel)

    if browser_channel == "msedge" and browser_executable is None:
        raise RuntimeError("Could not locate Microsoft Edge. Set SCRAPER_BROWSER_EXECUTABLE or use Chrome.")

    driver = None
    try:
        launch_kwargs = build_chrome_launch_kwargs(
            headless=not headed,
            user_data_dir=str(user_data_dir) if user_data_dir is not None else None,
            browser_executable=browser_executable,
        )
        driver = uc.Chrome(**launch_kwargs)
        driver.set_page_load_timeout(max(1, timeout_ms // 1000))
        driver.get(target.start_url)
        _maybe_wait_for_manual_verification_sync(
            enabled=manual_verification,
            settle_ms=settle_ms,
        )
        gate = detect_browser_gate(driver.title, driver.page_source)
        if gate is not None:
            print(
                f"Detected {gate} for {target.slug}. "
                f"Waiting up to {challenge_timeout_ms}ms for the page to clear automatically..."
            )
            _wait_for_gate_to_clear_sync(
                driver,
                target,
                timeout_ms=challenge_timeout_ms,
            )

        wait = WebDriverWait(driver, timeout_ms / 1000.0)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, target.ready_selector)))
        interaction_count = _apply_retailer_interactions_sync(
            driver,
            target,
            max_interactions=max_interactions,
            delay_ms=interaction_delay_ms,
        )
        if settle_ms > 0:
            time.sleep(settle_ms / 1000.0)

        title = driver.title
        final_url = driver.current_url
        html = driver.page_source
        html_path.write_text(html, encoding="utf-8")
        driver.save_screenshot(str(screenshot_path))
        primary_match_count = len(driver.find_elements(By.CSS_SELECTOR, target.primary_selector))
        preview_rows = extract_preview_rows_from_html(html, target, preview_limit=preview_limit)
        body_text_snippet = summarize_body_text(html)
    except TimeoutException as exc:
        status = "timeout"
        error = str(exc)
        if driver is not None:
            try:
                title = driver.title
                final_url = driver.current_url
                html = driver.page_source
                html_path.write_text(html, encoding="utf-8")
                driver.save_screenshot(str(screenshot_path))
                body_text_snippet = summarize_body_text(html)
            except Exception:
                pass
    except Exception as exc:
        status = "error"
        error = str(exc)
        if driver is not None:
            try:
                title = driver.title
                final_url = driver.current_url
                html = driver.page_source
                html_path.write_text(html, encoding="utf-8")
                driver.save_screenshot(str(screenshot_path))
                body_text_snippet = summarize_body_text(html)
            except Exception:
                pass
    finally:
        if driver is not None:
            driver.quit()

    captured_html = html_path.read_text(encoding="utf-8") if html_path.exists() else ""
    blocker = detect_browser_gate(title, captured_html)
    if blocker is not None:
        status = "blocked"
        blocker_detail = describe_gate(blocker)
        if error is None:
            error = blocker_detail
        if not body_text_snippet:
            body_text_snippet = summarize_body_text(captured_html)

    finished_at = datetime.now(UTC)
    summary = {
        "slug": target.slug,
        "display_name": target.display_name,
        "engine": "selenium",
        "status": status,
        "error": error,
        "http_status": None,
        "blocker": blocker,
        "blocker_detail": blocker_detail,
        "browser_channel": browser_channel,
        "browser_executable": browser_executable,
        "user_data_dir": str(user_data_dir) if user_data_dir is not None else None,
        "manual_verification": manual_verification,
        "start_url": target.start_url,
        "final_url": final_url,
        "title": title,
        "ready_selector": target.ready_selector,
        "primary_selector": target.primary_selector,
        "primary_label": target.primary_label,
        "primary_match_count": primary_match_count,
        "interaction": target.interaction,
        "interaction_count": interaction_count,
        "preview_rows": preview_rows,
        "body_text_snippet": body_text_snippet,
        "html_path": str(html_path),
        "screenshot_path": str(screenshot_path),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


async def run_retailer_diagnostic(
    target: RetailerDiagnosticTarget,
    *,
    output_dir: Path,
    headed: bool,
    browser_channel: Optional[str],
    user_data_dir: Optional[Path],
    manual_verification: bool,
    timeout_ms: int,
    challenge_timeout_ms: int,
    settle_ms: int,
    preview_limit: int,
    max_interactions: int,
    interaction_delay_ms: int,
) -> dict:
    try:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed. Run `venv\\Scripts\\pip install -r requirements.txt` and "
            "`venv\\Scripts\\playwright install chromium` first."
        ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC)
    stem = _build_output_stem(target.slug, started_at)
    html_path = output_dir / f"{stem}.html"
    screenshot_path = output_dir / f"{stem}.png"
    summary_path = output_dir / f"{stem}.json"

    status = "ok"
    error = None
    title = None
    primary_match_count = 0
    preview_rows: list[dict] = []
    interaction_count = 0
    final_url = target.start_url
    http_status: Optional[int] = None
    blocker = None
    blocker_detail = None
    body_text_snippet = ""

    browser = None
    context = None

    async with async_playwright() as playwright:
        try:
            if user_data_dir is not None:
                user_data_dir.mkdir(parents=True, exist_ok=True)
                context = await playwright.chromium.launch_persistent_context(
                    user_data_dir=str(user_data_dir),
                    channel=browser_channel,
                    headless=not headed,
                    viewport={"width": 1440, "height": 2200},
                )
                page = context.pages[0] if context.pages else await context.new_page()
            else:
                browser = await playwright.chromium.launch(
                    channel=browser_channel,
                    headless=not headed,
                )
                context = await browser.new_context(viewport={"width": 1440, "height": 2200})
                page = await context.new_page()

            goto_response = await page.goto(target.start_url, wait_until="domcontentloaded", timeout=timeout_ms)
            http_status = goto_response.status if goto_response is not None else None
            await _maybe_wait_for_manual_verification(
                page,
                enabled=manual_verification,
                settle_ms=settle_ms,
            )
            gate = detect_browser_gate(await page.title(), await page.content())
            if gate is not None:
                print(
                    f"Detected {gate} for {target.slug}. "
                    f"Waiting up to {challenge_timeout_ms}ms for the page to clear automatically..."
                )
                await _wait_for_gate_to_clear(
                    page,
                    target,
                    timeout_ms=challenge_timeout_ms,
                )
            await page.wait_for_selector(target.ready_selector, timeout=timeout_ms)
            interaction_count = await _apply_retailer_interactions(
                page,
                target,
                max_interactions=max_interactions,
                delay_ms=interaction_delay_ms,
            )
            if settle_ms > 0:
                await page.wait_for_timeout(settle_ms)

            title = await page.title()
            final_url = page.url
            html = await page.content()
            html_path.write_text(html, encoding="utf-8")
            await page.screenshot(path=str(screenshot_path), full_page=True)
            primary_match_count = await page.locator(target.primary_selector).count()
            preview_rows = extract_preview_rows_from_html(html, target, preview_limit=preview_limit)
            body_text_snippet = summarize_body_text(html)
        except PlaywrightTimeoutError as exc:
            status = "timeout"
            error = str(exc)
            try:
                title = await page.title()
                final_url = page.url
                html = await page.content()
                html_path.write_text(html, encoding="utf-8")
                await page.screenshot(path=str(screenshot_path), full_page=True)
                body_text_snippet = summarize_body_text(html)
            except Exception:
                pass
        except Exception as exc:
            status = "error"
            error = str(exc)
            try:
                title = await page.title()
                final_url = page.url
                html = await page.content()
                html_path.write_text(html, encoding="utf-8")
                await page.screenshot(path=str(screenshot_path), full_page=True)
                body_text_snippet = summarize_body_text(html)
            except Exception:
                pass
        finally:
            if context is not None:
                await context.close()
            if browser is not None:
                await browser.close()

    captured_html = html_path.read_text(encoding="utf-8") if html_path.exists() else ""
    blocker = detect_browser_gate(title, captured_html)
    if blocker is not None:
        status = "blocked"
        blocker_detail = describe_gate(blocker)
        if error is None:
            error = blocker_detail
        if not body_text_snippet:
            body_text_snippet = summarize_body_text(captured_html)

    finished_at = datetime.now(UTC)
    summary = {
        "slug": target.slug,
        "display_name": target.display_name,
        "engine": "playwright",
        "status": status,
        "error": error,
        "http_status": http_status,
        "blocker": blocker,
        "blocker_detail": blocker_detail,
        "browser_channel": browser_channel,
        "user_data_dir": str(user_data_dir) if user_data_dir is not None else None,
        "manual_verification": manual_verification,
        "start_url": target.start_url,
        "final_url": final_url,
        "title": title,
        "ready_selector": target.ready_selector,
        "primary_selector": target.primary_selector,
        "primary_label": target.primary_label,
        "primary_match_count": primary_match_count,
        "interaction": target.interaction,
        "interaction_count": interaction_count,
        "preview_rows": preview_rows,
        "body_text_snippet": body_text_snippet,
        "html_path": str(html_path),
        "screenshot_path": str(screenshot_path),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture live retailer pages for scraper diagnostics."
    )
    parser.add_argument(
        "--engine",
        default="auto",
        choices=["auto", "playwright", "selenium"],
        help="Browser automation engine to use. `auto` tries Playwright first, then Selenium on challenge/timeouts.",
    )
    parser.add_argument(
        "--retailer",
        default="all",
        choices=["all", *sorted(RETAILER_TARGETS)],
        help="Retailer slug to inspect, or `all` to run every configured target.",
    )
    parser.add_argument(
        "--output-dir",
        default="logs/playwright-diagnostics",
        help="Directory for HTML, screenshots, and JSON summaries.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run Chromium visibly instead of headless mode.",
    )
    parser.add_argument(
        "--browser-channel",
        default=None,
        choices=["chrome", "msedge"],
        help="Use an installed browser channel instead of bundled Chromium.",
    )
    parser.add_argument(
        "--user-data-dir",
        default=None,
        help="Persistent browser profile directory for cookie/session reuse.",
    )
    parser.add_argument(
        "--manual-verification",
        action="store_true",
        help="Pause after navigation so you can solve a challenge in a headed browser before capture continues.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=20_000,
        help="Navigation and selector wait timeout in milliseconds.",
    )
    parser.add_argument(
        "--challenge-timeout-ms",
        type=int,
        default=45_000,
        help="Extra wait time for self-clearing challenge pages before capture is treated as blocked.",
    )
    parser.add_argument(
        "--settle-ms",
        type=int,
        default=1_000,
        help="Additional wait after the page is ready before capture.",
    )
    parser.add_argument(
        "--preview-limit",
        type=int,
        default=3,
        help="How many matched nodes to summarize from the captured HTML.",
    )
    parser.add_argument(
        "--max-interactions",
        type=int,
        default=5,
        help="Maximum retailer-specific follow-up interactions, such as JW load-more clicks.",
    )
    parser.add_argument(
        "--interaction-delay-ms",
        type=int,
        default=2_000,
        help="Delay after each retailer-specific interaction.",
    )
    parser.add_argument(
        "--list-retailers",
        action="store_true",
        help="Print available retailer slugs and exit.",
    )
    return parser


async def _run_from_args(args) -> int:
    if args.list_retailers:
        for target in list_retailer_targets():
            print(f"{target.slug}: {target.display_name}")
        return 0

    targets = list_retailer_targets() if args.retailer == "all" else [get_retailer_target(args.retailer)]
    output_dir = Path(args.output_dir)
    user_data_dir = Path(args.user_data_dir).expanduser().resolve() if args.user_data_dir else None

    if args.manual_verification and not args.headed:
        raise SystemExit("--manual-verification requires --headed so you can interact with the browser.")

    exit_code = 0
    for target in targets:
        if args.engine == "selenium":
            summary = run_retailer_diagnostic_with_selenium(
                target,
                output_dir=output_dir,
                headed=args.headed,
                browser_channel=args.browser_channel,
                user_data_dir=user_data_dir,
                manual_verification=args.manual_verification,
                timeout_ms=args.timeout_ms,
                challenge_timeout_ms=args.challenge_timeout_ms,
                settle_ms=args.settle_ms,
                preview_limit=args.preview_limit,
                max_interactions=args.max_interactions,
                interaction_delay_ms=args.interaction_delay_ms,
            )
        elif args.engine == "playwright":
            summary = await run_retailer_diagnostic(
                target,
                output_dir=output_dir,
                headed=args.headed,
                browser_channel=args.browser_channel,
                user_data_dir=user_data_dir,
                manual_verification=args.manual_verification,
                timeout_ms=args.timeout_ms,
                challenge_timeout_ms=args.challenge_timeout_ms,
                settle_ms=args.settle_ms,
                preview_limit=args.preview_limit,
                max_interactions=args.max_interactions,
                interaction_delay_ms=args.interaction_delay_ms,
            )
        else:
            primary_summary = await run_retailer_diagnostic(
                target,
                output_dir=output_dir,
                headed=args.headed,
                browser_channel=args.browser_channel,
                user_data_dir=user_data_dir,
                manual_verification=args.manual_verification,
                timeout_ms=args.timeout_ms,
                challenge_timeout_ms=args.challenge_timeout_ms,
                settle_ms=args.settle_ms,
                preview_limit=args.preview_limit,
                max_interactions=args.max_interactions,
                interaction_delay_ms=args.interaction_delay_ms,
            )
            if should_retry_with_selenium(primary_summary):
                print(
                    f"Retrying {target.slug} with Selenium after "
                    f"{primary_summary['engine']} returned {primary_summary['status']}."
                )
                fallback_summary = run_retailer_diagnostic_with_selenium(
                    target,
                    output_dir=output_dir,
                    headed=args.headed,
                    browser_channel=args.browser_channel,
                    user_data_dir=user_data_dir,
                    manual_verification=args.manual_verification,
                    timeout_ms=args.timeout_ms,
                    challenge_timeout_ms=args.challenge_timeout_ms,
                    settle_ms=args.settle_ms,
                    preview_limit=args.preview_limit,
                    max_interactions=args.max_interactions,
                    interaction_delay_ms=args.interaction_delay_ms,
                )
                summary = annotate_fallback_summary(primary_summary, fallback_summary)
            else:
                summary = dict(primary_summary)
                summary["attempted_engines"] = [primary_summary.get("engine")]
                summary["fallback_triggered"] = False
        print(json.dumps(summary, indent=2))
        if summary["status"] != "ok":
            exit_code = 1
    return exit_code


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return asyncio.run(_run_from_args(args))


if __name__ == "__main__":
    raise SystemExit(main())
