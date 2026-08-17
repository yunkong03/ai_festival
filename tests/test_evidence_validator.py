"""Evidence Validation — 생성된 주장과 원문 대조."""
from __future__ import annotations

from dart_detective.agents import validator

SOURCES = [{
    "document_id": "D02",
    "document_date": "2023-05-15",
    "title": "분기보고서 (2023.03)",
    "text": "현금및현금성자산 | 239,036,839,774 | 320,363,496,754\n"
            "부채총계 | 2,581,553,023,711",
    "score": 10.0,
}]


def _v(answer: str, citations=None):
    return validator.validate(answer, citations or [], SOURCES)


def test_verbatim_quote_and_number_is_supported():
    result = _v(
        "현금및현금성자산은 239,036,839,774원이다.",
        [{"document_id": "D02", "quote_or_fact": "현금및현금성자산 | 239,036,839,774 | 320,363,496,754"}],
    )
    assert result["status"] == "SUPPORTED"


def test_judgment_word_without_source_is_partially_supported():
    """공시: 현금성자산 2,390억 / 생성: '회사는 현금이 부족하다' -> unsupported inference."""
    result = _v("회사는 현금이 부족하다.")
    assert result["status"] == "PARTIALLY_SUPPORTED"
    check = next(c for c in result["checks"] if c["check"] == "no_unsupported_inference")
    assert "부족" in check["inferences"]


def test_fabricated_number_is_unsupported():
    result = _v("현금및현금성자산은 999,999,999,999원이다.")
    assert result["status"] == "UNSUPPORTED"
    check = next(c for c in result["checks"] if c["check"] == "numbers_grounded")
    assert check["fabricated"] == ["999999999999"]


def test_quote_not_in_source_is_unsupported():
    result = _v("자료에 따르면 그렇다.",
                [{"document_id": "D02", "quote_or_fact": "이 문장은 어떤 공시에도 없다"}])
    assert result["status"] == "UNSUPPORTED"


def test_quote_attributed_to_wrong_document_is_partial():
    sources = SOURCES + [{
        "document_id": "D01", "document_date": "2023-05-23", "title": "신규시설투자등",
        "text": "2. 투자내역 | 투자금액(원) | 473,200,000,000", "score": 9.0,
    }]
    result = validator.validate(
        "투자금액은 473,200,000,000원이다.",
        [{"document_id": "D02", "quote_or_fact": "2. 투자내역 | 투자금액(원) | 473,200,000,000"}],
        sources,
    )
    assert result["status"] == "PARTIALLY_SUPPORTED"


def test_unit_conversion_of_won_amount_is_allowed():
    result = validator.validate(
        "투자금액은 약 4,732억원이다.", [],
        [{"document_id": "D01", "document_date": "2023-05-23", "title": "t",
          "text": "2. 투자내역 | 투자금액(원) | 473,200,000,000", "score": 1.0}],
    )
    assert result["status"] == "SUPPORTED"


def test_unsupported_year_is_flagged():
    result = _v("2026년 기준 현금및현금성자산은 239,036,839,774원이다.")
    assert result["status"] == "PARTIALLY_SUPPORTED"
    check = next(c for c in result["checks"] if c["check"] == "period_grounded")
    assert "2026" in check["unsupported_years"]
