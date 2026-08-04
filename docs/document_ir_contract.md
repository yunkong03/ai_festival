# DocumentIR Contract (document_ir_schema_v0, status: proposed)

Workstream A → B/C 공통 handoff 문서. 현재 구현(`src/dart_corpus/parsing/`, `src/dart_corpus/contract/snapshot.py`)만
기준으로 작성했다 — 새 Parser 기능은 없다. B/C가 요청한 필드 중 현재 코드에 없는 것은 "gap"으로 명시하고
추측하지 않는다.

관련 파일:
- 스키마: `schemas/document_ir_schema_v0.json`
- 대표 샘플: `data/artifacts/handoff/representative_documents.jsonl`
- 전체 산출물: `data/artifacts/corpus_snapshot.json`, `data/artifacts/document_ir/{periodic,major,exchange,holding}.jsonl`, `data/artifacts/parse_audit.jsonl`, `data/artifacts/parse_summary.json`, `data/artifacts/failed_documents.jsonl`

버전 표기(모든 DocumentIR 레코드에 실제로 포함되는 필드):
- `parser_version = "1.0.0"` (`dart_corpus.parsing.document_ir.PARSER_VERSION`)
- `schema_version = "1.0"` (`DOCUMENTIR_SCHEMA_VERSION` — DocumentIR dataclass 구조 버전. 이 문서/스키마 파일명의 `v0`는 계약 문서 자체의 버전이고 서로 다른 축이다)
- `corpus_snapshot_id` — 생성 시점에 사용한 Corpus Snapshot ID

---

## 1. DocumentIR 필드 설명

| 필드(요청명) | 현재 구현 매핑 | 의미 | 생성 시점 | 생성 규칙 | 예시 | 주의점 |
|---|---|---|---|---|---|---|
| `doc_id` | `DocumentIR.doc_id` | manifest doc_id 그대로 | 파싱 시작 시 입력값 복사 | 없음(manifest 값 그대로) | `"periodic_20231114001884"` | 전역 유일 |
| `source_file_id` | **gap** — 없음. `SourceFileIR.rel_path`가 대체 | 문서 내 원본 파일 식별자 | - | - | `"20231114001884.xml"` | 문서 내에서만 유일(전역 유일 아님) — 전역 키가 필요하면 `(doc_id, rel_path)` 조합 사용 |
| `file_role` | **gap** — 없음. `is_attachment`(bool) + `content_format` + `rel_path` 접미사 조합으로 유도 | MAIN/ATTACHMENT/VIEWER_HTML/SOURCE_PDF 구분 | - | 아래 §source_locator 규칙의 문서유형별 표 참고 | - | `is_attachment`는 pdf+html의 pdf/viewer.html 둘 다 `false`로 기록됨 — `is_attachment`만으로 MAIN vs VIEWER_HTML 구분 불가 |
| `detected_content_type` | `SourceFileIR.content_format` | raw bytes sniff 결과 | `sniff.sniff_content_type()` | 값: `dart_xml`\|`kind_html`\|`pdf`\|`unknown` | `"kind_html"` | manifest.file_format(확장자 기반)과 다를 수 있음(exchange 1469건) |
| `detected_encoding` | `SourceFileIR.actual_encoding_used` | 실제 디코딩에 쓴 인코딩 | `encoding.decode_with_fallback()` | UTF-8 우선 시도 → 실패 시 declared → 그것도 실패 시 `"utf-8(replace)"` | `"utf-8"`, `"utf-8(replace)"` | `declared_encoding`(파일 자기 선언)과 분리된 필드 — 다르면 `ENCODING_DECLARATION_MISMATCH` 경고 |
| `node_order` | `SourceLocation.order_index` | 파일 내 노드 등장 순번 | traversal 중 1씩 증가 | section/table/paragraph 구분 없이 공유되는 단일 카운터 | `0,1,2,...` | **파일이 바뀌면 0으로 리셋** — 문서 전체 전역 순번 아님. 여러 소스파일 간 순서는 파일명 정렬(`sorted()`)에 의존 |
| `section_id` | `SectionIR.section_id` | 섹션 고유 ID | `emit_section()` | `node_id`와 동일 값 | `"periodic_x::f.xml::n3"` | - |
| `parent_section_id` | `SectionIR.parent_section_id` | 부모 섹션 ID | `SectionStackBuilder.push()` | 부모의 `section_id`, 최상위면 문자열 `"ROOT"` | `"ROOT"` | `"ROOT"`는 가상 노드 — `nodes` 배열에 실체 없음 |
| `section_path` | **gap** — 없음. `section_hierarchy + [자기 title_text]`로 소비자가 직접 구성 | 루트부터 자기까지의 제목 경로 | - | 아래 §2 참고 | `"II. 사업의 내용 > 3. 원재료 및 생산설비"` | 파서가 구분자 있는 문자열을 만들어주지 않음 |
| `section_hierarchy` | `SectionIR.section_hierarchy` / `TableIR.section_hierarchy` / `ParagraphIR.section_hierarchy` | 조상 제목 리스트(루트→직계부모) | push 시점 스냅샷 | 자기 자신 **제외**(SectionIR 기준). TableIR/ParagraphIR은 노드 자체에 제목이 없으므로 "현재 열린 섹션 전체"가 곧 자기 소속 경로 | `["I. 회사의 개요"]` | TableIR의 경우 TABLE-GROUP 내장 TITLE이 방금 section으로 승격됐으면 그 제목까지 포함(표 자신의 캡션 섹션) |
| `table_group_id` | **gap** — 없음(§3 참고) | TABLE-GROUP 단위 ID | - | - | - | 현재는 `table_id`(=`node_id`)와 구분되지 않음 |
| `table_id` | `TableIR.node_id` | 표 하나의 ID | `emit_table()` | `make_ir_node_id()` | - | 하나의 TABLE-GROUP 안 물리적 `<TABLE>`이 여러 개면 그 TR들이 모두 합쳐져 **하나의** `table_id`가 됨(§3) |
| `row_id` | **gap** — 없음. `(table_id, row_index)` 조합으로 대체 | 표 안 행 식별자 | - | `row_index` = `raw_rows`/`normalized_rows` 배열의 바깥쪽 인덱스 | `("...::n5", 2)` | 결정론적(같은 parser_version 재실행 시 안정) |
| `source_locator` | `SourceLocation` | 원문 위치 정보 | 노드 생성 시 | §4 참고 | `{"rel_path":"f.xml","order_index":3,"byte_offset":null}` | `byte_offset`은 현재 항상 `null` |
| `parse_quality` | `DocumentIR.parse_quality`(`ParseQuality`) | 파싱 품질 요약 | `parse_document()` 종료 시 | §5 참고 | `{"tier":"structured",...}` | `tier`에 `"failed"` 없음(§5) |
| `warning_codes` | `DocumentIR.warnings[].code`(개별) 또는 `ParseAuditRecord.warning_codes`(중복제거+정렬된 문자열 리스트) | 발생한 경고 코드 | - | - | `["sanitized_entity","table_shape_mismatch"]` | DocumentIR 자체엔 `warning_codes`라는 이름의 필드는 없음 — `warnings` 배열에서 유도하거나 `parse_audit.jsonl`의 사전 집계값 사용 |
| `raw_rows` | `TableIR.raw_rows` | rowspan/colspan 미확장 원본 행 | `group_into_raw_rows()` | `raw_cells`를 row로 묶음(순서 보존, 빈 행도 유지) | - | - |
| `normalized_rows` | `TableIR.normalized_rows` | 직사각형으로 확장한 grid(text만) | `expand_normalized_rows()` | rowspan/colspan 반영 표준 확장 알고리즘 | - | 셀 메타데이터(tag 등) 소실 — 필요하면 `raw_rows` 사용 |
| `consolidation_basis` | `TableIR.consolidation_basis` | "연결"/"별도" 구분 | `infer_consolidation_basis()` | `section_hierarchy`에서 가까운(마지막) 제목부터 역순 탐색, 명확한 경우만 채움 | `"연결"` 또는 `null` | 근거는 `consolidation_basis_reason`. 모호하거나 없으면 항상 `null`(추측 금지) |

