# DART Corpus — Workstream A Handoff

Workstream A(Manifest/Universe Loader, Corpus Snapshot, Canonical Parser, DocumentIR)의
코드와 handoff 산출물. Workstream B(Chunking/Retrieval)와 C(Artifact Loader/Experiment
Runner)가 여기서 시작한다.

**전제**
- 원본 DART corpus는 이 저장소에 없다 — B/C 모두 각자 로컬에 이미 보유하고 있다는 전제.
- 전체 DocumentIR(실측 약 8.61GB, `data/artifacts/document_ir/*.jsonl`)도 이 저장소에 없다
  (`.gitignore` 참고). 아래 명령으로 로컬에서 재생성하거나 별도 공유 저장소를 쓴다.
- B용/C용 파일을 따로 두 벌 만들지 않는다 — 이 저장소 하나가 공통 source of truth다.

## 저장소 구조(핵심만)

```
schemas/document_ir_schema_v0.json         DocumentIR JSON Schema(status: proposed)
docs/document_ir_contract.md               필드설명+ID규칙+저장형식+parser_version 등 통합 계약 문서
src/dart_corpus/                           Workstream A 소스(contract/, parsing/)
scripts/run_full_corpus.py                 전체 4204건 파싱 실행
scripts/generate_handoff_samples.py        대표 샘플 11건 생성
scripts/generate_parser_gold_candidates.py Parser Gold 후보(90건) 생성 — 후보일 뿐 정답 아님
scripts/compute_document_ir_hashes.py      DocumentIR canonical hash manifest 생성
scripts/build_a_handoff_manifest.py        handoff 색인(a_handoff_manifest.json) 생성
data/artifacts/corpus_snapshot.json        Corpus Snapshot(해시+게이트 리포트)
data/artifacts/parse_summary.json          tier/doc_group/warning 분포 집계
data/artifacts/parse_audit.jsonl           문서별 파싱 감사 기록
data/artifacts/parser_gold_candidates.jsonl / parser_gold_annotation_template.csv
data/artifacts/handoff/                    B/C 공통 handoff 색인 + 대표 샘플 + hash manifest
data/artifacts/document_ir/*.jsonl         전체 DocumentIR(.gitignore로 제외, 로컬 전용)
```

## 설치

```bash
pip install -e .
pip install -r requirements-lock.txt   # 정확한 버전(재현성) — pyproject.toml은 범위(>=)만 고정
```

## 테스트

```bash
pytest -m "not integration"   # 빠름(수 초) — 실제 corpus 없이도 돎(합성 fixture 위주)
pytest -m integration         # 느림(실제 corpus 필요, 전체 4204건 스캔 포함)
```

---

## Workstream B(Chunking/Retrieval) 사용법

전체 DocumentIR이 필요하다. 두 가지 방법:

1. **이미 생성된 artifact 사용**(로컬에 있으면): `data/artifacts/document_ir/{periodic,major,exchange,holding}.jsonl`
2. **동일 parser_version으로 로컬 재생성**:
   ```bash
   PYTHONIOENCODING=utf-8 python3 scripts/run_full_corpus.py --out-dir data/artifacts
   # 실측 36.3분(네트워크 마운트 기준 — 로컬 디스크면 더 빠를 수 있음)
   ```

사용할 재현성 키: `data/artifacts/handoff/a_handoff_manifest.json`의
`corpus_snapshot_id` / `parser_version` / `parser_config_hash`. doc_group별 문서 수는
`doc_group_counts` 필드 참고.

**재생성 후 검증**:
```bash
# 1) corpus_snapshot_id 비교(원본 corpus가 같으면 항상 같은 값이어야 함)
python -c "import json; print(json.load(open('data/artifacts/corpus_snapshot.json', encoding='utf-8'))['corpus_snapshot_id'])"

# 2) 전체 문서 수 4204 확인
python -c "import json; s=json.load(open('data/artifacts/parse_summary.json', encoding='utf-8')); print(s['total_documents'], s['n_success'], s['n_failed'])"

# 3) document_ir_hash_manifest 재계산 후 비교(8.61GB를 다시 읽어야 함 — 한 번만)
python3 scripts/compute_document_ir_hashes.py --out-dir data/artifacts
python -c "import json; a=json.load(open('data/artifacts/handoff/document_ir_hash_manifest.json', encoding='utf-8')); print(a['corpus_document_ir_hash'], a['group_hashes'])"
# 위 corpus_document_ir_hash/group_hashes가 git에 커밋된 값과 다르면 재현 실패 — parser_config_hash와
# dependency 버전(requirements-lock.txt)부터 비교할 것

# 4) 테스트
pytest -m "not integration"
```

