# 3인 팀 Workstream 분담

> 전제: `hybrid_architecture_proposal.md`의 Hybrid(C) 아키텍처 채택. 아래 분담은 사용자가 제시한 배정을 그대로 채택하되, 업무량 불균형을 조정한 결과다.

## Workstream A — 팀원 A: 데이터 계약, Parser, Evidence, Fact Store, 정정 및 이벤트 연결

**소유 산출물**: `DocumentRecord`, `ParsedDocument`, `Chunk`, `Evidence`, `ExtractedFact`, `FilingEvent`, `VersionResolutionResult`

**범위 (기존 계획 `2026-07-29-mvp-fact-store.md` 확장)**:

**MVP 필수 (전체 코퍼스 구조 보존 Parsing — 4개 doc_group 전부, `hybrid_architecture_proposal.md` §5.1)**
0. `DartDocumentParser`/`KindXFormsParser`가 `TABLE`뿐 아니라 **`SECTION`/`PARAGRAPH` chunk를 생성**하도록 확장 — 정밀 Fact Extractor가 아직 없는 문서(EB·자산양수도, 지분공시 세부, 정기공시 위험요인·주석 등)도 예외 없이 전부 chunk화한다. `section_hierarchy`(TITLE 기반), `is_attachment`, `TableMetadata`를 채운다. 이것이 B의 전체 BM25 색인 원재료이므로 "일부만 파싱"은 허용되지 않는다.
   **[확인] 규모 주의**: periodic이 5.05GB(평균 3.44MB, 최대 30.7MB/파일)다. 전체를 메모리에 올리지 말고 **문서 단위 스트리밍 처리 + 중간 산출물 디스크 저장**을 전제로 설계한다.
0-b. **`derived_subtype` 생성** — `major` 598건은 `doc_subtype`이 전부 빈 문자열이므로 `report_nm`에서 파싱해 채운다(`interface_contract_draft.md` §1). 난이도는 낮지만 **B의 Metadata Filter가 이것에 의존**하므로 Week 0에 끝낸다.
0-c. **periodic 본문/첨부 구분** — `{rcept}.xml`이 본문, `{rcept}_00760.xml` 등이 첨부(감사보고서). 파일명 정렬 시 첨부가 먼저 오므로 `is_attachment`로 명시 표시.

**정밀 지원 로드맵 (`hybrid_architecture_proposal.md` §5.2, 착수 순서 — 실측 건수 기준으로 재배치)**
1. (기존 계획 그대로) 거래소공시 3종 Fact Store — 경로 해석, manifest/universe 로더, alias index, KindXFormsParser, DartDocumentParser(표), ParserRouter, 라벨/추출기, FactStore, CorrectionResolver
2. (신규) 정기공시 재무제표 핵심 계정 3종(매출액/영업이익/당기순이익, 연결기준) label 설계·추출 → Q1. **[확인] 연결/별도는 섹션 제목(`2-2. 연결 포괄손익계산서`)으로 판별 — 표 헤더 추론 불필요.** **[추정] 금융지주는 계정 체계가 다를 수 있어 표본 확인 필요**
3. (신규, **우선순위 재조정**) 주요사항보고서 정밀 추출 — **실측 분포 기준: 자기주식(338건, major 과반) → 유상증자(56) → 상각형조건부자본증권(71) → CB(22)**. **[확인] BW는 코퍼스 0건이므로 추출기를 만들지 않고 "공시 없음" 응답으로 처리**, EB(4건)·자산양수도(5건)는 범용 RAG. 이전 버전이 Q4 예시(82건, 13.7%)에만 맞춰 major 과반을 빠뜨렸던 것을 교정
4. (신규) 계약명/투자명 fact 추출 + 체결→해지 `FilingEvent` 연결 → Q5
5. (신규, **범위 축소**) 지분공시 **합계 행 한정** 정밀 지원(대표 보고자, 합계 보유주식수, 합계 지분율, 보고사유발생일). **[확인] 1문서에 보고자 16~27회·특별관계자 12~33회 출현하는 N행 표이므로 개별 행까지 정형화하지 않는다**
6. (확장) `CorrectionResolver`에 계약명/투자명 2차 신호 추가(§6-(2))
7. (수정) `FactStore` 명명 정정(append-only → snapshot writer), `Task 5` placeholder fixture 제거(§6-(5))

**주의**: 0/0-b/0-c(전체 구조 보존 Parsing과 파생 필드)는 1~7번 정밀 지원 순서와 무관하게 **가장 먼저, 4개 doc_group 전체 대상으로** 끝낸다. 5주 로드맵의 Week 0~1에 배치되는 이유다.

