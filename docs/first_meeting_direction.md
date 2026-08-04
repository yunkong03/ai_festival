# 첫 팀 회의 자료 — 전체 방향성

> 미래에셋증권 AI Festival "공시 Agent" 과제. 이 문서는 표지 겸 요약본이다. 세부 근거는 각 링크 문서 참조.

## 이 문서들이 만들어진 이유

기존에 `2026-07-29-mvp-fact-store.md`(거래소공시 3종 정형 추출 계획)를 이미 작성했다. 이번 라운드는 그 계획을 **구현하기 전에**, 공식 과제 PDF 기준으로 그 계획이 전체 요구사항 중 어디에 위치하는지 냉정하게 점검하고, 3인 팀이 예선(09.06 마감)까지 갈 전체 방향을 정하기 위한 것이다. **코드는 아직 한 줄도 건드리지 않았다.**

## 문서 목록

| 문서 | 내용 |
|---|---|
| [`official_requirements_gap.md`](./official_requirements_gap.md) | 공식 PDF 요구사항 요약 + 기존 계획의 커버리지 갭 분석(참고 질의 6종은 예시일 뿐이라는 전제 포함) |
| [`hybrid_architecture_proposal.md`](./hybrid_architecture_proposal.md) | A/B/C 방향 비교, Hybrid 추천 근거, 실행경로 4종 설계(+fallback 규칙), 문서유형별 3단계 지원 수준(정밀지원/범용RAG/지원제한), 우선순위 3단계(MVP필수/가능하면추가/Post-MVP), Retrieval·계산 아키텍처 원칙, 기존 계획 기술 검토 6항목 |
| [`corpus_coverage_strategy.md`](./corpus_coverage_strategy.md) | 문서유형×섹션 단위 지원 수준 매트릭스, 핵심 Fact/RAG 대상 목록, fallback 정책, 구현난이도·축소순서 |
| [`team_workstreams.md`](./team_workstreams.md) | 3인 역할 분담 및 업무량 조정 |
| [`interface_contract_draft.md`](./interface_contract_draft.md) | 병렬개발 전 합의할 14개 타입 계약 |
| [`evaluation_strategy.md`](./evaluation_strategy.md) | 공식 평가방법 + 내부 지표 매핑 + eval set 계획 |
| [`api_submission_plan.md`](./api_submission_plan.md) | 제출 요건, API 스키마, 체크리스트 |
| [`development_roadmap.md`](./development_roadmap.md) | 주차별 로드맵, Vertical Slice 3단계 |
| [`risk_register.md`](./risk_register.md) | 일정/기술/팀/평가 리스크와 완화방안 |
| [`official_qna_questions.md`](./official_qna_questions.md) | 주최 측에 확인할 질문 목록 |
| [`meeting_decisions.md`](./meeting_decisions.md) | 첫 회의용 빈 의사결정 체크리스트 |

## 1. 기존 Fact Store 계획의 전체 프로젝트 내 역할

**전체 프로젝트가 아니라, Hybrid 아키텍처의 `Workstream A` 시작점(FACT_LOOKUP 경로의 핵심 자산)이다.** PoC로 검증된 정확도(투자금액 5/5, 계약금액 5/5)는 그대로 유지하되, 공식 참고 질의 6종 중 5개(Q1, Q2, Q3 일부, Q4, Q6)를 지원하려면 정기공시 재무제표·주요사항보고서 자금조달·정기공시 서술 섹션까지 범위를 확장해야 한다.

## 2. 최종 권장 방향

**C. Hybrid** — 핵심 수치(매출액, 투자금액, 계약금액 등)는 Python 정형 추출로 정확도를 담보하고, 서술형·비교·요약 질의는 구조를 보존한 RAG + HyperCLOVA X로 처리한다. 근거: 공식 PDF가 "종합적으로 이해하고 비교·분석·설명하는 Agent"를 명시하고 있고, 평가지표 8개가 정확성과 서술 완결성을 동시에 요구하기 때문 — 거래소공시만 하는 A안, 순수 RAG인 B안은 각각 한쪽 평가축에서 구조적으로 무너진다. 상세 근거는 `hybrid_architecture_proposal.md`.

