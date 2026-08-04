# 개발 로드맵

> 기준일: 2026-07-29 (오늘). 공식 일정: 과제 세부공지 07.27(완료) → 예선기간 07.27~09.06 → 예선평가 09.07~09.30 → 결과발표 10.01. **제출 마감까지 약 5.5주.**

## 원칙

첫 개발 목표는 "전체 기능 완성"이 아니라 **Vertical Slice 3개**(질의 하나가 API 응답까지 실제로 흐르는 최소 경로)를 순서대로 완성하는 것이다:

1. **거래소공시 단일 금액 조회** (FACT_LOOKUP만) — 가장 단순, Workstream A 기존 자산으로 즉시 가능
2. **사업보고서/분기보고서 Open 요약** (EVIDENCE_SUMMARY) — 문단 chunk + retrieval + HyperCLOVA X 요약, A/B/C 3자 통합이 처음 필요
3. **계약 체결 후 해지 여부** (FACT_LOOKUP + MULTI_DOCUMENT_ANALYSIS) — Task Router가 두 경로를 조합해야 하는 가장 복합적인 슬라이스, Hybrid 구조의 실질 가치를 증명

이 순서는 "쉬운 것부터"가 아니라 **"파이프라인이 실제로 끝까지 흐르는가"를 가장 빨리, 가장 자주 검증하기 위한 순서**다. 각 슬라이스 완성 시점마다 API로 실제 호출해 응답이 나오는지 확인한다.

**이 로드맵을 관통하는 우선순위 원칙** (`hybrid_architecture_proposal.md` §5.1): MVP 필수(전체 구조 보존 Parsing + Metadata Filter + **계층형 축소** + 전체 문서 BM25 검색 + 기존 핵심 Fact Store/Calculator + HyperCLOVA X 근거 답변 + Citation)를 **다른 무엇보다 먼저** 전체 코퍼스 대상으로 세운다. Vertical Slice는 이 baseline 위에서 기능을 검증하는 방식이지, baseline 자체를 생략하고 3개 슬라이스만 좁게 파는 것이 아니다.

**[확인] 규모가 이 일정의 최대 변수**: 코퍼스는 **5.29GB**이고 그중 periodic이 5.05GB(95%)다. XML 평균 3.44MB·최대 30.7MB. 따라서 **Week 0~1의 성패는 "파싱·색인 파이프라인이 이 규모를 감당하는가"** 하나에 달려 있으며, 이것이 늦어지면 뒤의 모든 것이 밀린다. 5주 안에 3인이 이 규모를 다루려면:
> - 인메모리 일괄 처리 금지 — 문서 단위 스트리밍 + 중간 산출물 디스크 저장
> - BM25는 디스크 기반 역색인 엔진(SQLite FTS5/Tantivy/Lucene 계열). 순수 파이썬 인메모리 구현 금지
> - **[확인 — 주최 측 공식 답변] Dense Retrieval은 허용, 임베딩 모델은 BGE-M3·multilingual-e5 등 자유 선택**(생성만 HyperCLOVA X 제약). 단 전량 즉시 적용하지 않는다 — periodic 사업내용·원재료 및 생산설비·위험요인·연구개발활동 섹션부터 BM25+RRF로 적용하고, **Recall 개선이 실측되면** 확대한다
> - Week 0에 **periodic 1개 기업(13건) 파일럿**으로 파싱→색인 처리량을 먼저 측정하고, 전체 소요시간을 추정한 뒤 범위를 확정한다

## 주차별 계획

### Week 0 — 07.29 ~ 08.03: 합의와 착수

- 첫 회의: `meeting_decisions.md` 체크리스트 확정(아키텍처, 인터페이스 계약, 워크스트림, 개발 환경, **BM25 엔진 선택**)
- `interface_contract_draft.md`를 팀 합의 버전으로 확정 (Python 코드로 실제 파일화, `Chunk`에 `SECTION`/`section_hierarchy`/`is_attachment`/`table_metadata`, `DocumentRecord`에 `derived_subtype` 포함해서 시작)
- **[최우선] 규모 파일럿**: periodic 1개 기업(13건, ~45MB)으로 파싱→청킹→BM25 색인을 끝까지 돌려 **처리량(MB/분)과 청크 수를 측정**한다. 여기서 나온 수치로 전체 5.29GB 소요시간을 추정하고, 감당 안 되면 그 자리에서 범위(청킹 단위, Dense 적용 여부)를 조정한다. **이 측정 없이 Week 1로 넘어가지 않는다**
- A: `derived_subtype` 생성(0-b) + periodic 본문/첨부 구분(0-c) — 둘 다 난이도 낮고 B가 의존하므로 Week 0 내 완료. 이어서 4개 doc_group 대상 SECTION/PARAGRAPH chunk 확장 착수(0). 기존 `2026-07-29-mvp-fact-store.md` Task 1~11은 §6 결함(placeholder fixture 제거, FactStore 명명 정정) 반영해 병행
- B: BM25 엔진 선정·검증(파일럿 참여), retrieval 모듈 골격
- C: API 서버 골격, HyperCLOVA X API 키/사용법 확인
- 리스크 체크: `risk_register.md` 초안 검토