---

## 2. section_path 규칙

- **ROOT 처리**: 최상위 섹션의 `parent_section_id`는 항상 문자열 `"ROOT"`. ROOT는 가상 노드이며 `nodes` 배열에 실체가 없다.
- **TITLE level 판정**(`section_builder.classify_title_level`, 번호 패턴 기준):
  - `Ⅰ.`/`I.`(로마숫자) 또는 `【...】`(대괄호) → level 1
  - `N.`(단일 숫자) → level 2
  - `N-M.`(대시 숫자, 예: `2-1.`) → level 3
  - 위 패턴에 하나도 안 걸리면 **level 미확정**: 현재 스택 top의 `level + 1`로 대체하고 `level_confident=false` + `UNKNOWN_SECTION_DEPTH` 경고를 남긴다(스택이 비어있으면 level 1).
- **번호 패턴**: 정규식 기반, 텍스트 의미 해석 없음(순수 문자열 prefix 매칭).
- **ATOC 처리**: `TABLE-GROUP` 안에 내장된 `TITLE`의 `ATOC` 속성으로 승격 여부를 결정한다.
  - `ATOC="N"` → section으로 승격하지 않음(순수 표 캡션, 목차에도 없음. 예: "채무증권 발행실적")
  - `ATOC="Y"` 또는 속성 없음 → section으로 승격(부모 section의 numbering을 그대로 이어받음, 예: `"2-1. 연결 재무상태표"`)
- **TABLE-GROUP 내부 TITLE 처리**: 위 ATOC 규칙에 따라 승격되면 `emit_section()`을 호출해 진짜 SectionIR을 만들고, 그 직후 나오는 TABLE(들)의 `section_hierarchy`에 이 제목이 포함된다.
- **번호 없는 TITLE 처리**: level 판정 실패 시 "현재 열려 있는 섹션의 자식"으로 취급(현재 섹션 `level+1`). 형제로 취급하면 부모가 조기에 닫히는 버그가 있었음(테스트로 회귀 방지됨).
- **동일 TITLE 반복 처리**: **병합하지 않는다.** 같은 `title_text`가 여러 번 나오면 매번 새 `node_id`/`section_id`를 가진 별개의 SectionIR이 생성된다. 텍스트 기반 중복 감지/경고는 없음(gap).
- **section_path 구분자**: 파서는 구분자 있는 문자열을 만들지 않는다(gap). 소비자가 `section_hierarchy + [title_text]`를 `" > "`로 join하는 것을 권장 표현으로 삼는다.
  - 리스트: `["II. 사업의 내용", "3. 원재료 및 생산설비", "가. 생산능력"]`
  - 문자열: `"II. 사업의 내용 > 3. 원재료 및 생산설비 > 가. 생산능력"`
- **section_hierarchy와 section_path의 관계**: `section_hierarchy` = 자기 자신 제외 조상 리스트. `section_path`(파생값) = `section_hierarchy + [자기 title_text]`.
- **불확실한 hierarchy 처리**: `level_confident=false`는 **level 값만** 불확실하다는 뜻이다. `section_hierarchy` 리스트 자체(스택 상태)는 항상 정확하다 — 어떤 섹션이 열려 있었는지는 명확하게 추적되기 때문. 불확실성은 "이 섹션이 몇 레벨인가"에만 있다.
- **section_id와 parent_section_id의 관계**: `section_id == node_id`(자기 자신). `parent_section_id`는 push 시점에 스택 top(자기보다 얕은 레벨만 남을 때까지 pop한 뒤)의 `section_id`, 스택이 비면 `"ROOT"`.