## 3. 지원 수준과 MVP 범위 (수정됨 — 이전 "MVP Core/Coverage" 프레이밍은 폐기)

**중요한 수정**: 이전 버전은 "MVP Core(정형화)"와 "MVP Coverage(RAG)" 2층 구조를 쓰면서, Coverage 층 안에서도 "참고 질의에 없다"는 이유로 일부 문서(지분공시, 재무제표 주석, 임원보수 등)를 사실상 배제하는 서술이 섞여 있었다. 공식 참고 질의 6종은 **예시일 뿐**이므로 이 배제는 근거가 없었다 — `hybrid_architecture_proposal.md` §4에서 바로잡았다. 이제 두 축을 분리한다:

- **지원 수준 3단계** (무엇을 어떻게 지원하는가, §4): 정밀 지원(전용 Fact Extractor) / 범용 RAG 지원(전용 추출기는 없지만 검색·응답은 됨) / 지원 제한(코퍼스 밖·투자추천·원문누락·근거부족만). **전체 코퍼스가 최소 범용 RAG 지원 대상**이다.
- **우선순위 3단계** (언제 만드는가, §5.1): **MVP 필수**(전체 구조보존 Parsing + `derived_subtype` + Metadata Filter + **계층형 축소** + 전체 문서 BM25 검색 + 기존 핵심 Fact Store/Calculator + HyperCLOVA X 근거답변 + Citation) / **가능하면 MVP에 추가**(Dense Retrieval **범위 한정**, RRF, Context Bundling) / **Post-MVP**(Cross-Encoder, Query Decomposition) / **실험 트랙**(Hard Negative, HyDE, Dynamic N-shot, DPO Reranker — 게이팅 조건부).

일정이 부족해도 **전체 문서 BM25 검색 커버리지와 계층형 축소는 유지**하고, 학습형·고비용 기능부터 축소한다(`development_roadmap.md`의 축소 순서). 상세 매트릭스는 `corpus_coverage_strategy.md`.

### 실측 검증으로 바뀐 판단 (2026-07-29, `corpus_coverage_strategy.md` §0.1)

기획 문서를 코퍼스 실측치와 대조한 결과 **6건의 설계 전제가 틀렸음**이 확인되어 교정했다:

| 항목 | 이전 판단 | 실측 후 |
|---|---|---|
| 코퍼스 규모 | 명시 안 함(난이도 "중") | **5.29GB**(periodic 95%, XML 최대 30.7MB) → 난이도 "상", 파이프라인 설계 전면 재고 |
| 계층형 검색 | 가능하면 추가 | **MVP 필수** — 5GB flat 검색은 성립 불가 |
| Dense Retrieval | 가능하면 추가(전체) | **단계적 확대** — [확인, 주최 측 공식 답변] 규정상 허용(BGE-M3/multilingual-e5), periodic 4개 섹션(사업내용/생산설비/위험요인/연구개발)부터 적용, Recall 개선 실측 후 확대 |
| major 정밀 지원 | Q4 4종(유상증자/CB/BW/EB) | **자기주식(338건) 최우선** — Q4 4종은 82건(13.7%)뿐, major 과반을 빠뜨렸었음 |
| BW(신주인수권부사채) | 정밀 지원 대상 | **코퍼스 0건** — 추출기 대신 "공시 없음" 응답 |
| Q3 설비투자 데이터 소스 | 거래소공시 신규시설투자등 | **정기공시 II-3** — 거래소공시는 21/70개사만, 2차전지 대형 2사는 0건 |
| 연결/별도 구분 | 표 헤더 조사 필요(리스크 H) | **섹션 제목으로 판별 가능**(리스크 하향) |
| 지분공시 | 6개 필드 정밀 지원 | **합계 행 한정** — 1문서에 보고자 16~27회 나오는 N행 표 |
| `major.doc_subtype` | 필터 키로 사용 가정 | **598건 전부 공백** — `derived_subtype` 파생 필요 |

