import pytest

from dart_corpus.contract.manifest import DocumentRecord
from dart_corpus.parsing.canonical_parser import parse_dart_xml_text, parse_document
from dart_corpus.parsing.document_ir import NodeKind, ParagraphIR, SectionIR, TableIR, WarningCode
from dart_corpus.parsing.section_builder import ROOT_SECTION_ID
from dart_corpus.parsing.sniff import CONTENT_DART_XML, CONTENT_KIND_HTML, CONTENT_PDF


def _doc(**overrides) -> DocumentRecord:
    base = dict(
        doc_id="periodic_00000000000000", corp_code="00000000", corp_name="테스트기업",
        listed_name="테스트", stock_code="000000", industry="IT", sector="테스트섹터",
        doc_group="periodic", doc_subtype="annual", derived_subtype="annual",
        report_nm="테스트보고서", rcept_no="00000000000000", rcept_dt="20260101",
        flr_nm="테스트", is_correction=False, file_path="raw/periodic/테스트기업/00000000000000",
        file_format="xml", n_files=1,
    )
    base.update(overrides)
    return DocumentRecord(**base)


# --- fixture: periodic dart3 ---
def test_periodic_dart3(corpus_root):
    doc = _doc(
        doc_id="periodic_20231114001884", corp_name="HD현대일렉트릭",
        rcept_no="20231114001884", file_path="raw/periodic/HD현대일렉트릭/20231114001884_quarter_2023_09",
    )
    ir = parse_document(doc, corpus_root)
    assert ir.parse_quality.schema_version == "dart3.xsd"
    assert any(isinstance(n, SectionIR) for n in ir.nodes)
    assert any(isinstance(n, TableIR) for n in ir.nodes)
    assert any(isinstance(n, ParagraphIR) for n in ir.nodes)


# --- fixture: periodic dart4 ---
def test_periodic_dart4(corpus_root):
    doc = _doc(
        doc_id="periodic_20241114001965", corp_name="HD현대일렉트릭",
        rcept_no="20241114001965", file_path="raw/periodic/HD현대일렉트릭/20241114001965_quarter_2024_09",
    )
    ir = parse_document(doc, corpus_root)
    assert ir.parse_quality.schema_version == "dart4.xsd"
    table_nodes = [n for n in ir.nodes if isinstance(n, TableIR)]
    assert len(table_nodes) > 0
    # dart4는 TE 셀 태그가 우세(§검증4 실측) — 적어도 하나는 TE 태그 셀이 있어야 함
    all_tags = {c.tag for t in table_nodes for c in t.raw_cells}
    assert "TE" in all_tags


# --- fixture: major dart3/dart4 ---
def test_major_dart3(corpus_root):
    doc = _doc(
        doc_id="major_20230601000234", doc_group="major", corp_name="한화오션",
        rcept_no="20230601000234", file_path="raw/major/한화오션/20230601000234",
    )
    ir = parse_document(doc, corpus_root)
    assert ir.parse_quality.schema_version == "dart3.xsd"


def test_major_dart4(corpus_root):
    doc = _doc(
        doc_id="major_20251219000396", doc_group="major", corp_name="JYP Ent",
        rcept_no="20251219000396", file_path="raw/major/JYP Ent/20251219000396",
    )
    ir = parse_document(doc, corpus_root)
    assert ir.parse_quality.schema_version == "dart4.xsd"


# --- fixture: holding dart3/dart4 ---
def test_holding_dart3(corpus_root):
    doc = _doc(
        doc_id="holding_20230103000123", doc_group="holding", corp_name="HD현대일렉트릭",
        rcept_no="20230103000123", file_path="raw/holding/HD현대일렉트릭/20230103000123",
    )
    ir = parse_document(doc, corpus_root)
    assert ir.parse_quality.schema_version == "dart3.xsd"


def test_holding_dart4(corpus_root):
    doc = _doc(
        doc_id="holding_20240717000432", doc_group="holding", corp_name="HD현대일렉트릭",
        rcept_no="20240717000432", file_path="raw/holding/HD현대일렉트릭/20240717000432",
    )
    ir = parse_document(doc, corpus_root)
    assert ir.parse_quality.schema_version == "dart4.xsd"


# --- fixture: exchange HTML-in-.xml + 잘못된 인코딩 선언 ---
def test_exchange_html_in_xml_with_encoding_mismatch(corpus_root):
    doc = _doc(
        doc_id="exchange_20230406800008", doc_group="exchange", corp_name="엘에스일렉트릭",
        rcept_no="20230406800008", file_path="raw/exchange/엘에스일렉트릭/20230406800008",
    )
    ir = parse_document(doc, corpus_root)
    assert ir.source_files[0].content_format == CONTENT_KIND_HTML   # 확장자는 .xml인데 실제론 HTML
    assert ir.source_files[0].declared_encoding == "euc-kr"
    assert ir.source_files[0].actual_encoding_used == "utf-8"
    assert any(w.code == WarningCode.ENCODING_DECLARATION_MISMATCH for w in ir.warnings)
    assert any(isinstance(n, TableIR) for n in ir.nodes)


