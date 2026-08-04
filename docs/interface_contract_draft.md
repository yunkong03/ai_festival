# 최소 인터페이스 계약 초안 (병렬 개발 전 합의 대상)

> 이 문서는 **필드 수준 계약**이다. 구현 세부(어느 파일에 둘지, 어떤 라이브러리를 쓸지)는 각 Workstream 담당자가 결정한다. 여기서 고정하는 것은 **타입 이름, 필드명, 필드 타입, 소유 Workstream**뿐이다. 첫 회의에서 이 계약에 합의해야 A/B/C가 병렬로 작업을 시작할 수 있다.

표기: 소유 Workstream이 해당 타입을 생성하는 쪽. 다른 Workstream은 소비만 한다(임의로 필드를 추가/변경하지 않는다 — 변경이 필요하면 계약 자체를 갱신하고 팀에 공지).

## 1. `DocumentRecord` — 소유: A

manifest.jsonl 한 행 + **파생 필드 1개**. 기존 계획(`2026-07-29-mvp-fact-store.md` Task 2)의 정의에 `derived_subtype`을 추가한다.

**[확인] `derived_subtype`이 필요한 이유**: `major` 598건은 `doc_subtype`이 **전부 빈 문자열**이다(실측). Metadata Filter가 "유상증자 공시만"처럼 좁히려면 `report_nm`(예: `주요사항보고서(유상증자결정)`, `[기재정정]주요사항보고서(전환사채권발행결정)`)에서 유형을 파싱해 채워야 한다. 규칙: 정정 태그(`[...]`) 제거 → 괄호 안 문자열 추출 → 없으면 `doc_subtype` 그대로. 이 필드는 **A가 로딩 시점에 채우고** B의 Metadata Filter가 소비한다.

```python
@dataclass(frozen=True)
class DocumentRecord:
    doc_id: str            # "{doc_group}_{rcept_no}"
    corp_code: str          # 8자리, leading zero 보존
    corp_name: str
    listed_name: str
    stock_code: str          # 6자리, leading zero 보존
    industry: str
    sector: str
    doc_group: str           # "periodic" | "major" | "exchange" | "holding"
    doc_subtype: str          # 주의: major는 전 건 "" (빈 문자열)
    derived_subtype: str       # 파생 — major는 report_nm에서 추출(예: "유상증자결정"), 그 외는 doc_subtype 복사
    report_nm: str
    rcept_no: str
    rcept_dt: str             # YYYYMMDD
    flr_nm: str
    is_correction: bool
    file_path: str            # manifest 상대경로, 조인 키
    file_format: str          # "xml" | "pdf+html"
    n_files: int
    base_year: int | None
    base_month: int | None
```

## 2. `ParsedDocument` / `Chunk` / `Evidence` — 소유: A

기존 계획(Task 4)의 정의를 **전체 코퍼스 구조 보존 RAG(`hybrid_architecture_proposal.md` §4, §7) 지원을 위해 확장**한다. **`Chunk.kind`에 `PARAGRAPH`와 `SECTION`이 추가**되므로(§`team_workstreams.md` A 범위) B는 `kind != ChunkKind.TABLE`인 chunk(PARAGRAPH/SECTION)를 BM25/임베딩 검색 대상으로 삼는다. `SECTION` kind는 섹션 전체(제목+하위 문단 요약 또는 첫 문단)를 대표하는 상위 chunk로, §7.2 계층형 Retrieval의 "섹션 단계"에서 1차 후보를 좁히는 용도다 — **계층형 Retrieval과 `SECTION` chunk 생성 둘 다 MVP 필수**다(§5.1, 5.29GB 규모에서 flat 검색이 성립하지 않기 때문). **`Chunk.section_hierarchy`와 `Chunk.table_metadata`가 신규 필드**다 — 기존 `2026-07-29-mvp-fact-store.md` Task 4의 `Chunk`/`base.py` 구현에는 없으므로 Workstream A가 확장 구현해야 한다. **범위는 `exchange`/`major`/`periodic`/`holding` 4개 doc_group 전체**이며 정기공시에만 국한하지 않는다 — 정밀 Fact Extractor가 없는 문서(주요사항보고서 BW/EB, 지분공시 세부 등)도 반드시 Chunk를 생성해 검색 대상에 포함한다.

