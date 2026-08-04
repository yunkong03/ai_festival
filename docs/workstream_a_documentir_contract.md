# Workstream A — Canonical DocumentIR 계약 확정판

> `workstream_a_documentir_design.md`의 §2/§3(DocumentIR 초안)을 이 문서가 **대체(확정)**한다.
> 나머지 섹션(§1 corpus snapshot, §4-11)은 그 문서가 여전히 유효한 출처. 이번에도 구현 없음 —
> 타입/직렬화/ID규칙/fixture만 확정.

## 0. 검증으로 갱신된 사실 (설계에 반영됨)

- `file_format="xml"`은 "내용이 XML"이 아니라 "`.xml` 확장자 파일 있음"만 의미 — exchange는 예외 없이 HTML 콘텐츠
- exchange의 `charset=euc-kr` 선언은 **거짓** — 항상 utf-8로 강제 디코딩(선언 무시)
- dart3/dart4는 TD/TE 셀 태그 비중이 뒤집히지만 유니온 처리로 이미 대응 가능(변경 불요)
- 본문/첨부는 파일명 stem==rcept_no 여부로 결정적으로 판별 가능
- **content hash가 스냅샷/IR 어디에도 없다 — 이번 설계에서 추가**(`SourceFileIR.content_sha256`)

---

## 1. Parser 공통 산출물 vs Chunking 산출물 — 명확히 분리

```
raw XML/HTML 파일
      │
      ▼
CanonicalParser.parse(doc) -> DocumentIR      # ★ 여기가 Parser의 유일한 산출물. 청크 없음.
      │
      ▼  (여러 개 가능: whole_table 전략, row_table 전략, paragraph_480tok 전략 ...)
ChunkingStrategy.apply(DocumentIR) -> ChunkSet   # ★ 청킹은 여기서만. 전략 여러 개가 같은 IR을 재사용.
```

**DocumentIR은 청킹 전략과 무관하게 항상 하나다.** 같은 문서를 whole-table로도, row-table로도 청킹하고 싶으면 DocumentIR을 한 번만 만들고 `ChunkingStrategy`만 바꿔서 두 번 돌린다 — 재파싱 없음. 이게 §이전 리포트 §0에서 지적한 "파싱=청킹 미분리" 문제의 실제 해법.

---

## 2. 타입 정의