---

## 3. table_group_id / table_id / row_id 규칙

- **table_group_id 생성 기준**: **없음(gap).** 현재 구현은 "TABLE-GROUP 단위"와 "표 단위"를 구분하지 않는다 — `_extract_table_cells()`가 `TABLE-GROUP` element 하위 **모든** `<TR>`을 `.//TR`로 한 번에 수집하므로, 그 안에 물리적 `<TABLE>`이 여러 개 있어도(실측: 제목/기간 표시용 1행짜리 표 + 실제 데이터 표 조합이 흔함) 그 TR들이 전부 하나의 `raw_cells`/`raw_rows`로 합쳐져 **하나의** `TableIR`(하나의 `node_id`)이 된다.
- **table_id 생성 기준**: `TableIR.node_id` = `make_ir_node_id(doc_id, rel_path, order_index)` = `"{doc_id}::{rel_path}::n{order_index}"`. 텍스트 내용 기반이 아니라 **원문 등장 순서(order_index)** 기반 — 요구사항대로 텍스트만으로 ID를 만들지 않는다.
- **row_id 생성 기준**: **없음(gap).** `raw_rows`/`normalized_rows` 배열의 바깥쪽 인덱스(0-based)가 row 위치를 나타내며, `(table_id, row_index)` 튜플이 사실상 결정론적 row 식별자 역할을 한다. 별도 문자열 필드로 굳이 만들려면 `f"{table_id}::row{row_index}"` 형태를 권장(아직 코드에 없음).
- **source_file_id와의 관계**: `table_id`(=`node_id`) 문자열 안에 이미 `rel_path`가 포함되어 있어(`doc_id::rel_path::nN`), 별도 `source_file_id` 없이도 소속 파일을 알 수 있다.
- **node_order 또는 table_order 사용 여부**: 별도 `table_order`는 없다. section/table/paragraph가 파일 안에서 발생한 순서를 공유하는 **단일** `order_index` 카운터를 쓴다(§1 `node_order` 참고).
- **동일 입력 재실행 시 ID 안정성**: 안정적이다. `order_index`는 XML/HTML 파싱 순회 순서에서만 유도되므로, section 추정 규칙(level 판정 등)이 바뀌어도 ID는 안 바뀐다(`parsing/ids.py` 설계 의도). 단, **traversal 순서 자체**(예: 어떤 태그를 재귀하는지)가 바뀌면 ID가 바뀔 수 있다 — 이는 `parser_version` bump 대상(§7).
- **중첩 TABLE 또는 다중 TABLE 처리**: 위에서 설명한 대로 합쳐진다(gap). `TABLE-GROUP` 밖에 단독으로 나오는 `<TABLE>`(드묾)은 그 자체로 별개의 `TableIR`이 된다.
- **TABLE-GROUP 하나에 TABLE 여러 개 있을 때 구분 규칙**: **현재 구분하지 않는다(gap).** `raw_rows` 인덱스만으로는 원래 어느 물리적 `<TABLE>` 소속이었는지 복원할 수 없다. 필요해지면 `_extract_table_cells()`가 `<TABLE>` 경계도 함께 기록하도록 확장해야 한다(신규 Parser 기능 — 이번 단계 범위 밖).
- **raw row와 normalized row의 ID 관계**: 같은 `row_index`를 공유한다(`normalized_rows[i]`는 `raw_rows[i]`를 확장한 결과). 단 컬럼 수는 colspan 확장으로 달라질 수 있다.

---

## 4. source_locator 규칙 (`SourceLocation`)

현재 필드: `rel_path`(string), `order_index`(int, 파일별 0부터), `byte_offset`(항상 `null`, 예약 필드).

**지원하지 않는 것(명시, 추측 금지)**:
- `xml_xpath` / `logical_path`: 없음.
- `table_index`: 없음(§3 TABLE-GROUP 다중 TABLE 구분 불가와 동일 원인).
- `row_index` / `col_index`: `SourceLocation` 자체엔 없다. 표 안에서는 `TableIR.raw_cells[].row`/`.col`로 별도 유도 가능(표 전체 단위 `source`와는 별개 경로).
- `character_start` / `character_end`: 없음.
- `page_number`: 없음. PDF는 애초에 파싱하지 않으므로(§문서유형별 표) 페이지 개념 자체가 산출물에 없다.

**문서 유형별 구분**:

| 문서 유형 | rel_path 예시 | file_role(유도) | 비고 |
|---|---|---|---|
| XML 문서(dart3/dart4 본문) | `20231114001884.xml` | MAIN(`is_attachment=false`, `content_format="dart_xml"`) | `order_index`는 이 파일 안에서만 유효 |
| attachment XML | `20231114001884_01.xml` 등 | ATTACHMENT(`is_attachment=true`) | 본문과 동일한 규칙, 별도 카운터 |
| exchange HTML-in-.xml | `20230406800008.xml`(확장자만 xml) | MAIN(`is_attachment=false`, `content_format="kind_html"`) | 확장자로 유형 판단 금지 — `content_format`으로 구분 |
| viewer HTML(pdf+html) | `{rcept_no}_viewer.html` | VIEWER_HTML(`is_attachment=false`, `content_format="kind_html"`, rel_path가 `_viewer.html`로 끝남) | 이 문서의 유일한 파싱 대상(구조화된 노드가 나오는 곳) |
| PDF source artifact(pdf+html) | `{rcept_no}.pdf` | SOURCE_PDF(`is_attachment=false`, `content_format="pdf"`) | `source_files`엔 존재(해시 보존용)하지만 이 rel_path를 가리키는 `SourceLocation`은 **없음**(노드가 전혀 안 나옴) |

`file_role`은 위 표처럼 `is_attachment` + `content_format` + `rel_path` 접미사(`_viewer.html`)를 조합해야만 유도 가능하다 — 단일 enum 필드는 없다(gap, §1).

