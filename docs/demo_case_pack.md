# 데모 Case Pack — 후보 사건 비교, 선정 이유, 실행 방법

금융 탐정 게임 데모용 Case Pack 3건의 설계 문서. 전체 코퍼스(4,204건)를 게임으로
변환하지 않는다. **데모하기 좋은 실제 사건만 골라 프론트엔드가 바로 쓸 수 있는 팩으로 만든다.**

- 생성물: `data/artifacts/case_packs/CASE-00{1,2,3}.json` + `index.json`
- 스키마: `schemas/case_pack_schema_v0.json`
- 공시/Evidence 출처 매핑(자동 생성): `docs/demo_case_evidence_map.md`
- 재생성/검증: 이 문서 맨 아래 § 실행 방법

---

## 1. 후보 사건 탐색 방법

`data/3.공시/corpus/manifest.jsonl`(4,204건)에서 **시간 흐름과 판단 변화가 드러나는**
Event Chain을 뽑았다. 조건은 셋이다.

1. 최초 의사결정 공시가 코퍼스 기간(2023-01-01~2026-03-31) **안에** 있다
2. 그 뒤에 정정/변경/해지 공시가 **같은 사건에 대해** 존재한다
3. 최초 시점 **이전**에 판단 근거로 쓸 재무자료(정기보고서)나 계약 공시가 있다

코퍼스의 유형별 분포(실측):

| doc_group / doc_subtype | 건수 |
|---|---|
| exchange / 단일판매공급계약체결 | 1,106 |
| holding / 대량보유상황보고서 | 1,083 |
| major (주요사항보고서) | 598 |
| periodic (annual/half/quarter) | 1,054 |
| exchange / 투자판단관련주요경영사항 | 300 |
| exchange / **신규시설투자등** | **43** |
| exchange / 단일판매공급계약해지 | 20 |

신규시설투자등 43건이 가장 밀도가 높았다 — 투자금액·자기자본·자기자본대비·투자기간이
**정형 필드로 고정**되어 있고, 정정공시가 `정정전/정정후` 표를 그대로 담기 때문에
Reality Replay를 만들 때 사람이 해석을 덧붙일 필요가 없다.

## 2. 후보 비교표

7점 척도가 아니라 5점 만점. 마지막 열은 총점.

| # | 후보 사건 | 사건 이해 용이성 | 시간축 명확성 | 판단 갈등 | Evidence 충분성 | 교육 금융개념 | Reality Replay 재미 | 데모 안정성 | 계 |
|---|---|---|---|---|---|---|---|---|---|
| **A** | **에코프로비엠 CAM9 증설**<br>2023-05-23 결의(4,732억, 자기자본 31.8%) → 2024-10-22 정정(종료일 2년 연기, 사유 "전방시장 수요 변동성 확대") | 5 | 5 | **5** | **5** | 5 | **5** | 5 | **35** |
| **B** | **LS ELECTRIC 초고압 변압기 증설**<br>2024-05-21 결의(803억, 자기자본 4.7%) → 2024-08-13 정정(1,008억으로 증액) | 5 | 5 | 3 | 5 | 4 | 4 | 5 | 31 |
| **C** | **삼성바이오로직스 송도 5공장**<br>2023-03-17 결의(1조 9,801억, 자기자본 22.01%) → 2023-06-05 정정(일정 5개월 단축) → 2024-12-18 정정(297억 증액) | 4 | 5 | 4 | 3 | 5 | 5 | 4 | 30 |
| D | 레인보우로보틱스 사옥·제조시설 신축<br>2024-04-30(278.5억) → 2025-02-05 정정(281.8억, +1.2%) | 4 | 4 | 1 | 2 | 3 | 1 | 5 | 20 |
| E | HMM 메탄올 추진선 9척<br>2023-02-14(1조 4,128억). 코퍼스 내 정정 2건은 원본이 2020·2021년이라 **코퍼스 밖** | 3 | 2 | 3 | 3 | 4 | 3 | 2 | 20 |
| F | 두산퓨얼셀 연료전지 공급계약 해지<br>원본 2022-04-27(코퍼스 밖) → 2023-03-31 정정 → 2024-06-03 **해지**(193억, 매출액 대비 5.06%) | 4 | 3 | 4 | 2 | 4 | 5 | 2 | 24 |
| G | 삼성E&A / 효성중공업 공급계약 해지<br>해지 공시는 있으나 원계약이 코퍼스 기간 밖 | 3 | 2 | 3 | 1 | 3 | 4 | 2 | 18 |

### 감점 사유 (핵심만)

- **D 레인보우로보틱스**: 정정 폭이 +1.2%다. "판단이 뒤집히는" 사건이 아니라 단순 설계변경이라
  게임의 결정 화면이 무의미해진다.
