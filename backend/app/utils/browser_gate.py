import re

from bs4 import BeautifulSoup


def clean_browser_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def summarize_browser_body_text(html: str, *, limit: int = 240) -> str:
    text = clean_browser_text(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    return text[:limit]


def detect_browser_gate(title: str | None, html: str) -> str | None:
    normalized_title = (title or "").strip().lower()
    normalized_html = html.lower()

    if (
        "cloudflare" in normalized_html
        and (
            normalized_title == "just a moment..."
            or "performing security verification" in normalized_html
            or "cf-turnstile-response" in normalized_html
        )
    ):
        return "cloudflare_challenge"

    if (
        normalized_title == "403 forbidden"
        or "<h1>403 forbidden</h1>" in normalized_html
        or "error code: 403" in normalized_html
    ):
        return "http_403"

    if "access denied" in normalized_title or "access denied" in normalized_html:
        return "access_denied"

    return None