---

## Workstream C(Artifact Loader/Experiment Runner) 사용법

우선 스키마 + 대표 샘플 11건만 있으면 개발을 시작할 수 있다. 전체 DocumentIR은
**통합 테스트 단계에서만** 연결한다.

- 스키마: `schemas/document_ir_schema_v0.json`
- 대표 샘플: `data/artifacts/handoff/representative_documents.jsonl`(11건 — dart3/dart4 ×
  periodic/major/holding, exchange HTML-in-.xml, pdf+viewer HTML, 첨부 포함, sanitizer 사용,
  fallback, TABLE-GROUP 내부 TITLE, rowspan/colspan, 다중 header 전부 커버)
- 필드 설명/ID 규칙/source_locator 규칙/warning 형식: `docs/document_ir_contract.md`

**schema validation**:
```bash
pip install jsonschema   # 또는 pip install -e .[dev]
python -c "
import json, jsonschema
schema = json.load(open('schemas/document_ir_schema_v0.json', encoding='utf-8'))
validator = jsonschema.Draft202012Validator(schema)
with open('data/artifacts/handoff/representative_documents.jsonl', encoding='utf-8') as f:
    for line in f:
        doc = json.loads(line)
        errors = list(validator.iter_errors(doc))
        print(doc['doc_id'], 'OK' if not errors else errors)
"
```

---

## 알려진 이슈 — periodic 문서 parse_quality 주의

**periodic 1054건 전체가 `structured`가 아니다**(partial 975 + fallback 79, structured 0).
원인을 오해하지 않도록 정확히 구분해서 봐야 한다(전수, `data/artifacts/parse_audit.jsonl`
실측):

| 원인 | 문서 수 | `text_preservation_ratio` 평균 | 실질 텍스트 손실? |
|---|---|---|---|
| sanitizer 사용(bare `&`/`<` 이스케이프)만으로 partial | 972 | **1.02** | **없음** — 파싱 성공, tier만 규칙상 강등 |
| pdf+html 강제 partial(PDF 자체는 안 읽음) | 3 | 0.30 | 있음(3건 중 2건은 `<table>` 0개라 완전 손실(ratio 0.0), 1건만 실질 파싱) |
| fallback(XML well-formed 실패, 태그 벗겨낸 raw text만 보존, 20000자 절단) | 79 | 0.14 | 있음(큼) |

즉 **partial 975건 중 972건은 사실상 structured와 다름없다**(정보 손실 없음, tier
판정 규칙이 sanitizer 사용 여부에만 민감하기 때문). 실제로 걱정해야 할 대상은
**fallback 79건 + pdf+html 3건 = 82건**뿐이다. fallback 79건과 pdf+html 중 완전
손실 2건(둘 다 `parse_failed` 경고 있음)은 **서로 다른 별개 문서 집합**이다 — 혼동
방지용 상세 목록은 `data/artifacts/handoff/parse_failure_cases.jsonl`. 상세: `docs/document_ir_contract.md`
§ periodic parse quality.

## 데모 Case Pack (금융 탐정게임)

실제 공시에서 고른 사건 3건을 프론트엔드가 바로 쓸 수 있는 Case Pack JSON으로 만든다.
전체 코퍼스를 게임으로 변환하지 않는다 — 데모용 사건만 고품질로 만든다.

```bash
PYTHONIOENCODING=utf-8 python scripts/extract_case_source_docs.py   # 참조 문서만 캐시(약 6분)
PYTHONIOENCODING=utf-8 python scripts/build_case_packs.py           # Case Pack 생성
PYTHONIOENCODING=utf-8 python scripts/validate_case_pack.py         # Future Leakage/Grounding 검증
python -m pytest tests/test_case_pack_validation.py -q              # 검증기 자체 테스트
```