- **E HMM / F 두산퓨얼셀 / G**: 정정·해지 공시는 코퍼스 안에 있지만 **원계약이 2020~2022년**이라
  코퍼스 밖이다. 즉 simulation_date를 원본 시점으로 잡을 수 없고, "당시 공시만 조사한다"는
  게임 규칙을 원본 없이 세워야 한다. 데모 안정성 2점.
- **F**는 해지 사유("고객사의 계약 발효 조건 미이행")가 극적이라 Reality Replay 재미는 5점이다.
  원계약이 코퍼스에 들어오면 4순위 후보로 승격할 만하다.

## 3. 최종 선정 — CASE-001 / 002 / 003

### CASE-001 에코프로비엠 (1순위, 완성 우선)

- **왜 1등인가**: 판단 갈등이 데이터 안에 이미 들어 있다. 같은 분기보고서 안에
  "생산능력 2년 만에 3배"(증설 근거)와 "탄산리튬 가격 68% 급락"·"매출처 집중도 98.1%"
  (증설 반대 근거)가 동시에 적혀 있다. 플레이어가 어느 쪽을 더 봤는지에 따라 결론이 갈린다.
- **재무 연결이 깨끗하다**: 공시의 `자기자본 1,488,215,127,423원`이 분기보고서 요약재무정보의
  `자본총계` 전기 값과 **정확히 일치**한다. "공시 숫자가 어디서 왔는지"를 플레이어가
  직접 대조할 수 있다 — 금융교육 관점에서 가장 좋은 재료다.
- **현금 < 투자금액**: 보유 현금 2,390억원 < 투자금액 4,732억원. 자금조달이 반드시 필요하다는
  결론이 산수로 나온다. 그리고 실제로 5주 뒤 CB 4,400억원이 발행된다(Reality Replay).
- **Reality Replay가 4단계**: CB 발행(2023-06-30) → 삼성SDI 43.8조 장기공급계약(2023-12-01)
  → **증설 2년 연기**(2024-10-22) → 신종자본증권 2,440억 발행(2024-10-28).
  "돈을 빌려 지었는데 수요가 늦어졌고, 다시 빚을 갚을 돈을 빌렸다"가 실제 공시만으로 나온다.

### CASE-002 LS ELECTRIC (대조군)

CASE-001과 **정반대 방향**으로 정정된 사건을 붙였다. 자기자본 대비 4.7%(vs 31.8%),
현금이 투자금액의 8배(vs 절반 이하), 수주잔고 23,261억원이 이미 쌓인 상태 →
넉 달 뒤 정정은 축소가 아니라 **205억원 증액**이다.
같은 "신규시설투자등" 공시라도 회사 체력에 따라 결과가 갈린다는 걸 두 케이스 비교로 가르친다.
난이도 `easy`.

### CASE-003 삼성바이오로직스 (심화)

정정이 **두 번, 서로 다른 방향**으로 온다: 일정 단축(2023-06-05) 후 금액 증액(2024-12-18).
그리고 simulation_date 이전 자료가 계약 공시뿐이라, 플레이어는 재무제표 없이
`최근매출액`·`매출액대비(%)`만으로 판단해야 한다. 난이도 `hard`.

> **CASE-003의 알려진 한계**: 코퍼스의 정기공시는 FY2023부터라 2023-03-17 시점에
> 직전 사업보고서가 없다. 그래서 CASE-003만 `available_documents`가 4건(최소치)이고
> `role: financials` 문서가 없다. intro에 이 사실을 명시해 두었다.

## 4. Future Leakage 처리

`simulation_date`를 기준으로 두 집합이 코드 수준에서 분리된다.

```
available_document.document_date <= simulation_date
future_event.date                >  simulation_date
```

`scripts/build_case_packs.py`가 빌드 중에 위반을 만나면 **즉시 SystemExit**으로 죽는다
(팩이 생성되지 않는다). `scripts/validate_case_pack.py`는 완성된 팩을 다시 검사한다:

| 검사 | 내용 |
|---|---|
| 날짜 invariant | 위 두 부등식 |
| 식별자 누출 | 미래 공시의 `doc_id`/`rcept_no` 문자열이 intro·mission·문서·evidence·선택지 어디에도 없어야 함 |
| 미래 날짜 경고 | 플레이 전 영역에 simulation_date 이후 날짜가 있으면 **경고**(error 아님) — 공시 원문의 "투자 종료 예정일 2024-12-31"은 정상이기 때문 |
| Grounding | 모든 `evidence.source_text`가 해당 문서 `original_text`의 부분 문자열 |
| 수치 날조 | `evidence.text`의 모든 숫자가 `source_text`에 존재(원 → 만/백만/억 환산만 예외) |
| 참조 무결성 | finance_terms·decision_options가 실재하는 evidence_id만 참조 |
| manifest 대조 | 모든 doc_id가 `manifest.jsonl`에 있고 공시일·기업이 일치 |

