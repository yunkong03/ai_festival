"""Sanitizer 검증(항목 C) — 장식용 꺾쇠가 원문 그대로 살아남는지, sanitize 전후 텍스트/
숫자/표 셀이 손실되지 않는지, TITLE/P/TABLE-GROUP 개수가 변하지 않는지 확인한다.
"""
import re
import xml.etree.ElementTree as ET

from dart_corpus.parsing.canonical_parser import parse_dart_xml_text, sanitize_dart_xml

_TAG_COUNT_RE = {
    "TITLE": re.compile(r"</TITLE>"),
    "P": re.compile(r"</P>"),
    "TABLE-GROUP": re.compile(r"</TABLE-GROUP>"),
}


def _tag_counts(text: str) -> dict:
    return {name: len(rx.findall(text)) for name, rx in _TAG_COUNT_RE.items()}


# --- fixture: <Manufacturing Excellence>(실측: periodic_20260515002418 line 2914) ---
def test_decorative_bracket_manufacturing_excellence_preserved():
    xml = (
        '<?xml version="1.0"?><DOCUMENT><P>당사는 <Manufacturing Excellence> 전략을 '
        "추진한다.</P></DOCUMENT>"
    )
    nodes, warnings, ok = parse_dart_xml_text(xml, "doc", "rel.xml")
    assert ok is True
    text = nodes[0].text
    assert "<Manufacturing Excellence>" in text   # 이스케이프됐다가 itertext()에서 원래대로 복원돼야 함


# --- fixture: <IP 비즈니스>(실측: periodic_20251113001036) ---
def test_decorative_bracket_ip_business_preserved():
    xml = '<?xml version="1.0"?><DOCUMENT><P><IP 비즈니스> 영역을 확대한다.</P></DOCUMENT>'
    nodes, warnings, ok = parse_dart_xml_text(xml, "doc", "rel.xml")
    assert ok is True
    text = nodes[0].text
    assert "<IP 비즈니스>" in text


def test_sanitize_does_not_change_title_p_table_group_counts():
    xml = (
        '<?xml version="1.0"?><DOCUMENT><TITLE>1. 개요</TITLE>'
        '<P>매출 & 이익 <IP 비즈니스> 증가</P>'
        '<TABLE-GROUP><TR><TD>구분</TD><TD>1,234</TD></TR></TABLE-GROUP>'
        "</DOCUMENT>"
    )
    before = _tag_counts(xml)
    after = _tag_counts(sanitize_dart_xml(xml))
    assert before == after == {"TITLE": 1, "P": 1, "TABLE-GROUP": 1}


def test_sanitize_preserves_numbers_and_table_cell_text():
    xml = (
        '<?xml version="1.0"?><DOCUMENT>'
        '<P>Q&A 매출 1,234,567원 증가</P>'
        '<TABLE-GROUP><TR><TD>당기순이익</TD><TD>987,654</TD></TR></TABLE-GROUP>'
        "</DOCUMENT>"
    )
    nodes, warnings, ok = parse_dart_xml_text(xml, "doc", "rel.xml")
    assert ok is True
    all_text = "".join(getattr(n, "text", "") for n in nodes)
    all_text += "".join(c.text for n in nodes if hasattr(n, "raw_cells") for c in n.raw_cells)
    assert "1,234,567" in all_text
    assert "987,654" in all_text
    assert "당기순이익" in all_text


# --- fixture: 진짜 mismatched tag(합성이지만 실제 XML 규칙상 반드시 실패하는 크로스넥
# 구조 — bare &/< 문제가 아니라 태그 자체가 교차 중첩된 구조 오류) ---
def test_genuine_mismatched_tag_fails_even_with_perfect_sanitization():
    xml = '<?xml version="1.0"?><DOCUMENT><P>텍스트<TABLE-GROUP></P></TABLE-GROUP></DOCUMENT>'
    # sanitizer가 완벽하게 아무것도 안 건드려도(bare &/< 없음) 여전히 실패해야 한다 —
    # 이건 entity escaping으로 못 고치는 진짜 구조적 문제라는 걸 증명
    assert sanitize_dart_xml(xml) == xml
    nodes, warnings, ok = parse_dart_xml_text(xml, "doc", "rel.xml")
    assert ok is False


# --- fixture: 실제 코퍼스 잔여 fallback 사례(실측: 현대자동차 periodic_20260515002418) —
# "mismatched tag"가 아니라 ENG="..." 속성 안에 이스케이프 안 된 큰따옴표가 들어있는
# 경우였다(사전 가정이 틀렸음을 실측으로 확인 후 정정). 이번 단계 sanitizer는 태그/엔티티
# 레벨만 다루므로 속성값 내부 따옴표는 고치지 않는다 — fallback 유지가 맞는 판단임을
# 문서화하는 회귀 테스트.
def test_unescaped_quote_inside_attribute_value_is_not_fixed_by_current_sanitizer():
    xml = (
        '<?xml version="1.0"?><DOCUMENT><TABLE-GROUP><TR>'
        '<TE ENG=""Other receivables and others"" VALIGN="MIDDLE">미수금 등</TE>'
        "</TR></TABLE-GROUP></DOCUMENT>"
    )
    sanitized = sanitize_dart_xml(xml)
    # bare '&'도 없고, '<' 다음이 전부 실제 태그라서 sanitizer가 손댈 게 없다 — 그대로 통과
    assert sanitized == xml
    try:
        ET.fromstring(sanitized.encode("utf-8"))
        parsed_ok = True
    except ET.ParseError:
        parsed_ok = False
    assert parsed_ok is False   # 현재 구현은 이 케이스를 못 고침 — fallback 유지가 맞음(다음 단계 후보)
