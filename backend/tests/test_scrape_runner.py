from scripts.run_scraper import NATIVE_V2_SCRAPERS, build_arg_parser


def test_scrape_runner_parser_accepts_default_invocation():
    parser = build_arg_parser()
    args = parser.parse_args([])

    assert vars(args) == {}


def test_scrape_runner_batch_matches_current_native_retailer_set():
    assert len(NATIVE_V2_SCRAPERS) == 8
    assert {scraper.__name__ for scraper in NATIVE_V2_SCRAPERS} == {
        "run_computeralliance_v2_scraper",
        "run_shoppingexpress_v2_scraper",
        "run_scorptec_v2_scraper",
        "run_jw_v2_scraper",
        "run_centrecom_v2_scraper",
        "run_umart_v2_scraper",
        "run_msy_v2_scraper",
        "run_pccg_v2_scraper",
    }
