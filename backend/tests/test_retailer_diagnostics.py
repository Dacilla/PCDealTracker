from backend.app.utils.browser_gate import detect_browser_gate
from backend.tests.fixture_utils import load_fixture_html
from scripts.retailer_diagnostics import (
    annotate_fallback_summary,
    build_arg_parser,
    describe_gate,
    extract_preview_rows_from_html,
    get_retailer_target,
    list_retailer_targets,
    main,
    should_retry_with_selenium,
    summarize_body_text,
)


def test_retailer_diagnostic_targets_cover_all_supported_retailers():
    targets = list_retailer_targets()

    assert [target.slug for target in targets] == [
        "centrecom",
        "computeralliance",
        "jw",
        "msy",
        "pccg",
        "scorptec",
        "shoppingexpress",
        "umart",
    ]


def test_extract_preview_rows_from_product_fixture_computeralliance():
    target = get_retailer_target("computeralliance")
    html = load_fixture_html("scrapers", "computeralliance", "product_card.html")

    preview = extract_preview_rows_from_html(html, target, preview_limit=1)

    assert preview == [
        {
            "position": 1,
            "name": "ASUS GeForce RTX 5070 PRIME OC 12GB",
            "href": "/example-product",
        }
    ]


def test_extract_preview_rows_from_product_fixture_centrecom():
    target = get_retailer_target("centrecom")
    html = f'<div class="product-grid">{load_fixture_html("scrapers", "centrecom", "product_card.html")}</div>'

    preview = extract_preview_rows_from_html(html, target, preview_limit=1)

    assert preview == [
        {
            "position": 1,
            "name": "ASUS GeForce RTX 5070 DUAL OC 12GB",
            "href": "/asus-geforce-rtx-5070-dual-oc-12gb",
        }
    ]


def test_extract_preview_rows_from_subcategory_fixture_pccg():
    target = get_retailer_target("pccg")
    html = load_fixture_html("scrapers", "pccg", "category_page.html")

    preview = extract_preview_rows_from_html(html, target, preview_limit=2)

    assert preview == [
        {
            "position": 1,
            "name": "RTX 5070",
            "href": "/category/193/graphics-cards/nvidia-geforce-rtx-5070",
        },
        {
            "position": 2,
            "name": "RTX 5080",
            "href": "/category/193/graphics-cards/nvidia-geforce-rtx-5080",
        },
    ]


def test_detect_browser_gate_detects_http_403_blocks():
    blocker = detect_browser_gate(
        "403 Forbidden",
        "<html><head><title>403 Forbidden</title></head><body><h1>403 Forbidden</h1></body></html>",
    )

    assert blocker == "http_403"
    assert describe_gate(blocker) == "The site returned HTTP 403 Forbidden to the automated browser."


def test_detect_browser_gate_detects_cloudflare_challenges():
    blocker = detect_browser_gate(
        "Just a moment...",
        """
        <html>
          <body>
            <h2>Performing security verification</h2>
            <input type="hidden" name="cf-turnstile-response" />
            <footer>Performance and Security by Cloudflare</footer>
          </body>
        </html>
        """,
    )

    assert blocker == "cloudflare_challenge"
    assert describe_gate(blocker) == "The site presented a Cloudflare bot or security challenge instead of the target page."


def test_summarize_body_text_flattens_markup():
    snippet = summarize_body_text("<div>Alpha</div><div>Beta Gamma</div>")

    assert snippet == "Alpha Beta Gamma"


def test_retailer_diagnostics_parser_accepts_profile_options():
    parser = build_arg_parser()
    args = parser.parse_args(
        [
            "--engine",
            "auto",
            "--retailer",
            "centrecom",
            "--headed",
            "--browser-channel",
            "chrome",
            "--user-data-dir",
            "tmp-profile",
            "--challenge-timeout-ms",
            "60000",
        ]
    )

    assert args.engine == "auto"
    assert args.retailer == "centrecom"
    assert args.headed is True
    assert args.browser_channel == "chrome"
    assert args.user_data_dir == "tmp-profile"
    assert args.challenge_timeout_ms == 60000


def test_should_retry_with_selenium_for_playwright_blocked_or_timeout():
    assert should_retry_with_selenium({"engine": "playwright", "status": "blocked"}) is True
    assert should_retry_with_selenium({"engine": "playwright", "status": "timeout"}) is True
    assert should_retry_with_selenium({"engine": "playwright", "status": "ok"}) is False
    assert should_retry_with_selenium({"engine": "selenium", "status": "blocked"}) is False


def test_annotate_fallback_summary_records_attempt_details():
    primary_summary = {
        "engine": "playwright",
        "status": "blocked",
        "blocker": "cloudflare_challenge",
        "summary_path": "playwright.json",
    }
    fallback_summary = {
        "engine": "selenium",
        "status": "ok",
        "summary_path": "selenium.json",
    }

    combined = annotate_fallback_summary(primary_summary, fallback_summary)

    assert combined["attempted_engines"] == ["playwright", "selenium"]
    assert combined["fallback_triggered"] is True
    assert combined["fallback_from_engine"] == "playwright"
    assert combined["fallback_from_status"] == "blocked"
    assert combined["fallback_from_blocker"] == "cloudflare_challenge"
    assert combined["fallback_from_summary_path"] == "playwright.json"


def test_manual_verification_requires_headed_mode():
    try:
        main(["--retailer", "centrecom", "--manual-verification"])
    except SystemExit as exc:
        assert str(exc) == "--manual-verification requires --headed so you can interact with the browser."
    else:
        raise AssertionError("Expected SystemExit for manual verification without headed mode.")