```python
class ChunkKind(str, Enum):
    SECTION = "section"       # 섹션 전체를 대표하는 상위 chunk (계층형 검색의 1차 후보 좁히기용)
    TABLE = "table"
    PARAGRAPH = "paragraph"

@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    chunk_id: str
    row: int
    col: int
    label: str | None
    value: str

@dataclass(frozen=True)
class TableMetadata:
    """표 chunk에만 부착. Context Bundling(§7.4)과 연결/별도 구분(Q1)에 필수."""
    title: str | None
    row_headers: list[str]
    col_headers: list[str]
    unit: str | None                    # 예: "백만원", "원", "%"
    period: str | None                    # 예: "제56기(2024.01.01~2024.12.31)"
    consolidation_basis: str | None        # "연결" | "별도" | None
                                              # [확인] 1순위 판별은 section_hierarchy (예: "2-2. 연결 포괄손익계산서"),
                                              # 표 헤더 추론은 섹션 제목에 신호가 없을 때만 쓰는 2순위 fallback

@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    rel_path: str
    section_path: str
    section_hierarchy: list[str]      # 문서→장→절 breadcrumb, TITLE 텍스트 기반 (사람이 읽는 섹션 제목)
                                          # [확인] 정기공시는 "I. 회사의 개요" / "II. 사업의 내용" / "3. 원재료 및 생산설비"
                                          # 형태로 TITLE이 명확 — 추출 실현성 확인됨
    is_attachment: bool                 # [확인] periodic n_files>1 문서는 본문({rcept}.xml)과 첨부({rcept}_00760.xml 등)가 섞여 있고
                                          # 파일명 정렬 시 첨부가 먼저 온다. 둘 다 색인하되 본문 우선순위를 높이기 위해 표시
    kind: ChunkKind
    index: int
    text: str
    evidences: list[Evidence]
    table_metadata: TableMetadata | None = None   # kind==TABLE일 때만 채움

@dataclass
class ParsedDocument:
    doc_id: str
    chunks: list[Chunk]
    warnings: list[ParserWarning]
```

## 3. `ExtractedFact` — 소유: A

기존 계획(Task 8)의 정의 재사용. **소비**: C의 Calculator(비교/증감률 입력), B의 FACT_LOOKUP 조회(metadata 매칭).

```python
@dataclass(frozen=True)
class ExtractedFact:
    doc_id: str
    fact_type: str        # 예: "investment_amount_krw", "revenue_consolidated_krw", "contract_name"
    value: object          # 확정된 Python 값 (int, str 등 fact_type에 따름)
    raw_value: str          # 원문 텍스트
    evidence_id: str
    chunk_id: str
```

## 4. `FilingEvent` — 소유: A (신규)

정정·체결→해지처럼 "문서 간 관계로만 표현되는 사실"을 나타낸다. `VersionResolutionResult`(정정)와 계약 이벤트(체결/해지)를 공통 형태로 다룬다.

```python
class FilingEventType(str, Enum):
    CORRECTION = "correction"
    CONTRACT_SIGNED = "contract_signed"
    CONTRACT_TERMINATED = "contract_terminated"
    CAPITAL_RAISE = "capital_raise"

@dataclass(frozen=True)
class FilingEvent:
    event_id: str
    doc_id: str
    event_type: FilingEventType
    related_doc_id: str | None   # 정정→원본 doc_id, 해지→체결 doc_id
    status: str | None            # LinkStatus.value, 정정/계약연결 모두 재사용
    occurred_on: str               # rcept_dt 기준 YYYYMMDD
    reason: str                     # 매칭 근거 요약 (사람이 읽는 설명)
```