---

## 5. 파싱 경고·오류 형식

### ParserWarning (현재 필드)
`doc_id`(string), `rel_path`(string), `code`(enum, 아래 표), `severity`(`"info"`\|`"warning"`\|`"error"` — **`"fatal"` 없음**), `message`(자유 텍스트).

**gap**: `recoverable`, `recovery_used`, `details`(구조화 필드), `parser_version`, `source_locator` — 현재 `ParserWarning`엔 없다. 세부 정보는 `message` 자유 텍스트 안에 자연어로만 들어있다(구조화 안 됨). 복구 여부는 `ParseAuditRecord.used_sanitizer`/`used_encoding_recovery`/`used_fallback_parser`(파생 플래그, `parsing/audit.py`)로 문서 단위로만 알 수 있고, 경고 하나하나에 매달린 값은 아니다.

### warning code 전수(현재 9개, `WarningCode` enum)

| code | 의미 | severity | tier에 영향? |
|---|---|---|---|
| `sanitized_entity` | bare `&`/`<`를 엔티티로 치환 후 파싱 | info | **있음** — 하나라도 있으면 `structured`가 될 수 없고 `partial`로 강등(파싱 자체는 성공한 경우) |
| `encoding_declaration_mismatch` | 선언된 인코딩과 실제 디코딩에 쓴 인코딩이 다름 | warning | 없음 |
| `unknown_section_depth` | TITLE 번호 패턴 불인식, 스택 깊이로 level 추정 | info | 없음 |
| `table_merged_cell_ignored` | rowspan/colspan>1 셀 존재(이름과 달리 "무시"가 아니라 normalized_rows로 확장 처리함 — 메시지 문구가 오해 소지 있음, gap) | info | 없음 |
| `router_fallback_parser` | (정의만 됨) | info | 없음 — **현재 canonical_parser.py 어디서도 실제로 발생시키지 않는 예약 코드** |
| `content_type_mismatch` | sniff 결과가 doc_group 기대 파서와 다름 | warning | 없음(단, `ParseQuality.router_matched_expected_parser`를 `false`로 만듦 — tier 자체는 안 바뀜) |
| `parse_failed` | XML 파싱 자체 실패(sanitize 후에도 well-formed 아님) 또는 콘텐츠 타입 미인식 | error | **있음** — `parsed_ok=false`가 되어 tier가 강제로 `fallback` |
| `table_shape_mismatch` | row별 실제 컬럼 수가 최빈값과 다름 | info | 없음 |
| `table_metadata_uncertain` | 표 title/unit/period를 확실하게 못 채움 | info | 없음 |

**parse_quality.tier 판정 로직(현재 코드 그대로, `canonical_parser.parse_document`)**:
```
pdf+html 문서: tier = "partial" (항상, 경고 내용과 무관하게 고정)
그 외(xml):
  parsed_ok=False (parse_failed 있음)         -> tier = "fallback"
  parsed_ok=True  and sanitized_entity 없음    -> tier = "structured"
  parsed_ok=True  and sanitized_entity 있음    -> tier = "partial"
```
즉 tier를 낮추는 경고는 **`sanitized_entity`와 `parse_failed`(간접) 둘 뿐**이고, 나머지 6개 코드는 순수 정보성이다.

**"failed" 개념**: `ParseQuality.tier`의 값이 아니다. `parse_document()` 자체가 예외를 던져 DocumentIR이 아예 만들어지지 못한 경우를 가리키며, `scripts/run_full_corpus.py`가 이를 `failed_documents.jsonl`에 별도 기록한다(`parse_summary.json`에서는 tier 분포와 합쳐 4분류 — structured/partial/fallback/failed — 로 보고). **현재 권장 동작과 실제 동작이 이 지점에서 다르다**: B/C가 원하는 것처럼 `ParseQuality.tier`에 `"failed"`를 추가하려면 DocumentIR 스키마 변경(MAJOR 후보, §7)이 필요하다 — 이번 단계에서는 하지 않았다.

---

## 6. 저장 형식과 경로

**선택: doc_group별 JSONL.**

| 후보 | 판단 |
|---|---|
| 문서별 JSON(4204개 파일) | 기각 — 네트워크 마운트(WSL UNC)에서 파일 개수당 오버헤드가 지배적임을 실측 확인(gate 체크만 4204건 순회에 250초). 파일 4204개 추가 생성은 그 자체로 수 분 낭비 |
| Parquet | 기각(현재는) — `raw_cells`/`raw_rows`(중첩 list-of-struct) 컬럼 스키마 설계 비용 대비, B/C 둘 다 "문서 단위 스트리밍 순회"가 주 사용 패턴이라 컬럼기반 이점이 없음. 필요해지면 나중에 JSONL→Parquet 변환 스크립트를 추가하는 게 저비용 |
| **doc_group별 JSONL(선택)** | 스트리밍 읽기/쓰기 비용 최소, 한 줄 = 한 DocumentIR(스키마 검증 단위와 일치), doc_group 단위 분할로 B가 필요한 그룹만 골라 읽을 수 있음 |

**경로 구조**(실제 생성됨, `scripts/run_full_corpus.py` 기준):
```
data/artifacts/
├─ corpus_snapshot.json
├─ document_ir/
│  ├─ periodic.jsonl
│  ├─ major.jsonl
│  ├─ exchange.jsonl
│  └─ holding.jsonl
├─ parse_audit.jsonl
├─ parse_summary.json
├─ failed_documents.jsonl
└─ handoff/
   └─ representative_documents.jsonl
```

