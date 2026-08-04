# Workstream A 상세 설계 — Canonical Parser → DocumentIR → Chunking 분리

> 이 단계도 구현 없음(설계 문서만). 근거는 전부 `docs/superpowers/plans/2026-07-29-mvp-fact-store.md`(기존 계획, 미실행)와
> `docs/interface_contract_draft.md`(팀 확정 계약)와 실제 corpus 샘플 대조. 확정 사실과 제안(검증 필요)을 구분해 표기함
> — **[확인]** = 실제 파일로 검증됨, **[제안]** = 설계 결정이라 다음 단계에서 검증 필요.

---

## 0. 기존 계약과의 충돌 — 요약 (임의 필드 추가 없음)

| 충돌 지점 | 기존 계약(`interface_contract_draft.md`) | 이 설계의 선택 | 최소 변경안 |
|---|---|---|---|
| `TableMetadata` | 이미 확정된 dataclass(title/row_headers/col_headers/unit/period/consolidation_basis) | **그대로 import해서 씀** — `IRTableMetadata`를 새로 안 만듦 | 변경 없음, 재사용만 |
| `section_hierarchy: list[str]` | `Chunk`에 이미 있음 | IR 노드에도 **동일 타입·동일 이름**으로 둠(청킹 시 그대로 복사되게) | 변경 없음 |
| `Evidence.chunk_id` | Evidence는 **chunk에 속한다**고 계약돼 있음 | IR 단계에선 Evidence를 아직 안 만듦(chunk_id가 없으므로) — IR은 표의 raw cell 배열만 갖고, **Evidence 생성은 청킹 단계로 미룸** | 계약 위반 없음(Evidence는 여전히 청킹 결과물), 대신 IR에 `IRTableCell`(임시, chunk_id 없는 표현)이 새로 필요함 — 아래 §7 |
| `ChunkKind.SECTION` | "섹션 전체를 대표하는 상위 chunk"로 정의됨 | IR 단계엔 `IRSection`이 있지만 이건 chunk가 아니라 **경계 마커**임 — SECTION kind chunk는 청킹 전략이 IRSection 경계 안의 IRParagraph들을 요약/결합해서 **나중에** 만드는 것 | 개념 구분만 명확히, 필드 충돌 없음 |
| `is_attachment: bool` | `Chunk`에 있음 | IR 최상위(`DocumentIR.source_files[].is_attachment`)에 둠 — 파일 단위 속성이라 Chunk보다 상위가 더 정확한 위치 | Chunk가 이 값을 IR에서 그대로 물려받으면 되므로 충돌 아님 |
| `parse_quality` | 기존 계약에 **없음**(신규) | `DocumentIR.parse_quality`로 신규 추가 — 계약 확장 필요 | **팀에 계약 갱신 요청 필요**(interface_contract_draft.md 갱신 절차대로) |

---

## 1. Corpus Snapshot 스키마 + 검증 항목

기존 계획(Task 1-2) `ManifestLoader`/`UniverseLoader`를 그대로 채택하되, **검증 항목**을 명시적으로 추가한다(계획서엔 "몇 건이어야 하는지"만 있고 "무엇을 검증하는지" 체크리스트가 없었음).

```python
@dataclass(frozen=True)
class CorpusSnapshotReport:
    manifest_row_count: int          # [확인] 기대값 4204
    universe_row_count: int          # [확인] 기대값 70
    schema_version_histogram: dict[str, int]   # {"dart3.xsd": N, "dart4.xsd": M} — [신규 발견, §이전 리포트]
    file_format_histogram: dict[str, int]      # {"xml": 4201, "pdf+html": 3}
    doc_group_histogram: dict[str, int]
    n_files_mismatch: list[str]      # manifest.n_files != 실제 디렉터리 내 xml 개수인 doc_id 목록
    path_resolution_failures: list[str]   # resolve_corpus_path 실패한 file_path 목록(0건이어야 정상)
    major_doc_subtype_all_blank: bool     # [확인] 598건 전부 빈 문자열 — 검증 항목으로 명시
    corp_code_leading_zero_ok: bool       # 8자리 str 유지 확인(예: "00126380")
```

