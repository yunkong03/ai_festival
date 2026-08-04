"""Canonical DocumentIR — Parser의 유일한 산출물(청크 아님).

★★★ 팀 승인 대기 중 ★★★
이 모듈의 타입들(`DocumentIR` 및 관련 dataclass)은 `workstream_a_documentir_contract.md`
설계 승인만 받은 상태이며, `interface_contract_draft.md`(팀 확정 계약)엔 아직
반영되지 않았다. 특히 `parse_quality`/`ChunkSet` 개념은 계약 갱신 요청 대상 —
그 문서 §3 표 참고. 이 타입을 소비하는 다른 Workstream(B/C) 코드를 작성하기 전에
반드시 팀 승인을 받을 것.

이 모듈은 원래 계획(`docs/superpowers/plans/2026-07-29-mvp-fact-store.md` Task 4)의
`ParsedDocument`(파싱과 동시에 Chunk를 만들던 타입, 한 번도 구현된 적 없음)를
**대체**한다 — `ParsedDocument`는 이 코드베이스에 실제로 존재한 적이 없으므로
"삭제"할 코드는 없지만, 그 계획 문서를 더 이상 구현 대상으로 참조하지 않는다는
뜻에서 이 사실을 명시적으로 남긴다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class NodeKind(str, Enum):
    SECTION = "section"
    TABLE = "table"
    PARAGRAPH = "paragraph"


@dataclass(frozen=True)
class SourceLocation:
    rel_path: str
    order_index: int
    byte_offset: int | None = None


@dataclass(frozen=True)
class SourceFileIR:
    rel_path: str
    is_attachment: bool
    content_format: str            # sniff.py의 CONTENT_* 값 — 실제 콘텐츠 기준(manifest.file_format 아님)
    schema_version: str | None      # "dart3.xsd" | "dart4.xsd" | None
    content_sha256: str
    declared_encoding: str | None
    actual_encoding_used: str


@dataclass
class SectionIR:
    """★계약 변경 필요(팀 승인 대기): section_id/parent_section_id/level/
    section_hierarchy/start_order_index/end_order_index는 Section Builder Phase에서
    신규 추가된 필드. end_order_index는 해당 섹션이 stack에서 닫힐 때(다음 형제/상위
    섹션 등장 또는 문서 끝) 사후에 채워지므로 frozen dataclass에서 mutable dataclass로
    변경했다(다른 필드는 기존과 동일)."""
    node_id: str
    kind: NodeKind = NodeKind.SECTION
    title_text: str = ""
    source: SourceLocation | None = None
    section_id: str = ""                      # = node_id (동일 값, 필드명 명시 요구사항 때문에 별도 보관)
    parent_section_id: str = "ROOT"            # 최상위 섹션의 부모는 문서마다 하나뿐인 가상 ROOT(노드로 만들지 않음)
    level: int = 1                              # 번호 패턴 기반 추정 레벨(1=로마숫자/대괄호, 2="N.", 3="N-M" ...)
    level_confident: bool = True                # False면 번호 패턴을 못 찾아 스택 깊이로 추정했다는 뜻(UNKNOWN_SECTION_DEPTH 경고 동반)
    section_hierarchy: list[str] = field(default_factory=list)   # 자기 자신 제외, 루트→직계부모 순
    start_order_index: int = 0
    end_order_index: int | None = None          # None이면 아직 안 닫힘(버그) — 문서 끝에서 항상 채워져야 함


@dataclass(frozen=True)
class TableCellIR:
    row: int
    col: int
    text: str
    rowspan: int = 1
    colspan: int = 1
    tag: str = "TD"          # 원본 셀 태그명 보존(dart3/dart4 TD·TE 비중 반전 대응, §검증4)


@dataclass(frozen=True)
class TableIR:
    """★계약 변경 필요(팀 승인 대기): raw_rows/normalized_rows/header_row_indices/
    n_declared_cols/actual_col_counts/title_confirmed/unit_text/period_text는
    Table Serializer Phase에서 신규 추가된 필드. title/unit/period는 "확실한 경우만"
    채우고, 불확실하면 None+ParserWarning(TABLE_METADATA_UNCERTAIN)만 남긴다(추측 금지)."""
    node_id: str
    kind: NodeKind = NodeKind.TABLE
    section_hierarchy: list[str] = field(default_factory=list)
    source: SourceLocation | None = None
    raw_cells: list[TableCellIR] = field(default_factory=list)
    raw_rows: list[list[TableCellIR]] = field(default_factory=list)     # raw_cells를 row 단위로 묶은 것(순서 보존)
    normalized_rows: list[list[str]] = field(default_factory=list)       # rowspan/colspan 확장한 직사각형 grid(text만)
    header_row_indices: list[int] = field(default_factory=list)          # TH 태그가 다수인 row index들(다중 header 지원)
    n_declared_cols: int | None = None          # 가장 흔한 row의 실제 컬럼 수(최빈값) — "선언된 컬럼 수" 대체 지표
    actual_col_counts: list[int] = field(default_factory=list)           # row별 실제 컬럼 수(shape mismatch 진단용)
    # 이번 단계는 "최소 구조만" — title/unit/period는 TABLE-GROUP에 함께 있는 TITLE처럼
    # "확실한" 소스가 있을 때만 채운다. 추정(guess)이 아니라 확인(confirmed)이므로 필드명은
    # 유지하되 title_confirmed로 출처를 명확히 구분한다.
    normalized_title_guess: str | None = None
    title_confirmed: bool = False
    unit_text: str | None = None
    period_text: str | None = None
    # section_hierarchy 기반 추론(table_serializer.infer_consolidation_basis) — "연결"/"별도"가
    # 계층 제목에서 명확할 때만 채운다. consolidation_basis_reason에 근거를 남기고, 불확실하면
    # 둘 다 None(추측 금지 — TableMetadata와 동일한 원칙).
    consolidation_basis: str | None = None
    consolidation_basis_reason: str | None = None


@dataclass(frozen=True)
class ParagraphIR:
    node_id: str
    kind: NodeKind = NodeKind.PARAGRAPH
    section_hierarchy: list[str] = field(default_factory=list)
    text: str = ""
    source: SourceLocation | None = None
    is_footnote_like: bool = False


DocumentNodeIR = SectionIR | TableIR | ParagraphIR


class WarningCode(str, Enum):
    SANITIZED_ENTITY = "sanitized_entity"
    ENCODING_DECLARATION_MISMATCH = "encoding_declaration_mismatch"
    UNKNOWN_SECTION_DEPTH = "unknown_section_depth"
    TABLE_MERGED_CELL_IGNORED = "table_merged_cell_ignored"
    ROUTER_FALLBACK_PARSER = "router_fallback_parser"
    CONTENT_TYPE_MISMATCH = "content_type_mismatch"   # sniff 결과가 doc_group 기대와 다름
    PARSE_FAILED = "parse_failed"
    TABLE_SHAPE_MISMATCH = "table_shape_mismatch"       # row별 실제 컬럼 수가 최빈값과 다름
    TABLE_METADATA_UNCERTAIN = "table_metadata_uncertain"   # title/unit/period를 확실하게 못 채움


@dataclass(frozen=True)
class ParserWarning:
    doc_id: str
    rel_path: str
    code: WarningCode
    severity: str    # "info" | "warning" | "error"
    message: str


@dataclass
class ParseQuality:
    tier: str                       # "structured" | "partial" | "fallback"
    schema_version: str | None
    n_sanitized_entities: int = 0
    n_unresolved_section_depth: int = 0
    n_tables_with_merged_cells: int = 0
    router_matched_expected_parser: bool = True


# DocumentIR JSON 직렬화 포맷 버전(parsing/serialization.py) — 필드 추가/의미 변경 시 올린다.
# canonical_parser.py의 파싱 로직 자체 버전과는 별개(같이 바뀌는 게 아님).
DOCUMENTIR_SCHEMA_VERSION = "1.0"
# canonical_parser.py 파싱 로직 버전 — 이 값이 바뀌면 같은 원본이라도 재파싱 결과가
# 달라질 수 있다는 뜻(디버깅/재현성 추적용, sanitize/traversal 규칙이 바뀔 때 올린다).
PARSER_VERSION = "1.0.0"


@dataclass
class DocumentIR:
    doc_id: str
    source_files: list[SourceFileIR] = field(default_factory=list)
    nodes: list[DocumentNodeIR] = field(default_factory=list)
    warnings: list[ParserWarning] = field(default_factory=list)
    parse_quality: ParseQuality = None
    schema_version: str = DOCUMENTIR_SCHEMA_VERSION
    parser_version: str = PARSER_VERSION
    corpus_snapshot_id: str | None = None   # Corpus Snapshot Phase 산출물과 연결(직렬화 시점에 채움)
