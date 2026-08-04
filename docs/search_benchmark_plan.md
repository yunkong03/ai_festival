# 검색 성능 비교 실험 계획 (BM25 vs Dense×3 vs Hybrid RRF)

> 이 문서는 **계획만** 담는다. 코드는 작성/수정하지 않았다. `interface_contract_draft.md`(Chunk/Evidence/TableMetadata
> 스키마, Workstream A 소유)와 `evaluation_strategy.md`(Recall@k/MRR 정의, Dense 도입 게이트 원칙)에
> 이미 합의된 정의를 그대로 따르며, 새로 정의하는 것은 "이 실험 하나를 위한" 서브셋/파일 목록/실행순서뿐이다.
> Day 0 회의에서 Workstream B(Retrieval 담당)와 이 계획을 맞춰봐야 한다 — 특히 §1의 표 청킹 방식은
> 기존 계약과 미묘하게 다른 선택지라 팀 동의가 필요하다.

---

## 0. 사전 점검 결과 — 실행 전에 반드시 알아야 할 것

`src/`, `tests/`, `config/` **전부 비어 있고**, `requirements.txt`/`pyproject.toml`도 없다. 실제로 존재하는 건:
- `docs/superpowers/plans/2026-07-29-mvp-fact-store.md` — 파서 계획 초안(미실행, `hybrid_architecture_proposal.md` §6 검토에서 "표만 순회하고 문단은 chunk화 안 함" 등 6개 수정사항 지적됨)
- `interface_contract_draft.md` §2 — `Chunk`/`Evidence`/`TableMetadata` **스키마는 이미 확정**돼 있음(코드는 없음)
- eval set 20문항 초안(`project_vision_and_eval_set.md`) — 있지만 `evaluation_strategy.md` §3이 요구하는 **gold label(정답 문서/섹션/evidence_id)이 아직 안 붙어있음**

**결론: "기존 청크 산출물을 갖고 비교"가 불가능하다.** 이 실험은 필연적으로 "① 최소 chunker부터 만들어서 산출물을 낸다 → ② 그 위에서 검색 비교를 한다"는 2단계 구조가 된다. 다만 이건 낭비가 아니라 — 이 실험에서 만드는 chunker가 그대로 `hybrid_architecture_proposal.md` §5.1 "MVP 필수 1번"(전체 XML 구조보존 파싱)의 첫 착수판이 된다. 즉 이 실험을 하면서 Workstream A의 필수 작업 일부가 조기 완성된다.

---

## 1. Chunk 스펙 확정 — 사용자 지정안을 기존 계약에 매핑

사용자가 지정한 스펙(제목+section_path+본문, 450~500토큰, Table Row Chunk)을 `interface_contract_draft.md §2`의 기존 `Chunk`/`TableMetadata` 타입에 그대로 얹는다 — 새 스키마를 만들지 않는다.

| 사용자 지정 | 기존 계약 필드 매핑 |
|---|---|
| 제목 + section_path + 본문 | `Chunk.kind = PARAGRAPH`, `Chunk.section_hierarchy`(breadcrumb, TITLE 텍스트 기반), `Chunk.text` |
| Table Row Chunk | `Chunk.kind = TABLE`, `Chunk.table_metadata`(제목/행헤더/열헤더/단위/기준기간/연결·별도) |

**짚고 넘어가야 할 불일치 1건 — 표 청킹 단위:** `interface_contract_draft.md`는 "표 하나 = chunk 하나(구조 보존)"를 원칙으로 삼는다(맥락 유지가 목적). 사용자가 지정한 "Table **Row** Chunk"는 **행 단위**로 더 잘게 쪼개는 방식이다. 둘 다 일리 있다 — Row 단위는 Dense 검색에서 특정 셀 값과의 의미 매칭에 유리할 수 있고, 표 전체 단위는 BM25에서 "표 제목 키워드"로 찾을 때 유리할 수 있다. **이 실험에서는 사용자 지정대로 Row Chunk로 가되, 각 row chunk에 표 전체의 `table_metadata`(제목·헤더·단위·기준기간)를 그대로 복제해서 넣는다** — row 하나만 보면 "이 숫자가 뭔지" 맥락이 사라지기 때문이다. 이 선택 자체가 §7에서 "표는 Row 단위가 나은가 전체 단위가 나은가"라는 후속 실험 후보가 된다는 점을 리포트에 남긴다.