**검증 절차(순서):** (1) manifest/universe row count → (2) 파일포맷 분포 → (3) `resolve_corpus_path`로 전 문서 경로 해석 성공률(NFD/NFC) → (4) `n_files` 대 실제 디렉터리 파일 수 대조 → (5) 스키마버전 히스토그램(신규) → (6) major `doc_subtype` 공백 재확인. 이 리포트가 **파싱 시작 전에 통과해야 하는 게이트** — 하나라도 실패하면 파싱 자체를 안 돌림(잘못된 경로로 4천 건 다 실패하는 낭비 방지).

---

## 2. Canonical DocumentIR dataclass

```python
class IRNodeKind(str, Enum):
    SECTION_MARKER = "section_marker"   # TITLE 하나 = 경계 마커(그 자체는 텍스트 chunk 아님)
    PARAGRAPH = "paragraph"              # P 하나(또는 인접 P 묶음)
    TABLE = "table"                       # TABLE-GROUP 하나

@dataclass(frozen=True)
class SourceLocation:
    rel_path: str            # file_path 기준 상대경로(예: "20260316001112.xml", 첨부는 "20260316001112_00760.xml")
    order_index: int          # 그 파일 안에서 문서 순서(0부터, TITLE/P/TABLE-GROUP 전부 포함해 증가) — §5 순회규칙 산출값
    byte_offset: int | None = None   # 디버깅용, 필수 아님

@dataclass(frozen=True)
class IRParagraph:
    node_id: str                      # §3
    kind: IRNodeKind = IRNodeKind.PARAGRAPH
    section_hierarchy: list[str] = field(default_factory=list)   # TableMetadata와 동일 타입 재사용(§0)
    text: str = ""
    source: SourceLocation = None
    is_footnote_like: bool = False    # "※"/"주N)" 시작 패턴 — §설계 결정, 별도 kind 안 만들고 플래그만

@dataclass(frozen=True)
class IRTableCell:
    row: int
    col: int
    text: str
    rowspan: int = 1
    colspan: int = 1
    label_guess: str | None = None    # "마지막=값, 끝에서 두번째=라벨" 휴리스틱 결과(§0 Evidence 대체)

@dataclass(frozen=True)
class IRTable:
    node_id: str
    kind: IRNodeKind = IRNodeKind.TABLE
    section_hierarchy: list[str] = field(default_factory=list)
    source: SourceLocation = None
    raw_cells: list[IRTableCell] = field(default_factory=list)     # §7 raw
    normalized: "TableMetadata" = None    # 기존 계약 타입 그대로(§0) — §7 normalized

@dataclass(frozen=True)
class IRSectionMarker:
    node_id: str
    kind: IRNodeKind = IRNodeKind.SECTION_MARKER
    title_text: str = ""
    depth: int | None = None       # §6, None이면 depth 추정 실패(경고 발생)
    source: SourceLocation = None

@dataclass
class ParseQuality:      # §8-9
    tier: str            # "structured" | "partial" | "fallback"
    schema_version: str | None
    n_sanitized_entities: int
    n_unresolved_section_depth: int
    n_tables_with_merged_cells: int
    router_matched_expected_parser: bool

@dataclass
class DocumentIR:
    doc_id: str
    source_files: list[dict]        # [{"rel_path":..., "is_attachment": bool}, ...] — 본문/첨부 구분(§0)
    nodes: list[IRParagraph | IRTable | IRSectionMarker]   # §5: 원문 순서 그대로, 평평한 리스트
    warnings: list["ParserWarning"]
    parse_quality: ParseQuality
```

**설계 결정 — 트리 대신 평평한 리스트:** "TITLE/P/TABLE-GROUP 원문 순서 보존" 요구를 가장 직접적으로 만족하는 방법은 트리가 아니라 **순서 그대로의 flat list**다. `IRSectionMarker`가 나올 때마다 그 뒤 노드들의 `section_hierarchy`가 갱신되는 식 — 트리로 다시 만들고 싶으면 `section_hierarchy` breadcrumb으로 언제든 재구성 가능(정보 손실 없음), 반대(트리→순서복원)보다 훨씬 쉬움.