## 4. 3인 역할 분담

- **팀원 A**: 데이터 계약, Parser, Evidence, Fact Store, 정정/이벤트 연결 (기존 계획 + 재무제표/자금조달/계약명 확장)
- **팀원 B**: Query Analyzer, Metadata Filtering, Retrieval, Reranker, Task Router, 검색 평가
- **팀원 C**: HyperCLOVA X, Synthesizer, Calculator, Verifier, Citation, API, 배포
- 공동 책임: 전체 통합, eval set 제작, API 스키마 확정, 기술 제안서, 최종 데모

원 배정 그대로면 A가 과중해질 위험이 있어 §`team_workstreams.md`에서 범위 축소(재무계정 3개까지, 자금조달 2유형부터)로 조정했다.

## 5. 첫 Vertical Slice (개발 순서)

1. 거래소공시 단일 금액 조회 (FACT_LOOKUP만)
2. 사업보고서/분기보고서 Open 요약 (EVIDENCE_SUMMARY, A/B/C 3자 통합 최초 검증)
3. 계약 체결 후 해지 여부 (FACT_LOOKUP + MULTI_DOCUMENT_ANALYSIS 조합, Hybrid 가치 증명)

전체 기능 완성이 아니라 **이 3개 질의가 API 응답까지 실제로 흐르는 것**이 1차 목표. 상세 주차별 계획은 `development_roadmap.md`.

## 6. 첫 회의에서 확정할 사항

`meeting_decisions.md`에 체크리스트 형태로 정리됨 — 아키텍처 동의, MVP 범위 순서, 인터페이스 계약 승인, 역할 분담 동의, 개발환경/도구, 일정, Q&A 담당자, 다음 회의.

## 7. 공식 Q&A에서 확인할 사항

`official_qna_questions.md` 참조. 우선순위 높은 것: (2) pdf+html 3건 평가 범위 포함 여부, (3) 참고 질의 6종 외 유형 가능성, (8) think_trace 세부 규격. **(14) 임베딩 모델 허용 범위는 주최 측 공식 답변으로 확인 완료** — 아래 §12 참조.

## 8. 주요 리스크

`risk_register.md` 참조. 가장 치명적인 것 3개(실측 후 갱신):
- **[신규, H/H] 5.29GB 코퍼스 파싱·색인이 Week 1~2 안에 안 끝남** (완화: Week 0 파일럿으로 처리량 실측 후 범위 확정, 작은 doc_group부터 순차 색인)
- 09.06 마감 직전 A/B/C 통합 실패 (완화: Week 1부터 매주 실제 통합)
- 09.07~09.20 서버 무중단 운영 실패 (완화: 배포 자동화, 담당자 지정)

※ 기존 3순위였던 "연결/별도 구분 실패"는 섹션 제목으로 판별 가능함이 확인되어 **하향**됐고, 대신 "[추정] 금융지주 계정 체계 상이"가 새 확인 대상으로 올라왔다.

## 9. 이번에 생성한 문서 목록

```
docs/
├── first_meeting_direction.md       (이 문서)
├── official_requirements_gap.md
├── hybrid_architecture_proposal.md
├── corpus_coverage_strategy.md
├── team_workstreams.md
├── interface_contract_draft.md
├── evaluation_strategy.md
├── api_submission_plan.md
├── development_roadmap.md
├── risk_register.md
├── official_qna_questions.md
└── meeting_decisions.md
```

기존 `docs/superpowers/plans/2026-07-29-mvp-fact-store.md`는 그대로 유지되며, Workstream A 실행 시 `hybrid_architecture_proposal.md` §6의 수정사항(placeholder fixture 제거 등)을 반영해 실행한다. **이번 세션에서는 코드 수정, Task 실행, git commit을 하지 않았다.**

## 10. (추가 반영) 검색·계산 아키텍처 원칙

