"""Canonical Parser — 원본 파일 → DocumentIR. Chunk를 만들지 않는다.

★ 팀 승인 대기 계약(document_ir.py 상단 참고).

디스패치 규칙(요구사항 그대로):
  - 확장자/manifest.file_format만으로 파서를 고르지 않는다 — raw bytes를 먼저 읽고
    sniff.sniff_content_type()으로 실제 콘텐츠를 판별한 뒤에만 파서를 정한다.
  - dart3/dart4는 공통 traversal(_traverse_dart_element) 하나만 쓴다 — 실측(§검증4)
    결과 TD/TE 셀 태그 비중만 다르고 태그 어휘·구조 자체는 같아서, 유니온 셀태그
    집합으로 이미 대응되므로 schema-specific 분기를 넣지 않았다(넣을 이유가
    실측으로 확인되지 않음 — 필요해지면 이 파일에 분기 추가).
"""
from __future__ import annotations

import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from bs4 import BeautifulSoup

from dart_corpus.contract.manifest import DocumentRecord
from dart_corpus.contract.paths import resolve_corpus_path
from dart_corpus.parsing.document_ir import (
    DocumentIR, NodeKind, ParagraphIR, ParseQuality, ParserWarning, SectionIR,
    SourceFileIR, SourceLocation, TableCellIR, TableIR, WarningCode,
)
from dart_corpus.parsing.encoding import decode_with_fallback
from dart_corpus.parsing.ids import make_ir_node_id
from dart_corpus.parsing.section_builder import SectionStackBuilder
from dart_corpus.parsing.sniff import CONTENT_DART_XML, CONTENT_KIND_HTML, CONTENT_PDF, sniff_content_type
from dart_corpus.parsing.table_serializer import (
    compute_shape_diagnostics, detect_header_row_indices, expand_normalized_rows,
    extract_table_metadata, group_into_raw_rows, infer_consolidation_basis, shape_mismatch_warning,
)

logger = logging.getLogger(__name__)

_BARE_AMP = re.compile(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)")
_CLOSING_TAG_RE = re.compile(r"</([A-Z][A-Z0-9_-]*)>")
_SCHEMA_RE = re.compile(r'noNamespaceSchemaLocation="([^"]+)"')

# [실측, 파일럿 실행 중 발견] 순수 "다음 글자가 알파벳이면 real tag로 간주" 휴리스틱은
# 불충분함 — "<Manufacturing Excellence>"(소문자 섞임)뿐 아니라 "<IP 비즈니스>"(짧은
# 전대문자 단어+공백+한글)처럼 real tag처럼 보이는 장식용 꺾쇠도 실제 코퍼스에 존재
# (periodic_20260515002418, periodic_20251113001036 등, 240건 샘플 파일럿에서 발견).
# 해결: 이 문서에 실제로 등장하는 **닫는 태그 이름 집합**(</TITLE>, </P> 등)을 먼저
# 수집해서 화이트리스트로 쓴다 — real DART 태그는 반드시 짝이 맞는 닫는 태그가 어딘가
# 있고, 장식용 꺾쇠(<IP 비즈니스>, <Manufacturing Excellence>)는 애초에 안 닫히므로
# 이 집합에 없다.
def _build_known_tag_whitelist(text: str) -> set[str]:
    return set(_CLOSING_TAG_RE.findall(text))


def _make_bare_lt_pattern(known_tags: set[str]) -> re.Pattern:
    if known_tags:
        tag_alt = "|".join(re.escape(t) for t in sorted(known_tags, key=len, reverse=True))
        return re.compile(rf"<(?!/|!|\?|(?:{tag_alt})(?=[\s>/]))")
    return re.compile(r"<(?![A-Za-z/!?])")
_CELL_TAGS = {"TD", "TE", "TU", "TH"}
_STRIP_TAGS_RE = re.compile(r"<[^>]+>")


def sanitize_dart_xml(text: str) -> str:
    """bare '&'/'<' 이스케이프(실측 확인: 삼성전자 사업보고서에 649개, §검증).
    '<' 판별은 이 문서의 실제 닫는태그 화이트리스트 기반(위 주석 참고)."""
    fixed = _BARE_AMP.sub("&amp;", text)
    known_tags = _build_known_tag_whitelist(text)
    bare_lt_pattern = _make_bare_lt_pattern(known_tags)
    fixed = bare_lt_pattern.sub("&lt;", fixed)
    return fixed