```python
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


# --- 4. SourceLocation ---
@dataclass(frozen=True)
class SourceLocation:
    rel_path: str          # 예: "20250311001085.xml" 또는 "20250311001085_00760.xml"(첨부)
    order_index: int        # 그 rel_path 파일 안에서 문서 순서(0부터), §3 ID규칙의 근거값
    byte_offset: int | None = None   # 선택, 디버깅용


# --- SourceFileIR (신규) ---
@dataclass(frozen=True)
class SourceFileIR:
    rel_path: str
    is_attachment: bool          # stem == rcept_no 이면 False(본문), 아니면 True — §검증6 확정 규칙
    content_format: str           # "dart_xml" | "kind_html" | "pdf" (실제 콘텐츠 기준, file_format 아님 — §검증1 구분)
    schema_version: str | None    # "dart3.xsd" | "dart4.xsd" | None(kind_html/pdf)
    content_sha256: str           # ★신규(§검증7 gap 대응) — 재파싱 캐시 무효화/변경감지용
    declared_encoding: str | None   # 파일이 주장하는 인코딩(예: exchange의 "euc-kr")
    actual_encoding_used: str      # 실제로 디코딩에 쓴 인코딩(항상 "utf-8" — §검증2 확정)


# --- SectionIR ---
@dataclass(frozen=True)
class SectionIR:
    node_id: str
    title_text: str
    depth: int | None             # None=추정 실패(ParserWarning 발생, §6 규칙)
    source: SourceLocation


# --- TableIR ---
@dataclass(frozen=True)
class TableCellIR:
    row: int
    col: int
    text: str
    rowspan: int = 1
    colspan: int = 1
    tag: str = "TD"          # "TD"|"TE"|"TU"|"TH"(dart) 또는 "td"(kind) — §검증4 TD/TE 반전 대응, 원본 태그명 보존

@dataclass(frozen=True)
class TableIR:
    node_id: str
    section_hierarchy: list[str]
    source: SourceLocation
    raw_cells: list[TableCellIR]          # 병합 안 풀고 그대로
    normalized: "TableMetadata"             # 기존 계약 타입 그대로 재사용(아래 §3 충돌표 참조)


# --- DocumentNodeIR: Section/Table/Paragraph 통합 union ---
class NodeKind(str, Enum):
    SECTION = "section"
    TABLE = "table"
    PARAGRAPH = "paragraph"

@dataclass(frozen=True)
class ParagraphIR:
    node_id: str
    section_hierarchy: list[str]
    text: str
    source: SourceLocation
    is_footnote_like: bool = False

DocumentNodeIR = SectionIR | TableIR | ParagraphIR   # 순서 보존된 flat list의 원소 타입


# --- ParserWarning / ParseQuality ---
class WarningCode(str, Enum):
    SANITIZED_ENTITY = "sanitized_entity"
    UNKNOWN_SECTION_DEPTH = "unknown_section_depth"
    TABLE_MERGED_CELL_IGNORED = "table_merged_cell_ignored"
    ROUTER_FALLBACK_PARSER = "router_fallback_parser"
    PARSE_FAILED = "parse_failed"
    ENCODING_DECLARATION_MISMATCH = "encoding_declaration_mismatch"   # ★신규, §검증2 확정 사실 반영

@dataclass(frozen=True)
class ParserWarning:
    doc_id: str
    rel_path: str
    code: WarningCode
    severity: str    # "info"|"warning"|"error"
    message: str

@dataclass
class ParseQuality:
    tier: str                      # "structured"|"partial"|"fallback"
    schema_version: str | None
    n_sanitized_entities: int
    n_unresolved_section_depth: int
    n_tables_with_merged_cells: int
    router_matched_expected_parser: bool


# --- DocumentIR (top level, Parser의 유일한 산출물) ---
@dataclass
class DocumentIR:
    doc_id: str
    source_files: list[SourceFileIR]     # 본문+첨부 전부, is_attachment로 구분
    nodes: list[DocumentNodeIR]            # 원문 순서 그대로, flat
    warnings: list[ParserWarning]
    parse_quality: ParseQuality


# --- ChunkSet (Chunking 전략의 산출물, DocumentIR과 완전 분리) ---
@dataclass
class ChunkSet:
    doc_id: str
    strategy_name: str            # "whole_table" | "row_table" | "paragraph_480tok_bge_m3"
    chunks: list["Chunk"]           # 기존 계약의 Chunk 타입 그대로(§3 아래)
    source_ir_node_ids: list[str]     # 이 ChunkSet이 어느 DocumentIR.nodes에서 파생됐는지(추적성)
```

---

## 3. 기존 계약과의 충돌 — 명시 (임의 추가 없음)

| 충돌 지점 | 기존 계약 | 문제 | 최소 변경안 |
|---|---|---|---|
| **`ParsedDocument.chunks`** | 계획서(Task 4) — Parser가 `ParsedDocument`를 반환하는데 그 안에 `chunks: list[Chunk]`가 바로 들어있음 | **이 설계의 목표(Parser는 청킹 안 함)와 정면 충돌** — `ParsedDocument`는 사실상 "파싱+청킹 결과"였음 | `ParsedDocument`를 **폐기하고 `DocumentIR`로 대체**한다(같은 역할, 이름과 내용 변경). `ParsedDocument`를 그대로 두고 옆에 IR을 추가하면 두 개의 "문서 파싱 결과" 타입이 공존해 혼란 — 하나로 통일 권장. 이건 코드 삭제라 "충돌"이지 "추가"가 아님 |
| **`Evidence.chunk_id`** | Evidence는 chunk에 속함(계약 고정) | IR 단계(`TableCellIR`)엔 chunk_id가 없음(아직 청크가 없어서) | 변경 없음 — `Evidence`는 여전히 ChunkSet 생성 시점에만 만들어짐. `TableCellIR`은 Evidence가 아니라 **Evidence 이전 단계의 원재료**로 신규 타입(§2에 이미 반영) |
| **`Chunk.table_metadata: TableMetadata`** | 이미 확정 | `TableIR.normalized`가 이 타입을 그대로 재사용 | 변경 없음(재사용) |
| **`parse_quality`** | 기존 계약에 없음(신규) | — | **팀 계약 갱신 요청 필요**(임의 추가 아님, 이전 리포트에서도 동일하게 표시함 — 반복 확인) |
| **`ChunkSet` 자체** | 기존 계약엔 "Chunk 리스트"만 있고 그걸 묶는 상위 타입이 없음 | 청킹 전략이 여러 개(whole/row) 나올 걸 감안하면 "이 Chunk들이 어느 전략에서 나왔는지"를 추적할 그릇이 없었음 | **신규 타입 추가 필요**(계약 갱신 요청 대상, `parse_quality`와 같이 묶어서 팀에 한 번에 요청 권장) |