검증기 자체는 `tests/test_case_pack_validation.py`가 검증한다 — 팩을 일부러 망가뜨려
(미래 문서 삽입, doc_id 누출, 숫자 날조, 없는 원문) 검증기가 잡는지 확인한다.

## 5. 설계상 선택 몇 가지

- **정답을 저장하지 않는다.** `decision_options`에 정답 플래그가 없다. 대신 각 선택지에
  `supporting_evidence_ids` / `counter_evidence_ids` / `feedback_if_missing_critical`이 있어
  "네가 본 단서로 그 선택을 정당화할 수 있는가"로 피드백한다. 실제 기업의 행동은
  `future_events`에 그대로 두되 정답으로 취급하지 않는다.
- **원문은 표를 행 단위로 직렬화한 평문**이다(`scripts/case_pack_render.py`).
  `original_text`가 줄 리스트를 이어 붙인 것이라 `display_excerpt`·`source_text`가
  항상 연속 부분 문자열이 되고, 그래서 grounding 검사가 문자열 포함 여부만으로 성립한다.
- **정기보고서는 섹션만 잘라 담는다.** 사업보고서 한 건이 수 MB라 전체를 넣을 수 없다.
  `sections` 키워드로 필요한 절만 렌더하고, 어느 절을 썼는지 `source_locator.sections`에 남긴다.
- **기존 자산을 재사용한다.** 새 파서를 만들지 않았다. Workstream A의
  `data/artifacts/document_ir/*.jsonl`(DocumentIR)과 `manifest.jsonl`을 그대로 읽고,
  `corpus_snapshot_id`/`parser_version`을 팩의 `generator`에 기록해 재현성을 잇는다.

## 6. 현재 팩 요약

| case_id | 기업 | simulation_date | 난이도 | 조사 가능 문서 | Evidence(critical) | 금융용어 | 선택지 | Reality Replay |
|---|---|---|---|---|---|---|---|---|
| CASE-001 | 에코프로비엠 | 2023-05-23 | normal | 5 | 15 (8) | 5 | 4 | 4건 |
| CASE-002 | LS ELECTRIC | 2024-05-21 | easy | 5 | 13 (7) | 5 | 4 | 3건 |
| CASE-003 | 삼성바이오로직스 | 2023-03-17 | hard | 4 | 9 (6) | 5 | 4 | 3건 |

## 7. 실행 방법

```bash
# 0) 전제: DocumentIR이 로컬에 있어야 한다 (README의 run_full_corpus.py 참고)
#    data/artifacts/document_ir/{periodic,major,exchange,holding}.jsonl

# 1) Case가 참조하는 문서만 캐시로 추출 (periodic.jsonl 8.1GB 1회 스캔, 실측 약 6분)
PYTHONIOENCODING=utf-8 python scripts/extract_case_source_docs.py
#    -> data/artifacts/case_packs/_source_docs.jsonl (약 50MB, .gitignore 대상)

# 2) Case Pack 빌드
PYTHONIOENCODING=utf-8 python scripts/build_case_packs.py
#    -> data/artifacts/case_packs/CASE-00{1,2,3}.json, index.json
#    -> docs/demo_case_evidence_map.md

# 3) Future Leakage / Grounding 검증
PYTHONIOENCODING=utf-8 python scripts/validate_case_pack.py
#    -> "3/3 case packs valid"

# 4) 검증기 자체 테스트
python -m pytest tests/test_case_pack_validation.py -q
```

특정 Case만 다루려면:

```bash
PYTHONIOENCODING=utf-8 python scripts/build_case_packs.py --case CASE-001
PYTHONIOENCODING=utf-8 python scripts/validate_case_pack.py data/artifacts/case_packs/CASE-001.json
```

경고까지 실패로 취급하려면 `--strict`.

### Case를 추가할 때

1. `scripts/case_definitions.py`에 새 dict를 쓰고 `CASES`에 추가
2. 참조하는 doc_id를 `scripts/extract_case_source_docs.py`의 `DEFAULT_DOC_IDS`에 추가
3. 1~3단계 재실행. 빌드가 통과하면 원문 매칭과 leakage는 이미 보장된 상태다

## 8. 남은 일 (데모 범위 밖으로 의도적으로 남김)

- 4번째 Case: 두산퓨얼셀 공급계약 해지 — 원계약(2022-04-27)을 코퍼스에 추가 수집해야 성립
- `educational_reason` 안의 파생 지표(부채비율 165% 등)는 자동 검증 대상이 아니다.
  현재는 사람이 계산해 적고 리뷰로 확인한다
- 검색(BM25/Dense) 연동 없음. 데모 Case Pack은 정적 산출물이고,
  `experiments/retrieval_benchmark/`의 검색 파이프라인과는 아직 붙이지 않았다