**짚고 넘어가야 할 불일치 2건 — 토큰 수 기준:** "450~500토큰"이라고 했을 때 어느 모델의 토크나이저 기준인지가 정해져야 한다 — BGE-M3(XLM-RoBERTa 계열), multilingual-e5(mBERT 계열), Qwen3-Embedding(Qwen 자체 BPE)이 토크나이저가 전부 다르다. **"동일 Chunk를 모든 모델에 씀"이 실험 조건이므로, 청킹 자체는 모델 독립적이어야 한다** — 권장: `tiktoken`(범용, 설치 쉬움) 또는 BGE-M3 토크나이저 하나를 기준으로 통일해서 자르고, 그 결과 청크를 그대로 3개 모델에 다 먹인다(각 모델이 그 청크를 자기 토크나이저로 다시 재는 건 상관없음 — 자르는 기준만 통일하면 됨).

---

## 2. 코퍼스/질문 서브셋 정의

전체 5.29GB를 3개 임베딩 모델로 다 색인하면 1회성 벤치마크치고 비용·시간이 과하다. **대표성 있는 서브셋**을 쓴다.

**서브셋 구성 원칙:**
1. **§3의 eval set 20문항의 정답 문서는 100% 포함** — 이게 빠지면 애초에 Recall을 잴 수 없다.
2. 나머지는 `corpus_coverage_strategy.md`의 실측 문서유형 비율을 대략 유지해서 채운다 — 예: periodic 20~30건(사업보고서 위주, 회사 다양하게), exchange 50~80건, major 30~50건(자기주식·유상증자 등 실제 최다 유형 포함), holding 20~30건.
3. 목표 총 청크 수: 대략 5,000~20,000개 — 3개 임베딩 모델을 로컬/API로 무리 없이 처리할 수 있는 규모(전체 코퍼스를 다 하면 이 몇 배가 되어 1차 실험에 부적합).

---

## 3. Eval set(질문+정답 Evidence) — 준비 필요, 그대로 못 씀

`project_vision_and_eval_set.md`의 20문항을 재사용하되, `evaluation_strategy.md §3`이 요구하는 **4종 gold label**을 이 실험 전에 반드시 채워야 한다: (a) 기대 answer 값, (b) 정답 문서 `rcept_no`, (c) 정답 섹션(`section_hierarchy`), (d) 정답 `evidence_id`(들). 이게 없으면 Evidence Recall@k/MRR 자체를 계산할 수단이 없다.

**질문 유형 4분류 매핑** (사용자 요청 분류를 기존 20문항에 적용):

| 유형 | 대응하는 기존 문항 예시 | 비고 |
|---|---|---|
| Fact/Table | #1(재무수치), #7(유상증자 금액), #12(지분율), #17(단위불일치) | 표/숫자 근거 |
| Narrative | #3(사업내용), #4(위험요인), #13(연구개발) | 문단 근거 |
| Correction/Event | #9,#10(체결→해지), #16(정정 수치) | `FilingEvent`/`VersionResolutionResult` 관련 |
| Multi-document | #5(설비투자 비교), #11(연도 비교) | 여러 문서 종합 |