**고정 규칙**:
- 파일명: `{doc_group}.jsonl`(소문자, manifest의 `doc_group` 값 그대로)
- 인코딩: UTF-8, `ensure_ascii=False`(한글 원문 그대로 저장)
- 줄바꿈: `\n`(LF), 한 줄 = 한 DocumentIR(JSON), trailing newline 있음
- 압축: **없음(현재, gap)** — 전체 4204건 실측 완료: periodic 8.12GB, holding 424MB, major 50.7MB, exchange 24.9MB(합계 약 8.61GB, periodic이 94% 차지). 압축은 B/C 요구가 확인된 뒤 별도 결정
- 정렬 순서: `manifest.jsonl` 원본 등장 순서 그대로(파일 내 재정렬 없음)
- 필드 직렬화 순서: `document_ir_to_dict()`가 고정된 리터럴 순서로 dict를 만들어 항상 동일(결정론적, `dart_corpus.parsing.serialization` 참고)

---

## 7. parser_version 관리 방식

현재 값(수동 관리, 자동 계산 없음 — gap):
```
parser_version = "1.0.0"              # dart_corpus.parsing.document_ir.PARSER_VERSION
document_ir_schema_version = "1.0"    # dart_corpus.parsing.document_ir.DOCUMENTIR_SCHEMA_VERSION
document_ir_schema_v0.json            # 계약 문서/스키마 파일 자체의 버전(파일명에 박음, status=proposed)
```

**권장 Semantic Versioning 규칙**(제안 — 현재 코드는 이 규칙을 강제하지 않는다, 수동 판단 필요):
- **MAJOR**: 호환되지 않는 DocumentIR 의미 변경(필드 제거, 필드 의미 변경, tier 판정 로직 변경, node_id 생성 규칙 변경)
- **MINOR**: 하위 호환 가능한 필드/파싱 기능 추가(예: 이번에 추가한 `consolidation_basis`, `schema_version`/`parser_version`/`corpus_snapshot_id` 필드 추가는 MINOR 대상)
- **PATCH**: 출력 의미가 유지되는 버그 수정(예: sanitizer whitelist 정확도 개선처럼 "더 정확해질 뿐" 의미가 안 바뀌는 경우 — 다만 실제로는 결과값이 달라지므로 MINOR와의 경계가 모호할 수 있어 팀 논의 필요)

**코드 변경 없이 재실행**: `parser_version`/`document_ir_schema_version` 유지. `corpus_snapshot_id`도 원본(manifest/universe/raw)이 그대로면 유지.

**sanitizer 규칙 변경 / section hierarchy 규칙 변경 / table normalization 규칙 변경**: `parser_version` 증가 대상(결과가 달라질 수 있으므로 최소 PATCH, 의미 변화가 있으면 MINOR 이상).

**warning code 추가만 한 경우**: `WarningCode` enum에 값 추가 자체는 기존 소비자를 깨지 않으므로 MINOR. 단, JSON Schema(`schemas/document_ir_schema_v0.json`)의 `ParserWarning.code` enum 목록도 함께 갱신해야 한다(안 하면 schema validation이 새 코드를 거부함).

**schema 변경과 parser 변경 구분**: `document_ir_schema_version`은 "DocumentIR을 어떻게 JSON으로 담는가"(직렬화 형태)의 버전이고, `parser_version`은 "원문을 어떻게 해석하는가"(파싱 로직)의 버전이다. 직렬화 코드만 바뀌면(`serialization.py`) `document_ir_schema_version`만 올리고, 파싱 로직만 바뀌면(`canonical_parser.py`, `section_builder.py`, `table_serializer.py`) `parser_version`만 올린다. 대부분의 실제 변경은 후자다.

**corpus snapshot 변경과 parser version 변경 구분**: 완전히 독립된 축이다. `corpus_snapshot_id`는 원본 데이터(manifest.jsonl/universe.csv/raw 파일 바이트)가 바뀔 때만 바뀐다. `parser_version`은 파싱 로직 코드가 바뀔 때만 바뀐다. 같은 `corpus_snapshot_id`에 대해 `parser_version`이 다른 DocumentIR 여러 벌이 공존할 수 있고, 재현성을 위해 모든 artifact에 **항상 둘 다** 기록해야 한다.

**각 artifact에 기록되는 값**(현재 상태):
| 항목 | 현재 지원 여부 |
|---|---|
| `parser_version` | O — `DocumentIR.parser_version` |
| `document_ir_schema_version` | O — `DocumentIR.schema_version` |
| `corpus_snapshot_id` | O — `DocumentIR.corpus_snapshot_id`(직렬화 시점에 채움), `corpus_snapshot.json`, `parse_summary.json` |
| `source_locator_version` | **gap** — `SourceLocation`에 자체 버전 필드 없음(§4 필드 목록이 곧 버전 v0라고 취급 권장) |
| `code_revision`(git commit hash 등) | **gap** — 현재 어떤 artifact에도 기록 안 됨 |
| `config_hash` | **gap** — 애초에 파싱에 영향을 주는 "설정값" 자체가 `config.py`의 corpus_root 경로 하나뿐이라 별도 config 객체/해시가 없음. 재현성 키는 당분간 `(corpus_snapshot_id, parser_version)` 조합으로 대체 |

---

## 8. 대표 샘플(`data/artifacts/handoff/representative_documents.jsonl`) 선정 표

`scripts/generate_handoff_samples.py`로 생성. 11건, 모두 `schemas/document_ir_schema_v0.json` 기준 유효한 DocumentIR.