## 5. `VersionResolutionResult` — 소유: A

기존 `CorrectionLink`을 이 이름으로 통일(사용자 요청 인터페이스 이름). 필드는 `LinkStatus` enum(`resolved`/`probable`/`ambiguous`/`unresolved`/`manually_resolved`)을 그대로 사용.

```python
@dataclass(frozen=True)
class VersionResolutionResult:
    doc_id: str                    # 정정 문서의 doc_id
    status: LinkStatus
    resolved_doc_id: str | None   # 확정/추정된 원본 doc_id (resolved/probable/manually_resolved일 때만)
    candidates: tuple[str, ...]
    reason: str
```

## 6. `RetrievalQuery` — 소유: B

Query Analyzer의 출력. **§7.1(Metadata-First Filtering) 원칙에 따라 `corp_names`~`consolidation_basis`까지가 검색 전에 먼저 적용되는 하드 필터**다 — 이 필터 없이 전체 청크를 바로 검색하지 않는다.

```python
@dataclass
class RetrievalQuery:
    query_id: str
    raw_question: str
    corp_names: list[str]              # CorpAliasIndex.resolve() 결과 (canonical corp_name)
    doc_group_filter: list[str] | None
    doc_subtype_filter: list[str] | None   # DocumentRecord.derived_subtype과 매칭 (major는 doc_subtype이 비어 있으므로 파생값 사용)
    date_range: tuple[str, str] | None  # (YYYYMMDD, YYYYMMDD), 코퍼스 범위(20230101~20260331) 밖이면 사전 플래그
    fact_types: list[str] | None         # FACT_LOOKUP 힌트, ExtractedFact.fact_type과 매칭
    consolidation_basis: str | None       # "연결" | "별도" | None — 정기공시 재무제표 표 필터(Q1 대응)
    task_routes: list[str]                # ["FACT_LOOKUP", "EVIDENCE_SUMMARY", ...] — Task Router 판단 결과
    out_of_scope: bool                    # 기간/기업이 코퍼스 밖이면 True — LIMIT_OR_CLARIFICATION 즉시 트리거
```

## 7. `RetrievalResult` — 소유: B

**§7.2(계층형 Retrieval)/§7.3(BM25+Dense+RRF)/§7.4(Context Bundling) 원칙을 반영**한다. `facts`/`chunks`는 최종적으로 좁혀진 evidence 단계 결과이며, `retrieval_trace`가 문서→섹션→표/문단 각 단계에서 몇 건이 후보로 남았는지(Document/Section Recall@k 측정에 사용, `evaluation_strategy.md` 참조)와 각 검색기(BM25/Dense) 기여도를 기록한다.

```python
@dataclass
class RetrievalStageTrace:
    stage: str                  # "document" | "section" | "chunk" | "evidence"
    candidate_count: int
    method: str                  # "metadata_filter" | "bm25" | "dense" | "rrf_combined"

@dataclass
class RetrievalResult:
    query_id: str
    facts: list[ExtractedFact]
    chunks: list[Chunk]              # 근거 청크 — SECTION/TABLE/PARAGRAPH 모두 포함(문단만이 아님).
                                          # Context Bundling이 적용된 상태로 반환(적용 전이면 원본 그대로)
    events: list[FilingEvent]
    coverage_note: str | None         # 근거가 부족하거나 못 찾은 부분에 대한 명시적 서술 (LIMIT_OR_CLARIFICATION 입력)
    retrieval_trace: list[RetrievalStageTrace]   # 계층형 검색의 단계별 기록, think_trace/평가 지표 산출용
```

## 8. `TaskPlan` — 소유: B(생성) / C(실행)

**이 구조가 유일한 실행 모델이다.** 자유형 ReAct(매 스텝 LLM이 다음 행동을 즉흥 결정)는 채택하지 않는다(`hybrid_architecture_proposal.md` §3) — `TaskPlan.steps`는 Task Router가 질의 분석 시점에 전부 확정하고, C의 Synthesizer는 이 계획을 순서대로 실행만 한다.