### Week 1 — 08.04 ~ 08.10

- **08.06 오프라인 설명회 — 팀당 최소 1명 필참** (네이버클라우드 소개·사용법, 과제 소개, 테크 세션, Q&A)
- A: 거래소공시 3종 Fact Store 완성 (기존 계획 완주). 4개 doc_group 전체 구조 보존 Parsing 완료 목표 — **작은 것부터**: exchange(15MB)→major(22MB)→holding(207MB)→periodic(5,047MB) 순으로 진행해 파이프라인을 작은 규모에서 먼저 검증
- B: **전체 문서 BM25 색인 구축**(§5.1·§7.3) — A가 doc_group을 끝내는 순서대로 색인에 편입. `RetrievalQuery`/Metadata Filtering(§7.1, `derived_subtype` 사용), FACT_LOOKUP metadata 매칭 조회
- C: `GET /answer` API 골격 + `FinalResponse` 스키마 고정, HyperCLOVA X 최소 연동 테스트. **eval set 초기 제작 착수**(A가 파싱에 묶여 있으므로 C가 더 맡음 — `team_workstreams.md` 밸런스 조정 1-b)
- **마일스톤: Vertical Slice 1(거래소공시 단일 금액 조회) API 끝까지 응답 + exchange/major/holding 3개 group BM25 색인 완료.** periodic(5GB)은 Week 2까지 이어질 수 있음 — 그 경우에도 나머지 3개 group은 이미 검색 가능한 상태를 유지

### Week 2 — 08.11 ~ 08.17

- A: 정기공시 재무제표 핵심 3계정 추출 착수(Q1 — **연결/별도는 섹션 제목으로 판별**), 주요사항보고서 **자기주식(338건, major 최다)** 추출 착수
- B: **periodic 포함 4개 doc_group 전체 BM25 색인 완료(MVP 필수 마무리)** + **계층형 축소 구현**(문서→섹션→청크, §7.2 — MVP 필수로 상향됨). Task Router 1차(단일 경로 판별, BM25 fallback 포함)
- C: Synthesizer 1차(FACT_LOOKUP 결과만 조합), Citation 포맷 확정, eval set 계속
- 팀 공통: eval set 1차분 — **참고 질의 6종 유형뿐 아니라 재무주석·위험요인·지분공시 변동사유 등 RAG 전용 항목, 그리고 "BW 발행 내역"처럼 코퍼스에 데이터가 없는 케이스도 포함**(`evaluation_strategy.md`)

### Week 3 — 08.18 ~ 08.24

- A: major 정밀 추출 확대(유상증자 → 상각형조건부자본증권 → CB), 계약명/투자명 fact 추가(Q5 준비), 지분공시 **합계 행** 정밀 지원 착수
- B: EVIDENCE_SUMMARY 경로가 전체 BM25 + 계층형 축소 기반으로 완성(MVP 필수 확정). 여유가 있으면 **[가능하면 추가]** Dense 1단계 착수(§7.3) — **periodic 사업내용·원재료 및 생산설비·위험요인·연구개발활동 섹션만** BGE-M3/multilingual-e5로 임베딩해 BM25+RRF 결합, eval set으로 Recall@k 전/후 비교. 개선 확인되면 Week 4~5에 확대, 아니면 그 상태로 고정. Context Bundling 1차(§7.4 — 표 metadata·섹션 제목 결합)
- C: HyperCLOVA X 기반 EVIDENCE_SUMMARY 요약 통합, **답변 내 숫자를 원문과 대조하는 Verifier 체크 착수**(`hybrid_architecture_proposal.md` §8)
- **마일스톤: Vertical Slice 2(사업보고서/분기보고서 Open 요약) API 끝까지 응답 — 정기공시뿐 아니라 4개 doc_group 어디를 물어도 최소 BM25 근거로 응답 가능한 상태**

### Week 4 — 08.25 ~ 08.31

- A: 계약명 기반 체결→해지 `FilingEvent` 연결, `CorrectionResolver` 2차 신호(계약명/투자명) 보강
- B: Task Router 다중 경로 조합(FACT_LOOKUP + MULTI_DOCUMENT_ANALYSIS, FACT_LOOKUP 실패 시 EVIDENCE_SUMMARY fallback) 지원
- C: Verifier 완성(hallucination 체크 + 숫자 대조 + citation 완전성), LIMIT_OR_CLARIFICATION 가드레일(기간/기업 밖, 근거 부족, 투자의견 요청, 모호 질문 즉시 판별)
- **마일스톤: Vertical Slice 3(계약 체결 후 해지 여부) API 끝까지 응답**

### Week 5 — 09.01 ~ 09.06 (제출 주간)