| doc_id | doc_group | schema_version | 선정 이유 |
|---|---|---|---|
| `periodic_20231114001884` | periodic | dart3.xsd | periodic dart3 + sanitizer 사용 + merged cell + shape mismatch + unknown_section_depth |
| `periodic_20241114001965` | periodic | dart4.xsd | periodic dart4(TE 셀 태그 우세) + sanitizer 사용 |
| `major_20230601000234` | major | dart3.xsd | major dart3 |
| `major_20251219000396` | major | dart4.xsd | major dart4 |
| `holding_20230103000123` | holding | dart3.xsd | holding dart3 |
| `holding_20240717000432` | holding | dart4.xsd | holding dart4 |
| `exchange_20230406800008` | exchange | n/a(html) | exchange HTML-in-.xml + 인코딩 선언 불일치(euc-kr 선언, 실제 utf-8) |
| `periodic_20260513000860` | periodic | n/a(pdf+html) | pdf+viewer HTML(PDF는 보존만, viewer.html이 파싱 대상) |
| `periodic_20240312000736` | periodic | - | 첨부 포함 문서(n_files=3) + sanitizer 사용(삼성전자 사업보고서) |
| `periodic_20240516000601` | periodic | dart4.xsd | TABLE-GROUP 내부 TITLE 승격 + 다중 header 표 + rowspan/colspan + sanitizer 사용 |
| `periodic_20260515002418` | periodic | - | fallback tier(ENG 속성값 내부 미이스케이프 큰따옴표로 XML well-formed 실패) |

---

## 9. B/C 사용 가이드

**Workstream B(Chunking/Retrieval)**: 전체 DocumentIR이 필요하다.
- 이미 생성된 artifact를 쓰거나: `data/artifacts/document_ir/{periodic,major,exchange,holding}.jsonl`
- 또는 동일 `parser_version`/설정으로 로컬 재생성: §10 실행 명령
- 사용할 `corpus_snapshot_id`/`parser_version`은 `data/artifacts/corpus_snapshot.json`과 `data/artifacts/parse_summary.json`에서 확인(둘 다 같은 값이어야 함 — 다르면 재현성 깨진 것이니 재생성 필요)

**Workstream C(Artifact Loader/Experiment Runner)**: 우선 스키마와 대표 샘플만 있으면 된다.
- `schemas/document_ir_schema_v0.json` + `data/artifacts/handoff/representative_documents.jsonl`(11건)
- schema validation 방법: 표준 JSON Schema validator(예: Python `jsonschema` 패키지) 사용 — `python -c "import json, jsonschema; schema=json.load(open('schemas/document_ir_schema_v0.json', encoding='utf-8')); [jsonschema.validate(json.loads(l), schema) for l in open('data/artifacts/handoff/representative_documents.jsonl', encoding='utf-8')]"`
- 전체 DocumentIR(`data/artifacts/document_ir/*.jsonl`)은 **통합 테스트 단계에서만** 연결한다 — 그 전까지는 대표 샘플로 Loader/Runner 뼈대를 개발

---

## 10. DocumentIR 생성 실행 명령

```bash
# 전체 4,204건 파싱 + Corpus Snapshot(해시 포함) — 실측 36.3분(snapshot 9.6분 + 파싱/audit 26.7분,
# corpus_snapshot_id=snap_7484a10220422056로 이미 1회 완료됨. 네트워크 마운트 I/O가 지배적이라 로컬 디스크면 더 빠를 수 있음)
PYTHONIOENCODING=utf-8 python3 scripts/run_full_corpus.py --out-dir data/artifacts

# 대표 샘플 11건만(수 분 내 완료)
PYTHONIOENCODING=utf-8 python3 scripts/generate_handoff_samples.py

# Parser Gold 후보 생성(parse_audit.jsonl 필요 — 위 전체 실행 이후)
PYTHONIOENCODING=utf-8 python3 scripts/generate_parser_gold_candidates.py --out-dir data/artifacts
```
Windows 환경에서 콘솔이 cp949(비 UTF-8)면 `PYTHONIOENCODING=utf-8` 없이 실행 시 한글 print 구간에서 `UnicodeEncodeError`가 날 수 있음(실제로 재현 확인) — 항상 붙일 것. 파일 쓰기 자체는 모두 `encoding="utf-8"`로 열려 있어 이 문제와 무관하다.

---

## 11. 전체 실행 결과(실측, 2026-08-04 완료)

`corpus_snapshot_id = snap_7484a10220422056`, `parser_version = "1.0.0"`, 4204/4204건 성공(0건 실패/누락).

| doc_group | structured | partial | fallback | 합계 |
|---|---|---|---|---|
| periodic | 0 | 975 | 79 | 1054 |
| major | 409 | 189 | 0 | 598 |
| exchange | 1469 | 0 | 0 | 1469 |
| holding | 815 | 268 | 0 | 1083 |
| **전체** | **2693** | **1432** | **79** | **4204** |

- periodic은 **100%가 partial 또는 fallback**(structured 0건) — 모든 periodic 문서에 `sanitized_entity` 또는 `parse_failed`가 하나 이상 있다는 뜻. exchange는 반대로 100% structured(HTML이 단순 구조라 sanitize 대상 자체가 없음).
- **원인 정밀 분해(실측, `parse_audit.jsonl` 전수 기준 — 오해 방지용, B/C 필독)**:

  | 원인 | 문서 수(periodic 1054건 중) | `text_preservation_ratio` 평균 | 실질 텍스트 손실 여부 |
  |---|---|---|---|
  | sanitizer 사용(bare `&`/`<`)만으로 tier가 partial로 강등 | 972 | **1.021** | **없음** — XML 파싱 자체는 완전히 성공, tier 판정 규칙(§5)이 `sanitized_entity` 유무에만 반응해서 강등될 뿐 |
  | pdf+html 형식이라 강제로 partial(원본 PDF는 안 읽음, viewer.html만) | 3 | 0.301 | 있음 — PDF 콘텐츠 자체가 산출물에 없음. 3건 중 2건은 viewer.html에 `<table>` 자체가 없어 `n_nodes=0`(ratio 0.0, 완전 손실 — §parse_failed 정정 및 `parse_failure_cases.jsonl` 참고), 1건만 표가 있어 실질 파싱됨(ratio ≈0.90) |
  | fallback(XML이 sanitize 후에도 well-formed 아님 → `_build_fallback_node`로 태그만 벗겨낸 raw text 1개 문단, 20000자 절단) | 79 | 0.139 | 있음(큼) — 구조 전부 소실 + 긴 문서는 20000자 이후 내용도 소실 |

  결론: **partial 975건 중 972건(99.7%)은 사실상 structured와 동등하다**(정보 손실 없이 tier만 규칙상 낮음). 실제로 검토가 필요한 대상은 fallback 79건 + pdf+html 3건, 총 **82건**뿐이다. "fallback parser 사용 문서"와 "parse failure 문서"는 현재 구현에서 **완전히 같은 집합**(79건)이다 — `router_fallback_parser`(라우터가 잘못된 파서를 골라서 나는 fallback)라는 별도 경로는 정의만 있고 실제로 발생한 적이 없다(§5).