**주의:** 현재 20문항을 이 4분류로 나누면 카테고리당 3~6개뿐이라 통계적으로 얇다. 유형별 비교가 목적이면 **카테고리당 최소 8~10문항**은 되도록 보강을 권장 — 특히 함정 문항(#15~#20)도 유형별로 재분배해서 채워 넣을 수 있다(예: #15 BW 없음 질의는 Fact/Table 유형의 "데이터 없음" 케이스로).

---

## 4. 비교 대상 — 7개 시스템

| # | 시스템 | 구성 |
|---|---|---|
| 1 | BM25 only | Tantivy 색인, RRF 없음 |
| 2 | BGE-M3 dense only | 순수 벡터 검색 |
| 3 | multilingual-e5-large-instruct dense only | 순수 벡터 검색 |
| 4 | Qwen3-Embedding-0.6B dense only | 순수 벡터 검색 |
| 5 | BM25 + BGE-M3 (RRF) | `hybrid_architecture_proposal.md §7.3` 기본안(k=60) |
| 6 | BM25 + multilingual-e5 (RRF) | 동일 RRF 설정 |
| 7 | BM25 + Qwen3-Embedding (RRF) | 동일 RRF 설정 |

Reranker·Fine-tuning 없음(사용자 지정, `hybrid_architecture_proposal.md` §9 Post-MVP 원칙과도 일치 — 지금 단계에서 안 씀).

---

## 5. 통제 변수 체크리스트

실행 스크립트를 만들 때 아래를 **7개 시스템 전부 동일하게 고정**해야 비교가 유효하다. 이 표는 그대로 구현 시 assert 대상이 된다.

- [ ] 동일 질문 20(+보강)문항, 동일 gold evidence 라벨
- [ ] 동일 문서 서브셋(§2)
- [ ] 동일 Metadata Filter — `RetrievalQuery`의 `corp_names`/`doc_group_filter`/`date_range` 등을 검색 전에 먼저 적용(§7.1 원칙), 7개 시스템 다 이 필터를 거친 후보 집합 안에서만 검색
- [ ] 동일 Chunk(§1) — 청킹은 1회만 수행하고 산출물을 7개 시스템이 공유
- [ ] 동일 top-k(예: k=10, Recall@5/@10 둘 다 상위 10개 결과에서 잘라서 계산)
- [ ] 동일 Vector Index 설정 — 인덱스 타입(예: flat/HNSW 중 하나로 통일), 거리 함수(cosine 통일), normalize 여부 통일. **모델마다 임베딩 차원이 다르므로(예: BGE-M3 1024차원 vs e5-large 1024 vs Qwen3-0.6B는 모델마다 다름) 인덱스 "설정"이 같다는 건 파라미터(HNSW면 M/efConstruction 등)를 같게 맞춘다는 뜻이지 벡터 차원까지 강제로 맞춘다는 뜻은 아님 — 이 구분을 리포트에 명시**
- [ ] Reranker 없음, Fine-tuning 없음

---

## 6. 지표 측정 방법

| 지표 | 측정 방법 |
|---|---|
| Evidence Recall@5 / @10 | 질문별 top-k chunk 중 gold `evidence_id`가 속한 chunk가 포함되는 비율. chunk 자체가 evidence보다 큰 단위이므로 "gold evidence를 포함하는 chunk가 top-k 안에 있는가"로 판정(§evaluation_strategy.md의 Evidence Recall@k 정의를 chunk 단위로 근사) |
| MRR | 질문별로 gold evidence를 포함하는 **첫 chunk의 순위**의 역수(1/rank), 없으면 0. 20문항 평균 |
| 질의 latency | 질문 1건당 검색 전체(BM25 계산 + Dense 계산 + RRF 결합까지, 시스템마다 해당하는 것만) 소요시간. warm-up 1회 버리고 3회 반복 median |
| 임베딩 생성 시간 | 서브셋 전체 청크를 해당 모델로 임베딩하는 데 걸리는 총 시간(모델별), 초당 처리 청크 수도 같이 기록 |
| Vector Index 크기 | 디스크 상 인덱스 파일 용량(MB), 임베딩 차원·청크 수도 함께 기록(크기 차이의 원인을 구분하기 위해) |

**유형별 분리:** 위 지표를 20문항 전체 평균과, §3의 4개 유형(Fact/Table, Narrative, Correction/Event, Multi-document)별 평균으로 **둘 다** 낸다 — 유형별 평균이 최종 리포트의 핵심 표.

---

## 7. 필요 파일

```
dart_project/
├── data/eval/
│   ├── eval_set.jsonl          # 질문 + gold(doc_id/section/evidence_id/answer) — §3, 아직 없음, 먼저 만들어야 함
│   └── corpus_subset.jsonl     # 이번 실험에 쓸 문서 rcept_no 목록 — §2
├── data/chunks/
│   └── chunks.jsonl            # Chunk 스키마 그대로(§1) — 이번 실험에서 처음 생성
├── data/index/
│   ├── bm25_tantivy/           # Tantivy 색인 디렉터리
│   ├── vec_bge_m3/
│   ├── vec_e5_large_instruct/
│   └── vec_qwen3_0.6b/
├── src/dart_corpus/
│   ├── chunker.py              # §1 스펙대로 Chunk 생성 (신규, Workstream A 영역)
│   ├── bm25_index.py           # Tantivy 색인 빌드/질의
│   ├── dense_index.py          # 임베딩 생성 + 벡터 인덱스 빌드/질의 (모델은 인자로 교체)
│   └── rrf.py                  # RRF 결합(§7.3 공식 그대로, k=60)
├── scripts/
│   └── run_search_benchmark.py # 7개 시스템 전부 돌려서 결과 산출
└── docs/
    └── search_benchmark_report.md   # 실행 후 결과 리포트(이 계획 문서와 별개 산출물)
```

---

## 8. 실행 순서

1. **eval set gold label 완성** (§3) — 사람이 직접 원문 확인하며 20(+보강)문항에 정답 문서/섹션/evidence_id 라벨링. **이게 안 끝나면 그 뒤 아무것도 못 잰다 — 최우선 순서.**
2. **서브셋 문서 목록 확정** (§2) — eval set 정답 문서 전부 + 층화표본
3. **chunker 구현** (§1) — SECTION/PARAGRAPH/TABLE(Row) chunk 생성, `chunks.jsonl` 산출
4. **BM25 색인 구축** (Tantivy) — 디스크 기반, `corpus_coverage_strategy.md §5`에서 이미 확정된 엔진 선택 원칙(`rank_bm25` 같은 인메모리 순수 파이썬 안 씀) 재사용
5. **3개 임베딩 모델로 각각 벡터 인덱스 구축** — 이때 임베딩 생성시간·인덱스 크기 기록(§6)
6. **7개 시스템 각각에 eval set 전체 질의 실행** — top-10 chunk + latency 기록
7. **Recall@5/@10, MRR 계산** — 전체 평균 + 유형별(§3 4분류) 평균
8. **결과 집계 리포트 작성** (`search_benchmark_report.md`) — §9 형식
9. **게이트 판정** — `evaluation_strategy.md §2.5`의 기존 원칙 그대로: **BM25-only 대비 Recall@k가 실제로 개선되는 hybrid만** 다음 단계(다른 섹션·doc_group으로 확대)로 진행. 개선 안 되면 그 모델 조합은 채택 보류.

---

## 9. 결과 리포트 형식 (초안)

```
## 전체 평균 (20문항)
| 시스템 | Recall@5 | Recall@10 | MRR | 질의latency(ms) | 임베딩생성시간 | 인덱스크기 |
|---|---|---|---|---|---|---|
| BM25 only | | | | | - | - |
| BGE-M3 only | | | | | | |
| e5-large only | | | | | | |
| Qwen3-0.6B only | | | | | | |
| BM25+BGE-M3(RRF) | | | | | | |
| BM25+e5(RRF) | | | | | | |
| BM25+Qwen3(RRF) | | | | | | |

## 유형별 (Fact/Table · Narrative · Correction/Event · Multi-document)
(위와 동일한 표를 유형별로 4개)
```

---

## 요약 — 지금 당장 필요한 결정 3개

1. **표 청킹을 Row 단위로 갈지, 팀 기존 원칙(표 전체 1청크)으로 갈지** — §1, Day 0 회의에서 B와 합의 필요
2. **토큰 카운트 기준 토크나이저 통일** — §1
3. **eval set gold 라벨링 담당자·완료 시점** — §3, 이게 병목이라 가장 먼저 시작해야 함
