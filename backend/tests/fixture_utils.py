from pathlib import Path

from bs4 import BeautifulSoup


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def load_fixture_html(*parts: str) -> str:
    return (FIXTURES_DIR.joinpath(*parts)).read_text(encoding="utf-8")


def load_fixture_soup(*parts: str) -> BeautifulSoup:
    return BeautifulSoup(load_fixture_html(*parts), "html.parser")