```python
@dataclass
class TaskPlanStep:
    route: str                # "FACT_LOOKUP" | "EVIDENCE_SUMMARY" | "MULTI_DOCUMENT_ANALYSIS" | "LIMIT_OR_CLARIFICATION"
    depends_on: list[int]       # 이전 step 인덱스 (조합 실행 순서)
    input_ref: str               # 어떤 RetrievalResult 하위집합을 쓸지 참조

@dataclass
class TaskPlan:
    query_id: str
    routes: list[str]              # 사용된 고유 route 집합
    steps: list[TaskPlanStep]
```

## 9. `CalculationRecord` — 소유: C

**전량 Python으로 계산한 결과만 담는다.** 금액 파싱, 단위 정규화, 합계, 차이, 증감률, 비율, 비교 — 어떤 연산도 HyperCLOVA X에 위임하지 않는다(`hybrid_architecture_proposal.md` §8). HyperCLOVA X는 이 레코드를 입력받아 자연어로 설명하는 역할만 한다.

```python
class CalculationOp(str, Enum):
    DIFF = "diff"
    PCT_CHANGE = "pct_change"
    SUM = "sum"
    COMPARE = "compare"

@dataclass(frozen=True)
class CalculationRecord:
    calculation_id: str
    operation: CalculationOp
    input_evidence_ids: list[str]    # ExtractedFact.evidence_id 참조 — 계산도 evidence까지 역추적 가능해야 함
    result: float | int | str
    formula_note: str                  # 사람이 읽는 계산식 설명 (예: "(268,000,000,000 - 211,800,000,000) / 211,800,000,000")
```

## 10. `VerificationResult` — 소유: C

```python
@dataclass(frozen=True)
class VerificationResult:
    query_id: str
    hallucination_flag: bool
    unsupported_claims: list[str]   # retrieved_context에 근거 없는 answer 내 주장
    numeric_mismatch: list[str]        # answer에 등장한 숫자 중 retrieved_context 원문과 대조해 불일치한 것들
                                          # (Calculator 결과든 RAG가 인용한 숫자든 예외 없이 대조 — §8)
    citation_complete: bool
    safety_flag: bool                  # 프롬프트 인젝션·부적절 입출력 탐지 시 True
```

## 11. `FinalResponse` — 소유: C

공식 API `GET /answer` 응답 스키마와 1:1 대응.

```python
@dataclass
class FinalResponse:
    question_id: str
    question: str
    retrieved_context: str    # RetrievalResult를 사람이 읽는 형태로 직렬화
    think_trace: dict           # 구조화된 실행기록 — 비공개 CoT 금지, §api_submission_plan.md 참조
    answer: str
```

## 12. `AuditRecord` — 소유: C (팀 내부 전용, 제출물 아님)

```python
@dataclass
class AuditRecord:
    question_id: str
    latency_ms: int
    routes_used: list[str]
    facts_used: list[str]        # evidence_id 목록
    errors: list[str]
```

## 경계 규칙

1. `DocumentRecord`/`Chunk`/`Evidence`/`ExtractedFact`/`FilingEvent`/`VersionResolutionResult`는 **A만 생성**한다. B/C는 소비만 하고 필드를 임의로 늘리지 않는다 — 필요한 필드가 없으면 A에 요청해 계약을 갱신한다.
2. `RetrievalQuery`/`RetrievalResult`/`TaskPlan`(routes 결정까지)은 **B만 생성**한다.
3. `CalculationRecord`/`VerificationResult`/`FinalResponse`/`AuditRecord`는 **C만 생성**한다.
4. 모든 "근거"류 필드(`evidence_id`, `chunk_id`, `input_evidence_ids`)는 A가 만든 ID 형식을 그대로 참조한다 — B/C가 자체 ID 체계를 새로 만들지 않는다.
5. 이 계약에 없는 필드가 필요해지면 개인 임의 변경 대신 **이 문서를 갱신하고 팀에 공지**한다.