| case_id | 기업 | 사건 | simulation_date |
|---|---|---|---|
| CASE-001 | 에코프로비엠 | CAM9 증설 4,732억원(자기자본 31.8%) → 2년 연기 | 2023-05-23 |
| CASE-002 | LS ELECTRIC | 초고압 변압기 증설 803억원 → 1,008억원 증액 | 2024-05-21 |
| CASE-003 | 삼성바이오로직스 | 송도 5공장 1조 9,801억원 → 일정 단축 후 증액 | 2023-03-17 |

- 설계/후보 비교/선정 이유: `docs/demo_case_pack.md`
- 사용 공시 목록 + Evidence 출처 매핑(자동 생성): `docs/demo_case_evidence_map.md`
- 스키마: `schemas/case_pack_schema_v0.json`
- 산출물: `data/artifacts/case_packs/CASE-00{1,2,3}.json` + `index.json`

`simulation_date` 이후 공시는 `future_events`에만 들어간다. 빌드 중 위반이 발견되면
빌드가 실패하고, 완성된 팩은 `validate_case_pack.py`가 날짜 invariant·식별자 누출·
원문 grounding·수치 날조를 다시 검사한다.

## 웹 데모 — 공시 탐정사무소 🔍

실제 공시를 읽고 단서를 모아 판단하면 미래가 열리는 브라우저 데모.
새 프론트 프레임워크 없이 FastAPI가 바닐라 SPA(`src/dart_detective/static/`)를 그대로 서빙한다.

```bash
pip install -e ".[agent]"
PYTHONIOENCODING=utf-8 python scripts/build_case_search_index.py      # 최초 1회
PYTHONIOENCODING=utf-8 DART_DETECTIVE_LLM=off \
  uvicorn dart_detective.api:app --port 8000
# 브라우저에서 http://127.0.0.1:8000/
```

플레이 루프: **사건 파일 → 조사실 → 공시 원문 읽기 → 형광펜 단서 수집 → 금융수첩 →
사건 단서판 → AI 탐정 조수 → 판단 → Reality Replay → CASE COMPLETE**

- 공시는 요약본이 아니라 **원문**을 렌더하고, Case Pack evidence의 `source_text` 위치에
  형광펜을 친다. 클릭하면 단서가 수첩으로 날아가고 관련 금융용어가 열린다.
- AI 조수: 힌트(Tutor Agent)·자유질문(Evidence Agent). **둘 다 실패해도 메인 루프는 진행된다.**
  용어 설명과 "이 숫자가 왜 중요해?"는 Case Pack 데이터라 LLM이 아예 필요 없다.
- Reality Replay는 판단 확정 전 잠금이고, LLM을 타지 않아 항상 같은 결과가 나온다.
- 상단 `↺ 처음부터`로 시연 중 언제든 리셋. 조사 포인트는 첫 화면에서 끌 수 있다.

브라우저 E2E + 스크린샷 갱신:

```bash
pip install playwright && python -m playwright install chromium
PYTHONIOENCODING=utf-8 python scripts/run_web_demo_e2e.py     # 13개 화면 캡처 + 화면별 assert
```

화면 설명·시연 순서·스크린샷: `docs/web_demo.md`

### 배포 (남에게 링크 공유)

**Render 무료** — 저장소에 `render.yaml`(Blueprint)이 있어서 클릭 몇 번이면 끝난다.

1. https://dashboard.render.com → **New → Blueprint** → 이 저장소 선택 → **Apply**
2. 빌드 로그는 서비스의 **Logs** 탭. 끝나면 `https://<서비스>.onrender.com`
3. 배포본 검증: `python scripts/run_web_demo_e2e.py --base-url https://<서비스>.onrender.com`

무료 플랜은 15분 유휴 시 절전 → 첫 접속에 약 1분. 발표 직전에 한 번 열어 깨워두면 된다.

**발표 당일 라이브 시연**은 터널이 더 확실하다(콜드스타트 없음).