## Workstream B — 팀원 B: Query Analyzer, Metadata Filtering, Retrieval, Reranker, Task Router, 검색 평가

**소유 산출물**: `RetrievalQuery`, `RetrievalResult`, `TaskPlan`(생성까지 — 실행은 C)

**범위**:

**MVP 필수**
1. Query Analyzer — 자연어 질의에서 기업명(→ `CorpAliasIndex` 호출), 연도/기간, doc_group/subtype 힌트, **지표(fact_type), 연결/별도 기준**, 질의 유형(Closed/Open) 추출. HyperCLOVA X는 **규칙 기반 파싱이 실패했을 때만 fallback**으로 사용 (공식 규칙에 따라 HyperCLOVA X 최소 사용 원칙)
2. Metadata Filtering — manifest 필드(`corp_code`, `doc_group`, **`derived_subtype`**, `rcept_dt`, `is_correction`) 기반 후보 문서 축소. **모든 검색보다 먼저 실행** — §7.1. **[확인] `major`는 `doc_subtype`이 전 건 빈 문자열이므로 A가 채우는 `derived_subtype`을 써야 한다** — 이 의존성을 Week 0에 A와 확인할 것
3. **전체 문서 BM25 색인·검색** — A가 만든 `Chunk`(SECTION/TABLE/PARAGRAPH, **4개 doc_group 전체**) 전부를 색인. 정밀 Fact Extractor 유무와 무관하게 **모든 문서가 최소 BM25로는 검색 가능해야 한다**. **[확인] 코퍼스가 5.29GB(periodic 5.05GB, XML 평균 3.44MB/최대 30.7MB)이므로 순수 파이썬 인메모리 BM25(`rank_bm25` 등)는 부적합** — SQLite FTS5/Tantivy/Lucene 계열 디스크 기반 역색인을 쓴다(엔진 선택은 첫 회의 결정 사항). **`ExtractedFact` 대상은 벡터 검색이 아니라 metadata 매칭으로 조회**
4. **계층형 축소(문서→섹션→청크→Evidence)** — §7.2. **등급 상향**: 5GB 규모에서 flat 검색은 성립하지 않으므로 품질 옵션이 아니라 **필수 설계**다. `SECTION` chunk를 1차 후보 좁히기에 사용
5. Task Router — `TaskPlan.routes`(FACT_LOOKUP/EVIDENCE_SUMMARY/MULTI_DOCUMENT_ANALYSIS/LIMIT_OR_CLARIFICATION 조합)와 `TaskPlan.steps`(실행 순서)를 **모두 사전에 확정**한다. FACT_LOOKUP 실패 시 EVIDENCE_SUMMARY(BM25) fallback 단계도 포함(§3). **자유형 ReAct는 쓰지 않는다** — `interface_contract_draft.md` §8. 실제 실행은 C의 Synthesizer 담당
6. 검색 평가 — Document/Section/Evidence Recall@k 측정(`evaluation_strategy.md` §2.5). 계층형이 MVP 필수가 되었으므로 이 지표들도 MVP 내에서 측정 가능

**가능하면 MVP에 추가** (위 baseline 안정화 후)
7. **Dense Retrieval (단계적 확대) + RRF 결합** — **[확인 — 주최 측 공식 답변] Dense Retrieval 규정상 허용, 임베딩 모델은 BGE-M3·multilingual-e5 등 사전학습 모델 자유 선택**(임베딩·검색 대상은 제공 코퍼스로 제한, 답변 생성만 HyperCLOVA X). 5.29GB 전량 즉시 임베딩은 5주 일정·크레딧상 비현실적이므로 **1단계: periodic 사업내용·원재료 및 생산설비·위험요인·연구개발활동 섹션**에 적용 → **2단계: Recall@k 개선이 실측 확인되면** 다른 섹션·doc_group으로 확대. BM25가 이미 전체를 커버하므로 커버리지 손실 없음
8. Context Bundling — `section_hierarchy`·`table_metadata`를 구조적으로 결합(§7.4). **고정 윈도우(앞뒤 ±N 청크)로 무조건 붙이지 않는다**

**Post-MVP**
9. Cross-Encoder Re-ranking, Query Decomposition — §9 참조, MVP 범위 아님

## Workstream C — 팀원 C: HyperCLOVA X, Synthesizer, Calculator, Verifier, Citation, API, 배포

**소유 산출물**: `CalculationRecord`, `VerificationResult`, `FinalResponse`, `AuditRecord`