---

## 3. Deterministic ID 규칙

기존 계획 `make_chunk_id`/`make_evidence_id`(doc_id+rel_path+section_path+seq) 원칙을 IR 레벨로 한 단계 내림:

```python
def make_ir_node_id(doc_id: str, rel_path: str, order_index: int) -> str:
    return f"{doc_id}::{rel_path}::n{order_index}"
```

- **IR 노드 ID는 `order_index`(문서 내 절대 순서)만 쓴다** — section_path 문자열을 안 넣는 이유: section_path는 §6 추정 결과라 나중에 규칙을 고치면 바뀔 수 있는데, ID가 그걸 포함하면 규칙 개선할 때마다 ID가 바뀌어 재현성이 깨진다. `order_index`는 XML 파싱 순서라 규칙과 무관하게 항상 같다.
- **Chunk ID는 IR 노드 ID + 청킹 전략명 + 청크 내 서브인덱스**로 파생: `make_chunk_id(ir_node_id, strategy, sub_idx) -> f"{ir_node_id}::{strategy}::c{sub_idx}"` — 문단이 480토큰 넘어 여러 chunk로 쪼개질 때 `sub_idx`로 구분. 표(whole 모드)는 sub_idx 항상 0.
- **Evidence ID**: 청킹 단계에서 `IRTableCell`이 Chunk로 편입될 때 생성 — `f"{chunk_id}::r{row}c{col}"`(기존 규칙 그대로).

---

## 4. 공통 parser entry point + 문서유형별 policy

```python
def parse_document(doc: DocumentRecord, corpus_root: Path) -> DocumentIR:
    """유일한 공개 진입점. 내부에서 정책표 보고 분기, 실패 시 §9 순서로 강등."""
```

| doc_group | 기대 파서 | section_hierarchy 정책 | 근거 |
|---|---|---|---|
| periodic | DART XML | **깊은 계층**(I./1./가. 등 다단계) | [확인] TITLE 55개, TABLE-GROUP 26개(CJ제일제당 예시) |
| major | DART XML | **얕은 계층**(문서 제목 1단만, 세부 TITLE 거의 없음) | [확인] 이전 세션에서 유상증자결정 문서 봤을 때 번호 매긴 표 항목(1.신주의종류... )뿐, I/II 계층 없음 |
| holding | DART XML | **얕은 계층** + 표 안 다중 행(보고자 N명) | [확인] 이전 세션에 지분공시 다중행 구조 확인함 |
| exchange | KIND HTML | **계층 없음**(테이블 1~2개, 필드-값 나열) | [확인] `<html>` 루트, XML 아님 |

파서는 `doc.doc_group`으로 기대 파서를 고르되, `can_parse()`로 실제 루트 구조를 대조해서 안 맞으면 경고 남기고 다른 파서 시도(기존 `ParserRouter` 설계 그대로 재사용, 대상만 Chunk→DocumentIR로 변경).

---

## 5. TITLE/P/TABLE-GROUP 순회 규칙

```
DFS(root):
  order_index = 0
  section_stack = []   # (title_text, depth) 튜플 스택
  for element in root.iter() in document order:
      if element.tag == "TITLE":
          depth = infer_depth(element.text)          # §6
          pop section_stack until top.depth < depth (또는 depth 추정 실패시 안 건드림)
          push (element.text, depth)
          emit IRSectionMarker(title_text, depth, order_index); order_index += 1
      elif element.tag == "TABLE-GROUP" (또는 TABLE, 최상위인 것만 — 중첩 TABLE 무시):
          emit IRTable(section_hierarchy=snapshot(section_stack), ...); order_index += 1
      elif element.tag == "P":
          emit IRParagraph(section_hierarchy=snapshot(section_stack), ...); order_index += 1
      # 그 외 태그(SUMMARY, EXTRACTION 등)는 무시 — 순회에 안 들어감
```