```bash
uvicorn dart_detective.api:app --port 8000
cloudflared tunnel --url http://localhost:8000
```

Streamlit은 쓰지 않는다 — 이미 만든 SPA를 버려야 하고, 지금 앱은 그냥 FastAPI 컨테이너 하나다.
Hugging Face Spaces는 Docker Space가 **PRO 구독($9/월)** 대상이라 무료로는 못 쓴다.
공개 배포용으로 세션 상한(`max_sessions` / TTL)과 단일 워커 고정을 넣어 두었다.
옵션 비교·주의사항: `docs/deploy.md`

## 탐정 Agent Backend (LangGraph + Point-in-Time RAG)

Case Pack을 실제 플레이 가능한 백엔드로 만든 것. `src/dart_detective/`.

```bash
pip install -e ".[agent]"

PYTHONIOENCODING=utf-8 python scripts/build_case_search_index.py   # 검색 인덱스(과거+미래 chunk)
PYTHONIOENCODING=utf-8 python scripts/run_case_e2e.py              # Case 1건 E2E 실행
PYTHONIOENCODING=utf-8 uvicorn dart_detective.api:app --port 8000  # API 서버

python -m pytest tests/test_point_in_time_retriever.py tests/test_evidence_validator.py \
                 tests/test_agent_graph.py tests/test_api.py -q
```

- **Point-in-Time Retrieval**: 모든 검색이 `document_date <= simulation_date`를 통과한다.
  Prompt가 아니라 Retriever 계층에서 후보 풀을 자르고, 검색 후 한 번 더 assertion을 건다.
  인덱스에는 미래 문서도 들어 있어서, 필터를 끄면 미래 공시가 잡히는 것으로 필터가 실제로
  일한다는 걸 증명한다.
- **Deterministic Action Router**: 버튼 행동(`research`/`hint`/`term`/`decision`/`replay`/
  `open_document`)은 LLM routing 없이 노드로 직행. LLM은 research·hint에서만 호출되고,
  자격증명이 없으면 결정론적 fallback으로 동작한다(`DART_DETECTIVE_LLM=off`로 강제 가능).
- **Evidence Validator**: Agent 주장을 원문과 대조해 `SUPPORTED / PARTIALLY_SUPPORTED /
  UNSUPPORTED`로 판정. 원문에 없는 숫자를 만들면 LLM 답변을 폐기하고 발췌 답변으로 되돌린다.
- **Reality Replay 잠금**: 판단 확정 전에는 호출 불가. 미래 Event는 LLM이 생성하지 않고
  Case Pack 데이터를 그대로 쓴다.

설계·Mermaid 그래프·E2E 실행 결과: `docs/agent_backend.md`

## 문서 색인

| 문서 | 내용 |
|---|---|
| `docs/document_ir_contract.md` | 필드설명 / section_path / table_group_id·table_id·row_id / source_locator / warning 형식 / 저장형식 / parser_version / 재현성 / gap 전체 |
| `data/artifacts/handoff/a_handoff_manifest.json` | 이 handoff의 단일 색인(버전/해시/경로/재생성 명령/known_gaps) |
| `data/artifacts/handoff/document_ir_hash_manifest.json` | doc_group별 + 전체 corpus canonical hash(8.61GB 재다운로드 없이 재현성 검증용) |
| `docs/demo_case_pack.md` | 데모 Case Pack 후보 비교표 / 선정 이유 / Future Leakage 처리 / 실행 방법 |
| `docs/demo_case_evidence_map.md` | Case별 사용 공시 목록 + Evidence 출처 매핑(빌드 시 자동 생성) |
| `docs/agent_backend.md` | LangGraph 그래프(Mermaid) / GameState / Point-in-Time Retriever / Agent·Validator / API / E2E 실행 결과 |
| `docs/web_demo.md` | 웹 데모 화면 구성 / 프론트·백엔드 역할 분리 / 데모 안정성 설계 / 시연 순서 / 스크린샷 |
| `docs/deploy.md` | 배포 옵션 비교 / HF Spaces 절차 / Docker / 터널 / 공개 시 주의사항 |