**범위**:
1. HyperCLOVA X 연동 — API 클라이언트, 프롬프트 템플릿(질의분해/비정형요약/다중근거통합/Query Analyzer fallback 4용도로 최소 사용)
2. Synthesizer — `TaskPlan.steps`를 실행 순서대로 처리(FACT_LOOKUP 조회, EVIDENCE_SUMMARY 요약 호출, MULTI_DOCUMENT_ANALYSIS 조합), 결과를 자연어 `answer`로 통합
3. Calculator — **금액 파싱, 단위 정규화(억원↔백만원↔원), 합계, 차이, 증감률, 비율, 기업 간 비교 전부를 Python으로 수행**(`hybrid_architecture_proposal.md` §8) — `ExtractedFact`를 입력으로 받는 순수 Python 모듈이며 LLM 호출 없음. HyperCLOVA X는 `CalculationRecord`의 결과를 자연어로 설명하는 역할만 하고 숫자를 재계산하지 않는다. Workstream A의 fact 스키마를 그대로 소비하므로 A와 스키마 합의가 선행되어야 함
4. Verifier — hallucination 체크(답변의 각 주장이 `retrieved_context`에 존재하는지), **답변에 등장하는 모든 숫자를 원문 Evidence와 대조**(Calculator가 계산한 숫자든 RAG가 인용한 숫자든 예외 없이, `hybrid_architecture_proposal.md` §8 — `VerificationResult.numeric_mismatch`), citation 완전성 체크, 안전성 체크(프롬프트 인젝션·개인정보 노출 등), 근거 부족 시 LIMIT_OR_CLARIFICATION 트리거
5. Citation — `evidence_id`/`chunk_id`를 사람이 읽을 수 있는 근거 표시(공시명·공시일)로 변환
6. API 서버 — `GET /answer` 구현(FastAPI 등), 스키마 검증
7. 배포 — Dockerfile, NCP(또는 대안 환경) 서버 운영, `09.07~09.20` 활성화 유지

## 업무량 밸런스 조정

원 배정대로면 A(신규 fact 도메인 3개 + 문단 chunker + resolver 보강)가 가장 무겁고, C(대부분 통합/연결 성격)가 상대적으로 가볍다. 조정안:

1. **A의 정밀 지원 1차 범위 축소**: major는 실측 최다 유형부터(자기주식→유상증자→상각형→CB), 재무제표는 3계정(매출액/영업이익/순이익)까지만, 지분공시는 합계 행만. **BW(0건)는 아예 만들지 않고, EB(4건)·자산양수도(5건)는 RAG로 넘긴다.** **단, 이 축소는 정밀 지원(전용 Fact Extractor) 범위에만 적용된다 — 구조 보존 Parsing(0/0-b/0-c)은 축소 대상이 아니고 전체 doc_group에 처음부터 적용한다.**
1-b. **A의 실질 부담이 커졌다 — 5GB 파싱은 단독 부담이 아니다**: 구조 보존 Parsing이 MVP 필수로 격상되고 코퍼스가 5.29GB임이 확인되면서, A의 Week 0~1 작업량이 다른 두 명보다 현저히 크다. **파싱 파이프라인 성능/스트리밍 처리는 B가 색인 쪽에서 함께 설계**하고(색인 입력 포맷을 B가 정하면 A가 그 포맷으로 흘려보내는 구조), C는 Week 0~1에 API·HyperCLOVA X 골격이 상대적으로 가벼우므로 **eval set 초기 제작을 C가 더 많이 맡는다**.
2. **SECTION/PARAGRAPH chunker 경계 분리**: A는 XML에서 섹션·문단을 추출해 `Chunk(kind=SECTION|PARAGRAPH)`로 만드는 것까지만 책임진다. BM25/임베딩 인덱싱은 B가 담당한다. A→B 경계는 `Chunk` 스키마(`interface_contract_draft.md`)로 고정.
3. **검색평가/eval set 제작은 B 단독 부담 아님**: 공식 제출 요건이 아닌 팀 내부 품질 지표이므로 "공동 책임"(§공동 책임) 항목인 평가 데이터 제작과 겹친다 — B가 도구를 만들고 실제 질의-정답 세트 채우기는 3인이 분담.
4. **Calculator는 C가 소유하되 로직은 A와 조기 합의**: 계산 자체는 단순(합산/비교/증감률)하지만 어떤 `ExtractedFact` 조합을 계산 입력으로 쓸지는 A의 fact 스키마에 강하게 의존한다 — Task Plan에서 A/C 인터페이스를 첫 회의에서 예시로 맞춰본다.

## 공동 책임 (3인 전체)

- 전체 파이프라인 통합(Query → Router → 각 경로 실행 → Synthesizer → API)
- 평가 데이터(질의-정답-근거 세트) 제작
- API 스키마 최종 확정 및 검증
- 기술 제안서 작성
- 최종 데모 시나리오 준비 및 리허설
