from backend.app.database import ProductStatus
from backend.app.scrapers.computeralliance_v2_scraper import parse_computeralliance_listing
from backend.app.scrapers.centrecom_v2_scraper import parse_centrecom_listing, get_centrecom_next_page_url
from backend.app.scrapers.jw_v2_scraper import parse_jw_listing
from backend.app.scrapers.msy_v2_scraper import parse_msy_listing
from backend.app.scrapers.pccg_v2_scraper import (
    detect_pccg_product_layout,
    extract_pccg_subcategory_urls,
    parse_pccg_listing,
)
from backend.app.scrapers.scorptec_v2_scraper import parse_scorptec_listing
from backend.app.scrapers.shoppingexpress_v2_scraper import parse_shoppingexpress_listing, get_shoppingexpress_next_page_url
from backend.app.scrapers.umart_v2_scraper import parse_umart_listing, get_umart_max_page_url, get_umart_next_page_url
from backend.tests.fixture_utils import load_fixture_soup


def test_computeralliance_parser_contract_fixture():
    item = load_fixture_soup("scrapers", "computeralliance", "product_card.html").select_one(".product")
    snapshot = parse_computeralliance_listing(item, "https://www.computeralliance.com.au")

    assert snapshot is not None
    assert snapshot.name == "ASUS GeForce RTX 5070 PRIME OC 12GB"
    assert snapshot.url == "https://www.computeralliance.com.au/example-product"
    assert snapshot.image_url == "https://www.computeralliance.com.au/images/product.jpg"
    assert snapshot.price == 1299.0
    assert snapshot.status == ProductStatus.AVAILABLE


def test_shoppingexpress_parser_contract_fixture():
    item = load_fixture_soup("scrapers", "shoppingexpress", "product_card.html").select_one(".wrapper-thumbnail")
    snapshot = parse_shoppingexpress_listing(item, "https://www.shoppingexpress.com.au")

    assert snapshot is not None
    assert snapshot.name == "ASUS GeForce RTX 5070 DUAL OC 12GB"
    assert snapshot.url == "https://www.shoppingexpress.com.au/shop/asus-5070"
    assert snapshot.image_url == "https://www.shoppingexpress.com.au/img/example.jpg"
    assert snapshot.price == 1249.0
    assert snapshot.status == ProductStatus.AVAILABLE


def test_scorptec_parser_contract_fixture():
    item = load_fixture_soup("scrapers", "scorptec", "product_card.html").select_one(".product-list-detail")
    snapshot = parse_scorptec_listing(item, "https://www.scorptec.com.au")

    assert snapshot is not None
    assert snapshot.name == "ASUS GeForce RTX 5070 PRIME OC 12GB"
    assert snapshot.url == "https://www.scorptec.com.au/product/graphics-cards/nvidia/12345-asus-prime-5070"
    assert snapshot.image_url == "https://www.scorptec.com.au/img/scorptec.jpg"
    assert snapshot.price == 1279.0
    assert snapshot.status == ProductStatus.AVAILABLE


def test_jw_parser_contract_fixture():
    item = load_fixture_soup("scrapers", "jw", "product_card.html").select_one(".ais-InfiniteHits-item")
    snapshot = parse_jw_listing(item, "https://www.jw.com.au")

    assert snapshot is not None
    assert snapshot.name == "ASUS GeForce RTX 5070 DUAL OC 12GB"
    assert snapshot.url == "https://www.jw.com.au/product/asus-rtx5070-dual-oc"
    assert snapshot.image_url == "https://www.jw.com.au/images/jw-5070.jpg"
    assert snapshot.price == 1259.0
    assert snapshot.status == ProductStatus.AVAILABLE


def test_centrecom_parser_contract_fixture():
    item = load_fixture_soup("scrapers", "centrecom", "product_card.html").select_one(".prbox_box")
    snapshot = parse_centrecom_listing(item, "https://www.centrecom.com.au")

    assert snapshot is not None
    assert snapshot.name == "ASUS GeForce RTX 5070 DUAL OC 12GB"
    assert snapshot.url == "https://www.centrecom.com.au/asus-geforce-rtx-5070-dual-oc-12gb"
    assert snapshot.image_url == "https://www.centrecom.com.au/images/5070.jpg"
    assert snapshot.price == 1239.0
    assert snapshot.status == ProductStatus.AVAILABLE