# --- fixture: pdf+viewer.html ---
def test_pdf_viewer_html_uses_viewer_as_primary(corpus_root):
    doc = _doc(
        doc_id="periodic_20260513000860", corp_name="한화에어로스페이스",
        rcept_no="20260513000860", file_path="raw/periodic/한화에어로스페이스/20260513000860_quarter_2026_03",
        file_format="pdf+html", n_files=2,
    )
    ir = parse_document(doc, corpus_root)
    formats = {sf.rel_path: sf.content_format for sf in ir.source_files}
    assert formats["20260513000860.pdf"] == CONTENT_PDF
    assert formats["20260513000860_viewer.html"] == CONTENT_KIND_HTML
    # PDF는 파싱 안 하고 보존만 — 노드는 viewer.html에서만 나와야 함
    assert all(n.source.rel_path == "20260513000860_viewer.html" for n in ir.nodes if hasattr(n, "source") and n.source)
    assert len(ir.nodes) > 0   # viewer.html에서 최소 하나는 나옴


# --- fixture: malformed XML(합성, "mismatched tag" 유형). [정정, Partial-cause 분석
# 단계에서 재확인] periodic_20251114001959는 whitelist 기반 sanitizer 적용 후 실제로는
# 정상 파싱됨(ok=True) — 이전 세션 노트의 "이 문서가 mismatched-tag 실례"라는 메모는
# 틀렸음을 실측으로 확인. 코퍼스에 남아있는 실제 잔여 fallback 5건(예: 현대자동차
# periodic_20260515002418)은 전부 ENG="..." 속성값 내부에 이스케이프 안 된 큰따옴표가
# 원인이었다(tests/parsing/test_sanitizer_verification.py 참고) — mismatched tag가
# 아니었다. 여기 fixture는 순수 합성이며, 태그 이름 자체는 짝이 맞게 닫혀있어서(화이트리스트
# 기반 sanitizer로도 못 고치는) 구조적 크로스넥이 진짜 문제라는 걸 보여주는 용도로 유지) ---
def test_malformed_xml_falls_back_without_crashing():
    broken = "<?xml version=\"1.0\"?><DOCUMENT><P>텍스트<TABLE-GROUP></P></TABLE-GROUP></DOCUMENT>"
    nodes, warnings, ok = parse_dart_xml_text(broken, "synthetic_doc", "synthetic.xml")
    assert ok is False
    assert any(w.code == WarningCode.PARSE_FAILED for w in warnings)
    # canonical_parser.parse_document 레벨에서 fallback 노드가 만들어지는지는 실제 파일 필요 —
    # 여기서는 저수준 함수가 예외 없이 (빈 nodes, ok=False)를 반환하는 것만 확인
    assert nodes == []


# --- fixture: Section Builder + Table Serializer 실측 통합 검증
# (아모레퍼시픽 periodic_20240516000601, dart4 — partial-cause 분석에서 TABLE-GROUP
# 내장 TITLE 누락을 발견한 바로 그 문서) ---
def test_table_group_embedded_title_becomes_section_and_confirmed_table_title(corpus_root):
    doc = _doc(
        doc_id="periodic_20240516000601", corp_name="아모레퍼시픽",
        rcept_no="20240516000601", file_path="raw/periodic/아모레퍼시픽/20240516000601_quarter_2024_03",
    )
    ir = parse_document(doc, corpus_root)
    sections = [n for n in ir.nodes if isinstance(n, SectionIR)]
    by_title = {s.title_text: s for s in sections}

    assert "2. 연결재무제표" in by_title
    assert "2-1. 연결 재무상태표" in by_title   # TABLE-GROUP 내장 TITLE — 수정 전엔 누락됐음
    embedded = by_title["2-1. 연결 재무상태표"]
    parent = by_title["2. 연결재무제표"]
    assert embedded.level == 3
    assert embedded.parent_section_id == parent.section_id
    assert embedded.level_confident is True   # "2-1." 패턴은 확실하게 매치됨

    # ATOC="N" 캡션(예: "채무증권 발행실적")은 section으로 승격되지 않아야 한다
    assert "채무증권 발행실적" not in by_title

    tables_with_title = [n for n in ir.nodes if isinstance(n, TableIR) and n.normalized_title_guess == "2-1. 연결 재무상태표"]
    assert len(tables_with_title) >= 1
    assert tables_with_title[0].title_confirmed is True
    # 이 표는 실측상 TH 다수 행(컬럼 헤더)이 있음 — header_row_indices가 비어있지 않아야 함
    assert any(t.header_row_indices for t in tables_with_title)
    # section_hierarchy에 "2-1. 연결 재무상태표"가 있으므로 consolidation_basis="연결"로 채워져야 함
    assert tables_with_title[0].consolidation_basis == "연결"
    assert tables_with_title[0].consolidation_basis_reason is not None
    # 최상위 섹션의 parent는 가상 ROOT여야 한다
    assert by_title["III. 재무에 관한 사항"].parent_section_id == ROOT_SECTION_ID