- `avg_text_preservation_ratio = 0.776`
- warning code 분포: `sanitized_entity` 1508, `table_merged_cell_ignored` 4145, `table_metadata_uncertain` 4145, `table_shape_mismatch` 4140, `unknown_section_depth` 2648, `encoding_declaration_mismatch` 1469(=exchange 전체와 정확히 일치, exchange 100%가 이 경고를 가짐), `parse_failed` 81 **[2026-08-04 정정]** — 이전 버전은 "fallback 79건 중 2건이 첨부 XML 2개 이상 실패로 중복 계상"이라고 서술했으나 **틀림**(원본 `document_ir/periodic.jsonl` 전수 재대조 결과, fallback 79건은 문서당 `parse_failed` 정확히 1개씩, 합 79). 실제 구성은 **79(fallback, `ET.fromstring` 파싱 실패) + 2(별도 집합, tier는 `partial` 그대로 유지)** = 81. 이 2건은 `doc.file_format=="pdf+html"` 문서의 `{rcept_no}_viewer.html`에 `<table>` 태그가 0개라 `parse_kind_html_text()`가 경고만 남기고(`parsed_ok` 플래그를 안 건드림) tier를 fallback으로 안 내림 — `n_nodes=0`, `text_preservation_ratio=0.0`(완전 손실). doc_id 및 상세는 `data/artifacts/handoff/parse_failure_cases.jsonl` 참고
- 상세 근거: `data/artifacts/parse_summary.json`(doc_group/warning code별 분포 전체), `data/artifacts/parse_audit.jsonl`(문서별)
- `failed_documents.jsonl`은 0바이트 — 파싱 자체가 예외로 죽은 문서는 없음
- Parser Gold 후보 90건 생성 완료(`data/artifacts/parser_gold_candidates.jsonl` + 검수 template `data/artifacts/parser_gold_annotation_template.csv`) — **아직 사람 검수 전, gold 정답 아님**

## 12. 재현성(Reproducibility)

두 단계로 구분한다.

- **A. Semantic reproducibility**: 동일 doc_id 목록, 동일 section/table/paragraph 수, 동일
  ID와 source_locator, 동일 parse_quality/warning, canonicalized DocumentIR hash 일치.
- **B. Byte reproducibility**: 동일 JSONL byte stream, 동일 artifact SHA-256(파일 자체가
  바이트 단위로 완전히 같음).

**점검 결과(현재 코드 기준)**:

| 점검 항목 | 상태 |
|---|---|
| 문서 처리 순서 | **deterministic** — `ManifestLoader.load()`가 `manifest.jsonl`을 줄 순서 그대로 읽고, `run_full_corpus.py`도 그 리스트를 그대로 순회(정렬/셔플 없음) |
| doc_group별 출력 순서 | **deterministic** — 그룹 파일 안에서 `manifest.jsonl` 원본 등장 순서 그대로 |
| JSON key 순서 | **deterministic** — `document_ir_to_dict()`가 고정 리터럴 순서로 dict를 만듦(입력에 따라 달라지는 dict/set 순회 없음) |
| UTF-8/newline | **고정** — 모든 파일 `encoding="utf-8"`로 열고 `\n`으로 씀 |
| 실행 시점 의존 필드가 DocumentIR 본문에 있는가 | **없음** — `DocumentIR`/`corpus_snapshot.json` 어디에도 timestamp 필드 없음(코드 전수 grep 확인). `parse_summary.json`의 `elapsed_s`/`docs_per_s`만 실행마다 달라지는데, 이건 DocumentIR 본문이 아니라 별도 로그성 요약 파일이라 재현성 비교 대상에서 제외해야 함 |
| 절대 로컬 경로 출력 여부 | **없음** — `SourceLocation`/`SourceFileIR`은 `rel_path`(상대경로)만 저장. `sys.path.insert(str(Path(__file__)...))`처럼 스크립트 내부에서만 쓰이는 절대경로는 어떤 JSON 출력에도 안 들어감(전수 grep 확인) |
| ID 생성에 Python 내장 `hash()` 사용 여부 | **미사용** — `make_ir_node_id()`는 `doc_id`/`rel_path`/`order_index` 문자열 조합일 뿐, 내장 `hash()` 호출이 코드베이스 어디에도 없음(전수 grep 확인, `PYTHONHASHSEED`에 영향 안 받음) |
| set/dict 순회 순서 의존 여부 | **없음(위험 지점은 있었으나 이미 안전)** — `{w.code.value for w in warnings}`처럼 문자열 `set`을 만드는 곳은 `sorted()`로 즉시 고정한 뒤에만 씀(`audit.py`, `gold_candidates.py`). `dict`(Python 3.7+ 삽입순서 보장)는 위험하지 않음 — 문제는 `set`/`frozenset`의 문자열 해시가 `PYTHONHASHSEED`로 랜덤화될 수 있다는 점인데, 출력에 영향을 주기 전에 항상 정렬됨 |
| parser config가 hash로 기록되는가 | **이번에 추가함(gap이었음)** — `parser_config_hash`(§13). 이전에는 `parser_version` 수동 관리뿐이라 로직이 바뀌었는데 버전을 안 올리는 실수를 잡을 방법이 없었음 |
| dependency 버전이 고정되는가 | **부분적** — `pyproject.toml`은 범위(`>=`)만 고정. `requirements-lock.txt`(신규)가 이번 전체 실행 당시 실제 버전을 기록하지만, 이건 "패키지 관리자 lock file"이 아니라 수동 스냅샷이라 강제력은 없음(gap) |