**[제안, 검증 필요] TABLE-GROUP 안 중첩 TABLE 처리**: `<TABLE-GROUP>` 하나 안에 `<TABLE>`이 여러 개(예: 표 제목용 1행짜리 TABLE + 본문 TABLE) 있는 걸 이전 세션에서 목격함(한화에어로 사업보고서 §사업부문별 요약재무현황 예시). 규칙: **TABLE-GROUP 레벨에서 IRTable 1개로 묶는다**(안의 개별 TABLE을 따로 안 쪼갬) — TABLE-GROUP이 논리적 표 단위이고 개별 TABLE은 렌더링 상 조각일 뿐이라는 가정. **이건 실제 XML 여러 개 더 봐야 확정** — 다음 단계 검증 항목.

**[제안, 검증 필요] P가 TABLE-GROUP 안에 있는 경우**(표 캡션·각주가 P로 들어있는 경우): 순회에서 만나는 순서 그대로 처리하면 자동으로 해결되지만, 그 P가 "표의 일부"로 봐야 하는지 "독립 문단"으로 봐야 하는지는 표본 확인 필요.

---

## 6. Section Hierarchy 생성 규칙

```python
_DEPTH_PATTERNS = [
    (1, re.compile(r"^[IVX]+\.\s")),        # I. II. III.
    (2, re.compile(r"^\d+\.\s")),            # 1. 2. 3.
    (3, re.compile(r"^[가나다라마바사아자차카타파하]\.\s")),  # 가. 나.
    (4, re.compile(r"^\(\d+\)\s")),          # (1) (2)
]

def infer_depth(title_text: str) -> int | None:
    for depth, pattern in _DEPTH_PATTERNS:
        if pattern.match(title_text.strip()):
            return depth
    return None   # ParserWarning: UNKNOWN_SECTION_DEPTH — §8
```

**depth 추정 실패 시(예: "목차", "【 대표이사 등의 확인 】", 표 제목처럼 보이는 TITLE인 "사업부문별 요약재무현황")**: [제안] 직전 depth를 그대로 유지하고(스택 안 건드림) `ParserWarning(code="UNKNOWN_SECTION_DEPTH")` 기록. 강등은 안 함(전체 문서를 fallback시킬 정도의 문제가 아니므로) — 단, `parse_quality.n_unresolved_section_depth`에는 집계.

**[검증 필요] ATOC 속성으로 "진짜 섹션제목" vs "표 캡션성 TITLE" 구분 가능한지**: 이전 세션에 `<COVER-TITLE ATOC="Y">`만 봤고, 본문 TITLE의 ATOC 분포는 안 봤음 — 다음 단계에서 실제 body TITLE 100개 정도 뽑아서 ATOC 값 확인 권장(이 설계의 depth 추정이 번호패턴만 쓰는 이유는 ATOC 신뢰성이 아직 미검증이라서).

---

## 7. TableIR raw/normalized 구조

- **raw**(`IRTable.raw_cells: list[IRTableCell]`): 표를 있는 그대로 — 행/열 좌표 + rowspan/colspan 속성 + 텍스트. **병합셀도 값을 안 풀어서 그대로 둠**(1차 스코프, §이전 회의자료 "병합셀 1차는 무시" 결정과 일치 — "무시"의 정확한 의미: rowspan/colspan 숫자는 raw에 보존하되 그 셀이 차지하는 나머지 좌표에 값을 복제해서 채우지 않는다는 뜻. 복제해서 채우는 건 normalized 단계나 후속 개선에서).
- **normalized**(`IRTable.normalized: TableMetadata`, 기존 계약 타입 그대로): raw_cells에서 최선 추정으로 채움 —
  - `title`: 같은 section_hierarchy 안에서 이 TABLE 직전에 나온 IRSectionMarker나 첫 행이 표 전체를 가로지르는 단일 셀이면 그 텍스트
  - `unit`: raw_cells 텍스트 전체에서 정규식 `단위\s*[:：]\s*(\S+)` 검색
  - `period`: 정규식 `제\d+기` 검색
  - `consolidation_basis`: **[확인]** section_hierarchy 안에 "연결"/"별도" 문자열 있으면 그걸로 판별(표 헤더 추론보다 우선, 이미 팀 확정 원칙)
  - `row_headers`/`col_headers`: 첫 행/첫 열 텍스트(병합셀 있으면 부정확할 수 있음 — 한계로 명시)