- 전체 통합 리허설: eval set 전체 재실행, 회귀 확인(PoC 기준선 5/5, 5/5 포함)
- Verifier/안전성 테스트(프롬프트 인젝션 등 적대적 케이스)
- 기술 제안서 작성 완료(시스템 구성도, 기능 흐름도, 사용자 시나리오)
- Dockerfile·README 재현성 검증(팀원 본인 PC가 아닌 환경에서 1회 클린 빌드)
- **09.06 이전 코드 프리즈 → 제출** (마감 후 변경 시 실격이므로 최소 반나절 버퍼를 두고 프리즈 시점을 팀이 명시적으로 정한다)

### 09.07 ~ 09.20 — 정량평가 기간

- 코드 변경 금지, **서버 무중단 운영**이 유일한 할 일. 모니터링/알림 체계만 가동.

## 일정이 부족할 때의 축소 순서 (반드시 이 순서로만 자른다)

일정이 밀리면 아래 순서대로, **위에서부터** 자른다. 절대 순서를 거꾸로(전체 BM25 커버리지부터) 자르지 않는다 — BM25 전체 문서 검색이 곧 "범용 RAG 지원"의 최소 구현체이며, 이걸 줄이면 §4의 "코퍼스 밖은 정밀 지원이 없어도 검색은 된다"는 전제 자체가 무너져 §`official_requirements_gap.md`가 지적한 오류로 되돌아간다.

1. **가장 먼저 자른다 — 실험 트랙** (아래 별도 절): Hard Negative 학습, HyDE, Dynamic N-shot Prompting, DPO Re-ranker. 애초에 5주 로드맵에 넣지 않았으므로 "자른다"기보다 "시작하지 않는다."
2. **다음으로 자른다 — Post-MVP**: Cross-Encoder Re-ranking, Query Decomposition.
3. **다음으로 자른다 — "가능하면 MVP에 추가" 3종**: Dense Retrieval(1단계 4개 섹션 한정 적용, [확인] 주최 측 공식 허용 — BGE-M3/multilingual-e5), RRF 결합, Context Bundling. 이 3개가 없어도 BM25 + Metadata 필터 + 계층형 축소로 "정밀 지원 없는 문서도 검색은 된다"는 조건은 유지된다 — 품질은 떨어지지만 커버리지 자체는 유지. Dense는 규정상 문제는 없으나 **효과가 실측되지 않으면 확대하지 않는다는 게이팅 자체가 축소 기준**이므로, 1단계조차 시간이 없으면 가장 먼저 스킵할 후보다.
4. **다음으로 자른다 — 정밀 지원 확장분**: major 하위 유형(CB·상각형 등 뒤쪽 순번), 지분공시 합계행 정밀화, 재무제표 추가 계정. 단, 이 항목들의 **RAG 검색 대상 포함 자체는 자르지 않는다** — 정밀 Fact Extractor만 못 만드는 것이지, 그 문서가 검색에서 빠지는 게 아니다.
5. **절대 자르지 않는다 — MVP 필수**: 전체 4개 doc_group 구조 보존 Parsing, `derived_subtype`, Metadata Filter, **계층형 축소**, 전체 문서 BM25 검색, 거래소공시 3종 Fact Store, Python Calculator, HyperCLOVA X 근거 답변, Citation.

**계층형 축소가 3번에서 5번으로 옮겨간 이유**: 이전 버전은 계층형을 "가능하면 추가"로 두고 축소 후보에 넣었다. 5.29GB 실측 후, 계층형 없이 flat 검색을 하면 응답 지연·메모리에서 성립하지 않고 Recall@k 지표도 못 재므로 **MVP 필수로 이동**했다.

## Post-MVP (5주 로드맵에는 배치하지 않음, §5.1 참조)

`hybrid_architecture_proposal.md` §9 참조. "가능하면 MVP에 추가" 4종이 안정화되고 buffer가 남을 때만 순서대로 검토:

1. **Cross-Encoder Re-ranking** — 1차 후보군 정밀 재정렬. 지연시간 영향 확인 후 도입.
2. **Query Decomposition** — 복합 질의 자동 하위질의 분해. MVP는 사람이 짠 route 조합 규칙으로 대체.

두 항목 모두 예선 제출(09.06) 이전에 시간이 남으면 Week 4~5 buffer에서, 아니면 예선 통과 후(10.01 이후) 결선 준비 단계에서 재검토한다.

## 실험 트랙 (Research Track — 5주 로드맵 외부, 게이팅 조건부)

`hybrid_architecture_proposal.md` §10 참조: Hard Negative 학습, HyDE, Dynamic N-shot Prompting, DPO Re-ranker. **게이팅 조건**: 내부 eval set(§`evaluation_strategy.md`)과 검색 실패 로그가 충분히 쌓인 뒤에만 착수 여부를 판단한다. 5주 로드맵의 어느 주차에도 이 4개를 넣지 않는다 — 넣는 순간 일정을 위협하는 과잉 설계가 된다.