---

## 4. 직렬화 형식

- `DocumentIR` → `data/document_ir/{doc_id}.json`(문서당 1파일, JSON — 나중에 여러 청킹 전략이 같은 파일을 재사용하기 쉽게)
- `ChunkSet` → `data/chunks/{strategy_name}/{doc_id}.jsonl`(전략별 디렉터리 분리 — whole_table과 row_table이 같은 doc_id라도 안 섞임)
- 두 산출물을 **물리적으로도 분리된 디렉터리**에 둬서 "IR 재사용, Chunk만 다시 생성" 워크플로우가 파일시스템 레벨에서도 자연스럽게 성립

---

## 5. Deterministic ID 규칙 (최종)

```python
def make_ir_node_id(doc_id: str, rel_path: str, order_index: int) -> str:
    return f"{doc_id}::{rel_path}::n{order_index}"

def make_chunk_id(ir_node_id: str, strategy_name: str, sub_idx: int) -> str:
    return f"{ir_node_id}::{strategy_name}::c{sub_idx}"

def make_evidence_id(chunk_id: str, row: int, col: int) -> str:
    return f"{chunk_id}::r{row}c{col}"
```
변경 없음(이전 리포트 §3과 동일) — 이번 검증에서 이 규칙을 깨는 사실은 안 나옴, 그대로 확정.

---

## 6. 파일별 변경 계획 (이번 설계 반영, 구현은 다음 단계)

| 파일 | 내용 |
|---|---|
| `src/dart_corpus/parsing/document_ir.py` | §2 타입 전부(SourceFileIR/SectionIR/TableIR/ParagraphIR/DocumentIR/ParseQuality/ParserWarning) |
| `src/dart_corpus/parsing/chunk_set.py` | §2 `ChunkSet`(신규, Chunk는 기존 계약 import) |
| `src/dart_corpus/parsing/ids.py` | §5 3개 함수 |
| `src/dart_corpus/contract/snapshot.py` | **수정 필요** — `SourceFileIR.content_sha256` 대응, snapshot 단계에서 파일별 해시도 같이 찍어두면 IR 생성 시 재사용 가능(중복 I/O 방지) |

## 7. Fixture 목록 (검증으로 확정된 실제 샘플, §검증5 표 그대로 + 인코딩/첨부 케이스 추가)

| fixture | doc_id | 목적 |
|---|---|---|
| periodic dart3 | `periodic_20231114001884` | TD 우세 스키마 |
| periodic dart4 | `periodic_20241114001965` | TE 우세 스키마(같은 회사, 구조반전 직접 대조) |
| major dart3 | `major_20230601000234` | — |
| major dart4 | `major_20251219000396` | — |
| holding dart3 | `holding_20230103000123` | — |
| holding dart4 | `holding_20240717000432` | — |
| exchange 인코딩거짓선언 | `exchange_20230406800008` | euc-kr 선언·utf-8 실체 — 디코딩 강제 로직 테스트 |
| 첨부파일 있음 | `periodic_20250311001085`(n_files=3) | 본문/첨부 판별 규칙 테스트 |
| pdf+html | `periodic_20260619000667` | DocumentIR 생성 안 하고 unsupported로 명시 처리되는지 |

**팀에 계약 갱신 요청할 것(임의 반영 안 함): `parse_quality` 필드 + `ChunkSet` 타입 — 이 둘만 `interface_contract_draft.md`에 정식 추가 필요.**