XBRL Agent / FinQAPT / FinSage 참고 원칙을 `hybrid_architecture_proposal.md` §7~§10, `interface_contract_draft.md`(Chunk/RetrievalQuery/RetrievalResult/TaskPlan/CalculationRecord 확장), `team_workstreams.md`(B/C 범위), `development_roadmap.md`(Post-MVP/실험 트랙), `evaluation_strategy.md`(§2.5 계층형 지표)에 반영했다. 핵심:

- 검색 전 metadata로 후보 축소 → 문서→섹션→표/문단→Evidence 계층형 검색 → BM25+Dense+RRF(학습불필요 기본안) 결합 → 구조적 Context Bundling(고정 윈도우 아님)
- 계산(파싱/정규화/합계/차이/증감률/비율/비교)은 전량 Python, HyperCLOVA X는 결과 설명만
- Task Router는 `TaskPlan`을 사전에 구조화해 확정 — 자유형 ReAct는 채택하지 않음
- 평가는 최종 답변뿐 아니라 Document/Section/Evidence Recall@k, Fact Extraction/Calculation/Citation Accuracy로 단계 분리 측정
- Cross-Encoder Re-ranking·Query Decomposition은 MVP 이후, Hard Negative·HyDE·Dynamic N-shot·DPO Reranker는 eval 데이터·실패로그 확보 후의 실험 트랙으로 분리 — 5주 로드맵에는 넣지 않음

## 11. (추가 수정) 잘못된 제외 논리 교정 — 전체 코퍼스 RAG 커버리지

이전 버전 문서들에 "참고 질의 6종에 없으므로", "질의 빈도가 낮을 것 같으므로", "자유서술형이므로", "정형화가 어려우므로 질의 지원에서도 제외"라는 논리로 일부 문서·섹션(재무제표 상세 주석, 임원보수, 계열회사 현황, 위험 요인, 투자판단관련주요경영사항, 외부평가·주식매수청구권 조건, 자산양수도·자금조달 자유서술, 지분공시 등)을 사실상 배제하는 서술이 있었다 — 실제 평가셋은 비공개이므로 참고 질의 6종만으로 지원 범위를 좁힐 근거가 없었다. `hybrid_architecture_proposal.md` §4에서 "정밀 지원 / 범용 RAG 지원 / 지원 제한" 3단계로 재분류했고, `corpus_coverage_strategy.md`에 전체 매트릭스를 정리했다. **"지원 제한"은 코퍼스 밖 기업·기간·외부정보, 투자 추천, 원문 누락·파싱 불가, 근거 부족·모호한 질문 — 이 4가지 사유로만 한정**하며 그 외 모든 XML 문서는 최소 BM25 검색 대상이다.

## 12. (추가 확인) 주최 측 공식 답변 — 임베딩 모델 허용 및 Dense 적용 방식

`official_qna_questions.md` Q14에 대한 주최 측 공식 답변을 반영했다:

- **답변 생성(LLM)은 HyperCLOVA X만 제한된다. 임베딩/검색 도구로 BGE-M3, multilingual-e5 등 사전학습 임베딩 모델 사용은 허용된다.** 단 임베딩·검색 대상은 제공 코퍼스로 제한하고 최종 답변 생성은 HyperCLOVA X만 사용한다.
- **Dense Retrieval 적용 방식도 주최 측이 구체적으로 제시**: 전체 코퍼스 일괄 적용이 아니라 Open-ended 질의 비중이 높은 **periodic의 사업내용·생산설비·위험요인·연구개발 섹션부터** 적용하고 BM25와 RRF로 결합한 뒤, **Recall 개선이 확인될 때만** 범위를 확대한다.

이는 `corpus_coverage_strategy.md` §0.1의 "5.29GB 전량 임베딩 비현실적"이라는 실측 근거의 **결론(단계적 적용)은 그대로 유지**하면서, "규정상 안 되는 것"이 아니라 "리소스상 단계적으로 할 것"이라는 근거를 명확히 했다. `hybrid_architecture_proposal.md` §7.3·§8, `team_workstreams.md`, `development_roadmap.md`, `evaluation_strategy.md`(Dense 도입 게이트), `risk_register.md`, `meeting_decisions.md`에 반영했다.
