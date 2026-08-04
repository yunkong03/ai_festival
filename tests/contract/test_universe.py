from dart_corpus.contract.universe import UniverseLoader


def test_loads_70_companies_with_string_codes(corpus_root):
    companies = UniverseLoader(corpus_root).load()
    assert len(companies) == 70
    samsung = next(c for c in companies if c.corp_name == "삼성전자")
    assert samsung.corp_code == "00126380"
    assert isinstance(samsung.corp_code, str)
    assert samsung.stock_code == "005930"
    assert samsung.sector == "반도체·전자부품"