두 표현을 다 갖고 있는 이유: whole-table 청킹 전략은 normalized만 쓰면 되고, 나중에 row-단위 ablation 청킹 전략은 raw_cells가 필요함 — IR 단계에서 한 번만 파싱해두면 두 전략이 재파싱 없이 같은 IR 재사용 가능(§0 목표와 일치).

---

## 8. ParserWarning + parse_quality

```python
class WarningCode(str, Enum):
    SANITIZED_ENTITY = "sanitized_entity"              # bare & 또는 < 이스케이프함
    UNKNOWN_SECTION_DEPTH = "unknown_section_depth"     # §6
    TABLE_MERGED_CELL_IGNORED = "table_merged_cell_ignored"
    ROUTER_FALLBACK_PARSER = "router_fallback_parser"    # 기대 파서 실패, 다른 파서로 성공
    PARSE_FAILED = "parse_failed"                          # §9 fallback 진입
    SCHEMA_VERSION_UNEXPECTED = "schema_version_unexpected"  # dart3/dart4 외 값

@dataclass(frozen=True)
class ParserWarning:
    doc_id: str
    rel_path: str
    code: WarningCode
    severity: str   # "info" | "warning" | "error"
    message: str
```

`parse_quality.tier`는 이 warnings 목록에서 **파생 계산**(별도로 손으로 안 정함, §9 규칙표 그대로 적용) — warnings와 tier가 따로 놀면(수동 설정) 나중에 불일치 위험 있어서 반드시 코드로 유도.

---

## 9. structured → partial → fallback 처리 규칙

| tier | 조건 | 산출물 |
|---|---|---|
| **structured** | sanitize 불필요(bare `&`/`<` 0건) **and** router가 기대 파서 그대로 성공 **and** 모든 TITLE의 depth 추정 성공 | 완전한 DocumentIR(SECTION/TABLE/PARAGRAPH 다 있음) |
| **partial** | sanitize 필요했지만 파싱 성공, **또는** UNKNOWN_SECTION_DEPTH 1건 이상, **또는** ROUTER_FALLBACK_PARSER 발생 | 완전한 DocumentIR이지만 `parse_quality`에 결함 기록, 신뢰도 낮음 표시 |
| **fallback** | sanitize 후에도 `ElementTree`/`BeautifulSoup` 파싱 자체가 실패 **또는** 루트 태그가 어느 파서와도 안 맞음 | **최소 IR**: 태그 다 벗겨낸 raw text 전체를 `IRParagraph` 1개로(section_hierarchy=[], is_footnote_like=False), PARSE_FAILED 경고, tier=fallback |

**fallback도 절대 빈 chunk를 안 만든다**(§이전 리포트 "정밀 실패해도 검색은 된다" 원칙) — 최소 1개 문단이라도 나와야 BM25/Dense 검색 대상에 포함됨.

---

## 10. 품질검증 지표 + artifact 형식

```
data/parse_quality/
├── parse_quality_report.jsonl   # 문서 1건당 1행: doc_id, tier, warnings(code 목록), n_sections, n_tables, n_paragraphs
└── parse_quality_summary.json    # 코퍼스 전체 집계
```

`parse_quality_summary.json` 스키마:
```python
{
  "total_documents": int,
  "tier_histogram": {"structured": N, "partial": M, "fallback": K},
  "tier_by_doc_group": {...},
  "warning_code_histogram": {...},
  "schema_version_histogram": {"dart3.xsd": N, "dart4.xsd": M},
  "documents_needing_review": [doc_id, ...]   # fallback 전부 + partial 중 warning severity=error
}
```

이 summary가 **실제 5천~2만 chunk 규모 corpus를 만들기 전에 사람이 보는 첫 게이트** — fallback 비율이 예상보다 높으면(예: 5% 넘으면) §6/§9 규칙을 고치고 나서 진행.

---

## 11. 단위테스트 fixture (실제 corpus 파일, 이번 세션에서 이미 확인된 것 우선 사용)