def _strip_ns(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _cell_tag_of(elem: ET.Element) -> str:
    t = _strip_ns(elem.tag)
    return t if t in _CELL_TAGS else "TD"


class _TraversalContext:
    def __init__(self, doc_id: str, rel_path: str):
        self.doc_id = doc_id
        self.rel_path = rel_path
        self.order_index = 0
        self.section_stack = SectionStackBuilder()
        self.section_hierarchy: list[str] = []   # section_stack의 현재 스냅샷(paragraph/table이 참조)
        self.nodes: list = []
        self.warnings: list[ParserWarning] = []
        self.n_merged_cell_tables = 0

    def _next_id(self) -> str:
        node_id = make_ir_node_id(self.doc_id, self.rel_path, self.order_index)
        self.order_index += 1
        return node_id

    def emit_section(self, title_text: str):
        title_text = title_text.strip()
        own_order_index = self.order_index
        loc = SourceLocation(self.rel_path, own_order_index)
        node_id = self._next_id()
        section = SectionIR(node_id=node_id, title_text=title_text, source=loc, section_id=node_id)
        self.nodes.append(section)
        self.section_stack.push(section, own_order_index)
        if not section.level_confident:
            self.warnings.append(ParserWarning(
                self.doc_id, self.rel_path, WarningCode.UNKNOWN_SECTION_DEPTH, "info",
                f"section {node_id} title={title_text!r}: no recognized numbering pattern — "
                f"assumed sibling of current depth(level={section.level})",
            ))
        self.section_hierarchy = self.section_stack.current_hierarchy_titles()

    def close_all_sections(self):
        self.section_stack.close_all(self.order_index)

    def emit_paragraph(self, text: str):
        text = text.strip()
        if not text:
            return
        loc = SourceLocation(self.rel_path, self.order_index)
        is_footnote = text.startswith("※") or bool(re.match(r"^주\d*\)", text))
        self.nodes.append(ParagraphIR(
            node_id=self._next_id(), section_hierarchy=list(self.section_hierarchy),
            text=text, source=loc, is_footnote_like=is_footnote,
        ))

    def emit_table(self, cells: list[TableCellIR], embedded_title_text: str | None = None):
        loc = SourceLocation(self.rel_path, self.order_index)
        has_merge = any(c.rowspan > 1 or c.colspan > 1 for c in cells)

        raw_rows = group_into_raw_rows(cells)
        normalized_rows = expand_normalized_rows(raw_rows)
        header_row_indices = detect_header_row_indices(raw_rows)
        n_declared_cols, actual_col_counts = compute_shape_diagnostics(raw_rows)
        metadata = extract_table_metadata(embedded_title_text)
        consolidation_basis, consolidation_basis_reason = infer_consolidation_basis(self.section_hierarchy)

        node_id = self._next_id()

        if has_merge:
            self.n_merged_cell_tables += 1
            self.warnings.append(ParserWarning(
                self.doc_id, self.rel_path, WarningCode.TABLE_MERGED_CELL_IGNORED, "info",
                f"table {node_id} has merged cells (rowspan/colspan) — expanded into normalized_rows",
            ))
        shape_warn = shape_mismatch_warning(self.doc_id, self.rel_path, node_id, actual_col_counts, n_declared_cols)
        if shape_warn:
            self.warnings.append(shape_warn)
        if not metadata.title_confirmed or metadata.unit_text is None or metadata.period_text is None:
            self.warnings.append(ParserWarning(
                self.doc_id, self.rel_path, WarningCode.TABLE_METADATA_UNCERTAIN, "info",
                f"table {node_id}: title_confirmed={metadata.title_confirmed} "
                f"unit_text={metadata.unit_text!r} period_text={metadata.period_text!r} — "
                f"left None where not confidently extracted",
            ))

        self.nodes.append(TableIR(
            node_id=node_id, section_hierarchy=list(self.section_hierarchy), source=loc,
            raw_cells=cells, raw_rows=raw_rows, normalized_rows=normalized_rows,
            header_row_indices=header_row_indices, n_declared_cols=n_declared_cols,
            actual_col_counts=actual_col_counts,
            normalized_title_guess=metadata.title, title_confirmed=metadata.title_confirmed,
            unit_text=metadata.unit_text, period_text=metadata.period_text,
            consolidation_basis=consolidation_basis, consolidation_basis_reason=consolidation_basis_reason,
        ))


def _traverse_dart_element(elem: ET.Element, ctx: _TraversalContext) -> None:
    """dart3/dart4 공통 traversal. TITLE/TABLE-GROUP을 만나면 그 하위는 더 안 내려가고
    (이미 통째로 처리했으므로), 그 외 컨테이너 태그는 자식 순서대로 재귀한다."""
    tag = _strip_ns(elem.tag)

    if tag == "TITLE":
        ctx.emit_section("".join(elem.itertext()))
        return
    if tag == "TABLE-GROUP":
        # [실측, periodic_20240516000601/20231114001884] TABLE-GROUP은 직계 자식으로
        # TITLE을 가질 수 있다. ATOC="N"이면 순수 표 캡션(목차에 없음, 예: "채무증권
        # 발행실적") — section으로 승격하지 않는다. ATOC="Y"(또는 속성 없음)면 실제
        # section(예: "2-1. 연결 재무상태표")이라서 반드시 push해야 한다 — 안 그러면
        # 원문 TITLE 태그 수와 SectionIR 개수가 어긋난다(파일럿 실측: 93/240건에서 확인).
        embedded_title_elem = next(
            (c for c in elem if _strip_ns(c.tag) == "TITLE"), None,
        )
        caption_text = None
        if embedded_title_elem is not None:
            title_text = "".join(embedded_title_elem.itertext()).strip()
            if title_text:
                if embedded_title_elem.attrib.get("ATOC") == "N":
                    caption_text = title_text
                else:
                    ctx.emit_section(title_text)
                    caption_text = title_text
        cells = _extract_table_cells(elem)
        if cells:
            ctx.emit_table(cells, embedded_title_text=caption_text)
        return
    if tag == "TABLE":
        # TABLE-GROUP 밖에 단독으로 나오는 TABLE(드묾) — 그 자체를 표로 처리
        cells = _extract_table_cells(elem)
        if cells:
            ctx.emit_table(cells)
        return
    if tag == "P":
        ctx.emit_paragraph("".join(elem.itertext()))
        return

    for child in elem:
        _traverse_dart_element(child, ctx)


def _extract_table_cells(table_group_elem: ET.Element) -> list[TableCellIR]:
    cells: list[TableCellIR] = []
    rows = table_group_elem.findall(".//TR")
    for row_idx, row in enumerate(rows):
        col_idx = 0
        for child in row:
            tag = _strip_ns(child.tag)
            if tag not in _CELL_TAGS:
                continue
            text = "".join(child.itertext()).strip()
            rowspan = int(child.attrib.get("ROWSPAN", "1") or "1")
            colspan = int(child.attrib.get("COLSPAN", "1") or "1")
            cells.append(TableCellIR(row=row_idx, col=col_idx, text=text, rowspan=rowspan, colspan=colspan, tag=tag))
            col_idx += 1
    return cells


def parse_dart_xml_text(text: str, doc_id: str, rel_path: str) -> tuple[list, list[ParserWarning], bool]:
    """반환: (nodes, warnings, parsed_ok). parsed_ok=False면 호출자가 fallback 노드를 만든다."""
    warnings: list[ParserWarning] = []
    n_bare_amp = len(_BARE_AMP.findall(text))
    known_tags = _build_known_tag_whitelist(text)
    n_bare_lt = len(_make_bare_lt_pattern(known_tags).findall(text))
    sanitized = sanitize_dart_xml(text)
    if n_bare_amp or n_bare_lt:
        warnings.append(ParserWarning(
            doc_id, rel_path, WarningCode.SANITIZED_ENTITY, "info",
            f"sanitized {n_bare_amp} bare '&' and {n_bare_lt} bare '<' before XML parse",
        ))

    try:
        root = ET.fromstring(sanitized.encode("utf-8"))
    except ET.ParseError as exc:
        warnings.append(ParserWarning(
            doc_id, rel_path, WarningCode.PARSE_FAILED, "error",
            f"XML still not well-formed after sanitization: {exc}",
        ))
        return [], warnings, False

    ctx = _TraversalContext(doc_id, rel_path)
    _traverse_dart_element(root, ctx)
    ctx.close_all_sections()
    ctx.warnings = warnings + ctx.warnings
    return ctx.nodes, ctx.warnings, True


def parse_kind_html_text(text: str, doc_id: str, rel_path: str) -> tuple[list, list[ParserWarning]]:
    """KIND xforms HTML — BeautifulSoup(html.parser)는 malformed HTML에 관대해서
    (닫히지 않은 <meta> 등) 예외를 거의 안 낸다. 표 단위로 TableIR 생성(최소 구조:
    label/value 추정 없이 raw cell만 — 그건 Chunking/Facts 단계에서)."""
    warnings: list[ParserWarning] = []
    soup = BeautifulSoup(text, "html.parser")
    ctx = _TraversalContext(doc_id, rel_path)

    tables = soup.find_all("table")
    if not tables:
        warnings.append(ParserWarning(
            doc_id, rel_path, WarningCode.PARSE_FAILED, "warning", "no <table> found in KIND HTML document",
        ))

    for table in tables:
        cells: list[TableCellIR] = []
        rows = [tr for tr in table.find_all("tr") if tr.find_parent("table") is table]
        for row_idx, row in enumerate(rows):
            col_idx = 0
            for td in row.find_all("td", recursive=False):
                text_val = td.get_text(strip=True)
                rowspan = int(td.attrs.get("rowspan", 1) or 1)
                colspan = int(td.attrs.get("colspan", 1) or 1)
                cells.append(TableCellIR(row=row_idx, col=col_idx, text=text_val, rowspan=rowspan, colspan=colspan, tag="td"))
                col_idx += 1
        if cells:
            ctx.emit_table(cells)

    ctx.warnings = warnings + ctx.warnings
    return ctx.nodes, ctx.warnings


def _build_fallback_node(doc_id: str, rel_path: str, raw_text: str) -> ParagraphIR:
    """구조 파싱이 완전히 실패했을 때도 빈 문서를 반환하지 않는다 — 태그만 벗겨낸
    raw text 전체를 문단 1개로(검색은 되게)."""
    stripped = _STRIP_TAGS_RE.sub(" ", raw_text)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return ParagraphIR(
        node_id=make_ir_node_id(doc_id, rel_path, 0),
        section_hierarchy=[], text=stripped[:20000],   # 너무 크면 잘라냄(다음 단계에서 480토큰 청킹으로 다시 나뉨)
        source=SourceLocation(rel_path, 0), is_footnote_like=False,
    )


def parse_document(doc: DocumentRecord, corpus_root: Path) -> DocumentIR:
    """유일한 공개 진입점."""
    doc_dir = resolve_corpus_path(corpus_root, doc.file_path)
    warnings: list[ParserWarning] = []
    all_nodes: list = []
    source_files: list[SourceFileIR] = []

    if doc.file_format == "pdf+html":
        pdf_path = doc_dir / f"{doc.rcept_no}.pdf"
        viewer_path = doc_dir / f"{doc.rcept_no}_viewer.html"
        # PDF는 fallback/source artifact로만 보존(파싱 안 함) — viewer.html이 primary source
        source_files.append(SourceFileIR(
            rel_path=pdf_path.name, is_attachment=False, content_format=CONTENT_PDF,
            schema_version=None, content_sha256=_sha256_of(pdf_path),
            declared_encoding=None, actual_encoding_used="n/a(binary)",
        ))
        raw = viewer_path.read_bytes()
        decoded = decode_with_fallback(raw)
        content_type = sniff_content_type(raw)
        source_files.append(SourceFileIR(
            rel_path=viewer_path.name, is_attachment=False, content_format=content_type,
            schema_version=None, content_sha256=hashlib.sha256(raw).hexdigest(),
            declared_encoding=decoded.declared_encoding, actual_encoding_used=decoded.detected_encoding,
        ))
        if decoded.mismatch:
            warnings.append(ParserWarning(doc.doc_id, viewer_path.name, WarningCode.ENCODING_DECLARATION_MISMATCH,
                                           "warning", f"declared={decoded.declared_encoding} actual={decoded.detected_encoding}"))
        nodes, node_warnings = parse_kind_html_text(decoded.text, doc.doc_id, viewer_path.name)
        all_nodes.extend(nodes)
        warnings.extend(node_warnings)
        tier = "partial"   # viewer.html만 쓰고 원본 pdf 텍스트는 미추출이라 구조상 부분적
        schema_version = None
        parsed_ok = True
    else:
        xml_files = sorted(p for p in doc_dir.iterdir() if p.suffix.lower() == ".xml")
        parsed_ok = True
        schema_version = None
        for xml_path in xml_files:
            is_attachment = xml_path.stem != doc.rcept_no
            raw = xml_path.read_bytes()
            decoded = decode_with_fallback(raw)
            content_type = sniff_content_type(raw)

            if content_type == CONTENT_DART_XML:
                m = _SCHEMA_RE.search(decoded.text[:400])
                sv = m.group(1) if m else "unknown"
                if not is_attachment:
                    schema_version = sv
            else:
                sv = None

            source_files.append(SourceFileIR(
                rel_path=xml_path.name, is_attachment=is_attachment, content_format=content_type,
                schema_version=sv, content_sha256=hashlib.sha256(raw).hexdigest(),
                declared_encoding=decoded.declared_encoding, actual_encoding_used=decoded.detected_encoding,
            ))
            if decoded.mismatch:
                warnings.append(ParserWarning(doc.doc_id, xml_path.name, WarningCode.ENCODING_DECLARATION_MISMATCH,
                                               "warning", f"declared={decoded.declared_encoding} actual={decoded.detected_encoding}"))

            expected = CONTENT_DART_XML if doc.doc_group in {"periodic", "major", "holding"} else CONTENT_KIND_HTML
            if content_type != expected:
                warnings.append(ParserWarning(
                    doc.doc_id, xml_path.name, WarningCode.CONTENT_TYPE_MISMATCH, "warning",
                    f"doc_group={doc.doc_group} expected {expected} but sniffed {content_type}",
                ))

            if content_type == CONTENT_DART_XML:
                nodes, node_warnings, ok = parse_dart_xml_text(decoded.text, doc.doc_id, xml_path.name)
                if not ok:
                    parsed_ok = False
                    nodes = [_build_fallback_node(doc.doc_id, xml_path.name, decoded.text)]
            elif content_type == CONTENT_KIND_HTML:
                nodes, node_warnings = parse_kind_html_text(decoded.text, doc.doc_id, xml_path.name)
            else:
                node_warnings = [ParserWarning(doc.doc_id, xml_path.name, WarningCode.PARSE_FAILED, "error",
                                                f"unrecognized content type (sniff={content_type})")]
                nodes = [_build_fallback_node(doc.doc_id, xml_path.name, decoded.text)]
                parsed_ok = False

            all_nodes.extend(nodes)
            warnings.extend(node_warnings)

        tier = "structured" if parsed_ok and not any(w.code == WarningCode.SANITIZED_ENTITY for w in warnings) else (
            "fallback" if not parsed_ok else "partial"
        )

    quality = ParseQuality(
        tier=tier, schema_version=schema_version,
        n_sanitized_entities=sum(1 for w in warnings if w.code == WarningCode.SANITIZED_ENTITY),
        n_unresolved_section_depth=sum(1 for w in warnings if w.code == WarningCode.UNKNOWN_SECTION_DEPTH),
        n_tables_with_merged_cells=sum(1 for w in warnings if w.code == WarningCode.TABLE_MERGED_CELL_IGNORED),
        router_matched_expected_parser=not any(w.code == WarningCode.CONTENT_TYPE_MISMATCH for w in warnings),
    )
    return DocumentIR(doc_id=doc.doc_id, source_files=source_files, nodes=all_nodes, warnings=warnings, parse_quality=quality)


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