**결론**: 현재 코드는 **A(semantic reproducibility)를 보장하도록 설계되어 있고(§13 canonical hash로 검증 가능)**, 실제로 두 개의 다른 환경에서 재실행해 비교한 적은 없다(단일 실행만 존재). **B(byte reproducibility)는 미검증** — `requirements-lock.txt`를 그대로 쓰고 동일 OS/파일시스템이면 이론상 바이트까지 같을 가능성이 높지만(dict 순서/정렬 로직이 전부 고정이므로), 줄바꿈 방식이 다른 OS(예: 텍스트 모드 `\r\n` 자동 변환)에서 깨질 여지가 있어 "보장"이라고 말할 수준은 아니다. 이번 단계에서 별도 코드 수정은 하지 않았다(발견된 위험 지점이 이미 다 안전하게 처리되어 있었음) — 유일한 실질적 gap은 dependency 정확한 고정이었고, `requirements-lock.txt` 추가로 대응했다.

## 13. Canonical Hash

재현성 검증을 8.61GB 전체 파일 비교 없이 하기 위한 것. `dart_corpus.parsing.canonical_hash` 모듈.

**규칙**: UTF-8, JSON key 정렬(`sort_keys=True`), 공백 제거(`separators=(",", ":")`), 리스트
순서는 원본 그대로(재정렬 안 함 — 원본 자체가 이미 결정론적 순서라 재정렬할 필요가 없음),
SHA-256. 실행 시각/절대경로 등 비결정적 필드는 **애초에 DocumentIR에 없으므로**(§12) 별도
제외 로직이 필요 없었다.

- `document_ir_hash`: 문서 하나의 canonical hash(= `sha256(canonical_json(document_ir_to_dict(ir)))`)
- `group_artifact_hash`: doc_group별 `(doc_id, document_ir_hash)` 목록을 **doc_id로 정렬한 뒤** canonical hash
- `corpus_document_ir_hash`: 전체 4204건의 `(doc_id, document_ir_hash)`를 doc_id로 정렬한 뒤 canonical hash

정렬 기준(`doc_id`)을 쓰기 때문에 두 실행에서 문서 처리 **순서**가 달라도(예: 병렬화해서
순서가 섞여도) 결과 hash는 같다 — 순서 자체의 재현성(§12 "문서 처리 순서")과는 별개로,
내용의 재현성만 검증한다.

`scripts/compute_document_ir_hashes.py`가 `document_ir/*.jsonl`을 한 줄씩 스트리밍으로 읽어
계산하고(전체를 메모리에 올리지 않음), 결과를 작은 파일 하나로 저장한다:
`data/artifacts/handoff/document_ir_hash_manifest.json`.

**실측값(2026-08-04, corpus_snapshot_id=snap_7484a10220422056)**: `data/artifacts/handoff/document_ir_hash_manifest.json` 참고(`group_hashes`, `corpus_document_ir_hash`, `canonicalization_version="v1"`, `hash_algorithm="sha256"`).

## 14. 알려진 gap 요약

| 항목 | 상태 |
|---|---|
| `source_file_id` | 없음 — `rel_path`로 대체 |
| `file_role` enum(MAIN/ATTACHMENT/VIEWER_HTML/SOURCE_PDF) | 없음 — `is_attachment`+`content_format`+`rel_path` 접미사 조합으로 유도 |
| `section_path` 문자열/리스트 | 없음 — `section_hierarchy`+자기 title로 소비자가 구성 |
| `table_group_id`(≠`table_id`) | 없음 — 물리적 TABLE 여러 개가 하나의 `table_id`로 합쳐짐 |
| `row_id` | 없음 — `(table_id, row_index)`로 대체 |
| `xml_xpath`/`logical_path` | 없음 |
| `table_index`/`row_index`/`col_index`(source_locator 레벨) | 없음(`row`/`col`은 `TableCellIR`에만 있음) |
| `character_start`/`character_end` | 없음 |
| `page_number` | 없음(PDF 자체를 파싱 안 함) |
| `byte_offset` | 필드는 있으나 항상 `null`(미구현) |
| `ParserWarning.recoverable`/`recovery_used`/`details`/`parser_version`/`source_locator` | 없음(`message` 자유 텍스트에만 정보 있음) |
| `parse_quality.tier == "failed"` | 없음(별도 개념 — `failed_documents.jsonl`) |
| `router_fallback_parser` warning code | enum에 정의만 되어 있고 실제로 발생 안 함(예약 코드) |
| `source_locator_version` | 없음(§4 필드 목록 자체가 v0라고 취급 권장) |
| `code_revision` | `a_handoff_manifest.json`에 필드는 있으나, 이 manifest를 만든 시점엔 git 저장소가 아직 없어서 `null` — 최초 commit 후 재생성 필요 |
| `parser_config_hash` | **이번에 추가함**(§13) — 더 이상 gap 아님 |
| dependency 정확한 버전 고정 | 부분적 — `requirements-lock.txt`(신규)는 수동 스냅샷, 패키지 관리자 lock file 수준의 강제력은 없음 |
| Byte reproducibility(동일 JSONL 바이트) | 미검증(§12) — 설계상 위험 요소는 없으나 실제 교차환경 검증 안 함 |
| JSONL 압축 | 없음(비압축, 실측 약 8.61GB) |
| Source-level Dedup Metadata(content fingerprint, duplicate_group_id 등) | **이번 단계 구현 대상 아님**(명시적 범위 제외) |