| fixture | doc_id | 검증 목적 |
|---|---|---|
| periodic, dart4.xsd, 깊은 계층, ROWSPAN 있음 | `periodic_20260316001112`(한화에어로 2025 사업보고서) | §5/§6/§7 정상 케이스, [확인] TITLE/TABLE-GROUP 실제 존재 |
| periodic, dart3.xsd, 구버전 스키마 | `periodic_20230515002270`(CJ제일제당 2023 분기) | §2 스키마버전 혼재 대응, [확인] TITLE 55개 |
| periodic, bare `&`/`<` 649개 | `periodic_20250311001085`(삼성전자 2024 사업보고서) | §9 partial tier(sanitize 필요), [확인] "R&D" 실측 |
| major, 얕은 계층 | `major_20250320001145`(한화에어로 유상증자결정) | §4 policy(얕은 계층) 검증 |
| exchange, KIND HTML 2셀 | `exchange_20230228801277`(대우건설 계약체결) | §4 KIND 파서 경로, [확인] 이전 세션에 직접 읽음 |
| holding, 다중행 | `holding_20260113000652`(한화에어로 최대주주) | §7 다중 보고자 행 처리 |
| **fallback 강제(합성 픽스처)** | 실제 파일 하나를 테스트에서 임의로 truncate/깨뜨린 사본 | §9 fallback tier가 정말로 최소 IR을 만드는지(실제 코퍼스엔 이런 파일이 없어서 합성 필요 — 유일하게 실제 파일 아님, 명시) |
| `file_format=pdf+html` | 3건 중 1건(예: 한화에어로스페이스 분기보고서 2026.03) | §1 corpus snapshot 검증(스킵 안 하고 unsupported로 기록되는지) |

---

## 12. 구현 순서 + 파일별 변경 계획

| 순서 | 파일 | 내용 | 의존성 |
|---|---|---|---|
| 1 | `src/dart_corpus/contract/*` | 기존 계획 Task 1-3 그대로(NFD/NFC, manifest/universe loader, alias) | 없음 |
| 2 | `src/dart_corpus/contract/snapshot.py` | §1 `CorpusSnapshotReport` + 검증 게이트 | 1 |
| 3 | `src/dart_corpus/parsing/document_ir.py` | §2 dataclass 전부(IRParagraph/IRTable/IRSectionMarker/DocumentIR/ParseQuality) | 없음(순수 타입) |
| 4 | `src/dart_corpus/parsing/ids.py` | §3 `make_ir_node_id` (+ 기존 make_chunk_id/make_evidence_id를 청킹 단계용으로 이관) | 없음 |
| 5 | `src/dart_corpus/parsing/section_builder.py` | §6 `infer_depth`, 스택 관리 로직 단독 모듈(테스트 쉽게 분리) | 3 |
| 6 | `src/dart_corpus/parsing/table_serializer.py` | §7 raw_cells 추출 + normalized 추정 | 3 |
| 7 | `src/dart_corpus/parsing/canonical_parser.py` | §4/§5 — dart_parser.py/kind_parser.py 로직 재활용, `parse_document()` entry point, section_builder/table_serializer 호출 | 3,5,6 |
| 8 | `src/dart_corpus/parsing/fallback.py` | §9 fallback 최소 IR 생성 | 3 |
| 9 | `src/dart_corpus/parsing/router.py` | 기존 Task 7 재사용, 반환 타입만 DocumentIR로 | 7,8 |
| 10 | `src/dart_corpus/quality/report.py` | §10 quality artifact 생성 | 2,7 |
| 11 | `tests/parsing/*` | §11 fixture 기반 테스트 전부 | 3-9 |
| 12 | `scripts/run_corpus_snapshot.py` | §1 게이트 단독 실행 스크립트(파싱 전에 먼저 돌리는 것) | 2 |
| 13 | `scripts/run_parse_all.py` | 전 문서 파싱 + quality summary 생성(이때 처음으로 실제 5천~2만 규모 IR 나옴) | 9,10,12 |

**계약 갱신 필요 항목(팀 승인 대기, 임의로 진행 안 함):** `parse_quality`를 `interface_contract_draft.md`에 신규 필드로 추가하는 것 — §0 표에 이미 표시함, 이 문서 승인과 별개로 계약 문서 자체도 갱신 필요.