def test_umart_parser_contract_fixture():
    item = load_fixture_soup("scrapers", "umart", "product_card.html").select_one(".goods_info")
    snapshot = parse_umart_listing(item, "https://www.umart.com.au")

    assert snapshot is not None
    assert snapshot.name == "ASUS GeForce RTX 5070 DUAL OC 12GB"
    assert snapshot.url == "https://www.umart.com.au/product/asus-rtx-5070-dual-oc"
    assert snapshot.image_url == "https://www.umart.com.au/images/5070.jpg"
    assert snapshot.price == 1229.0
    assert snapshot.status == ProductStatus.AVAILABLE


def test_msy_parser_contract_fixture():
    item = load_fixture_soup("scrapers", "msy", "product_card.html").select_one(".goods_info")
    snapshot = parse_msy_listing(item, "https://www.msy.com.au")

    assert snapshot is not None
    assert snapshot.name == "Corsair RM850x Shift 850W 80 Plus Gold Modular Power Supply"
    assert snapshot.url == "https://www.msy.com.au/product/corsair-rm850x-shift"
    assert snapshot.image_url == "https://www.msy.com.au/images/rm850x.jpg"
    assert snapshot.price == 239.0
    assert snapshot.status == ProductStatus.AVAILABLE


def test_pccg_parser_contract_fixture():
    item = load_fixture_soup("scrapers", "pccg", "product_card_layout1.html").select_one("[data-product-card-container]")
    snapshot = parse_pccg_listing(
        item,
        base_url="https://www.pccasegear.com",
        name_selector="[data-product-card-title] a",
        price_selector="[data-product-price-current]",
        image_selector="[data-product-card-image] img",
    )

    assert snapshot is not None
    assert snapshot.name == "ASUS GeForce RTX 5070 DUAL OC 12GB"
    assert snapshot.url == "https://www.pccasegear.com/products/99999/asus-geforce-rtx-5070-dual-oc-12gb"
    assert snapshot.image_url == "https://www.pccasegear.com/images/5070.jpg"
    assert snapshot.price == 1219.0
    assert snapshot.status == ProductStatus.AVAILABLE


def test_pccg_subcategory_contract_fixture():
    soup = load_fixture_soup("scrapers", "pccg", "category_page.html")
    urls = extract_pccg_subcategory_urls(soup, "https://www.pccasegear.com")

    assert urls == [
        "https://www.pccasegear.com/category/193/graphics-cards/nvidia-geforce-rtx-5070",
        "https://www.pccasegear.com/category/193/graphics-cards/nvidia-geforce-rtx-5080",
    ]


def test_pccg_layout_detection_contract_fixture():
    soup = load_fixture_soup("scrapers", "pccg", "product_page_layout2.html")
    items, layout = detect_pccg_product_layout(soup)

    assert items is not None
    assert len(items) == 1
    assert layout is not None
    assert layout["container_selector"] == ".product-container.list-view"
    assert layout["name_selector"] == ".product-title"


def test_shoppingexpress_next_page_contract_fixture():
    soup = load_fixture_soup("scrapers", "shoppingexpress", "category_page_with_next.html")
    next_page_url = get_shoppingexpress_next_page_url(
        soup,
        "https://www.shoppingexpress.com.au",
        "https://www.shoppingexpress.com.au/category?page=1",
    )

    assert next_page_url == "https://www.shoppingexpress.com.au/category?page=2"


def test_centrecom_next_page_contract_fixture():
    soup = load_fixture_soup("scrapers", "centrecom", "category_page_with_next.html")
    next_page_url = get_centrecom_next_page_url(
        soup,
        "https://www.centrecom.com.au",
        "https://www.centrecom.com.au/nvidia-amd-graphics-cards?page=1",
    )

    assert next_page_url == "https://www.centrecom.com.au/nvidia-amd-graphics-cards?page=2"


def test_umart_page_helpers_contract_fixture():
    soup = load_fixture_soup("scrapers", "umart", "category_page_with_page_size_and_next.html")
    max_page_url = get_umart_max_page_url(
        soup,
        "https://www.umart.com.au/pc-parts/computer-parts/cpu-processors-611",
        "https://www.umart.com.au/pc-parts/computer-parts/cpu-processors-611",
    )
    next_page_url = get_umart_next_page_url(
        soup,
        "https://www.umart.com.au",
        "https://www.umart.com.au/pc-parts/computer-parts/cpu-processors-611?pagesize=3",
    )

    assert max_page_url == "https://www.umart.com.au/pc-parts/computer-parts/cpu-processors-611?pagesize=3"
    assert next_page_url == "https://www.umart.com.au/pc-parts/computer-parts/cpu-processors-611?pagesize=3&page=2"
