# 웹 데모 — 공시 탐정사무소

실제 DART 공시를 읽고 단서를 모아 판단하고, 그 뒤에 미래가 공개되는 경험을 완성한 데모.
캐릭터 이동·전투·물리엔진 같은 게임 개발 영역은 구현하지 않는다.

- 프론트엔드: `src/dart_detective/static/` (`index.html` + `styles.css` + `app.js`)
- 백엔드: 앞 단계의 LangGraph Agent Backend(`src/dart_detective/api.py`)가 그대로 서빙
- 스크린샷: `docs/screenshots/` (E2E 실행 시 자동 갱신)

## 1. 기술 선택 — 새 프레임워크를 추가하지 않았다

이 저장소의 스택은 Python + FastAPI다. 프론트엔드 빌드 체인(React/Vite/npm)이 없다.
그래서 **FastAPI가 정적 파일을 그대로 서빙하는 바닐라 SPA**로 만들었다.

| 항목 | 선택 | 이유 |
|---|---|---|
| 프레임워크 | 없음(바닐라 JS) | 저장소에 프론트 빌드 체인이 없다. 새로 들이면 데모 하나를 위해 npm 의존성이 생긴다 |
| 서빙 | `app.mount("/app", StaticFiles(...))` | 백엔드와 같은 포트/오리진 → CORS 설정 불필요 |
| 폰트·아이콘 | 시스템 폰트 + 이모지 | 외부 CDN을 쓰지 않는다. 인터넷이 끊긴 발표장에서도 그대로 뜬다 |
| 빌드 | 없음 | 파일 저장 후 새로고침이면 끝. 발표 직전 수정이 안전하다 |

## 2. 프론트 / 백엔드 역할 분리

게임 상태를 프론트가 따로 들고 있으면 LangGraph State와 반드시 어긋난다. 그래서
**프론트는 게임 상태를 만들지 않는다.** 모든 액션은 `POST /sessions/{id}/actions`를 거치고,
프론트는 응답의 `state`를 그대로 반영한다.

| 프론트 | 백엔드(LangGraph) |
|---|---|
| 화면 전환, 드로어 열림/닫힘 | 게임 진행 상태(GameState) |
| 애니메이션(단서 비행, 반짝임, 도장) | Evidence 수집 여부 |
| 선택 UI, 현재 열어본 탭 | 검색 결과(Point-in-Time) |
| 원문 하이라이트 위치 계산 | 학습한 용어, Decision, Future Unlock |

프론트가 유일하게 계산하는 "상태 비슷한 것"은 **용어 잠금 여부**다
(`source_evidence_ids` 중 하나라도 수집됐는가). 이것도 서버가 준 `found_evidence`에서
파생될 뿐 따로 저장하지 않는다.

## 3. 화면 구성

| # | 화면 | 구현 | 데이터 출처 |
|---|---|---|---|
| 0 | 사건 파일 보관함 | `#screen-cases` | `GET /cases` |
| 1 | 사건 파일(CASE 001, MISSION, 도장) | `#screen-casefile` | `POST /sessions` → briefing |
| 2 | 조사실(책상 위 서류 카드) | `#screen-desk` | briefing.documents |
| 3 | 공시 읽기(원문 + 형광펜) | `#screen-doc` | `open_document` → original_text |
| 4 | 금융수첩(드로어) | `#drawerNotebook` | `term` 액션 |
| 5 | 사건 단서판(드로어) | `#drawerBoard` | `GET /sessions/{id}/evidence` |
| 6 | AI 탐정 조수(드로어) | `#drawerAssistant` | `hint` / `research` 액션 |
| 7 | 판단하기 | `#screen-decision` | `decision` 액션 |
| 8 | Reality Replay | `#screen-replay` | `replay` 액션 |
| 9 | CASE COMPLETE | `#screen-complete` | 누적 state |

### 실제 공시 원문을 읽게 만든 방식

조사실 카드에는 `display_excerpt`를 미리보기로 깔고, 문서를 열면 **`original_text` 전문**을
등폭 글꼴로 렌더한다. 여기에 Case Pack evidence의 `source_text` 위치를 찾아
`<mark class="clue">`로 감싼다.

```js
const i = text.indexOf(o.source_text);   // 정규식이 아니라 정확한 문자열 위치
```

`source_text`는 Case Pack 빌드 단계에서 **원문의 부분 문자열임이 보장**되므로
(`scripts/validate_case_pack.py`의 grounding 검사) 하이라이트가 어긋날 수 없다.
`tests/test_api.py::test_evidence_options_carry_source_text_for_highlighting`가 이 계약을 지킨다.

형광펜 문장을 클릭하면 → 서버에 수집 요청 → 카드가 금융수첩 버튼으로 날아가고 →
토스트 "🔍 단서 획득" → 관련 금융용어가 열리면 "📖 금융용어 발견" 토스트 + 수첩 항목 반짝임.

### 사건 단서판 분류

자유로운 그래프 편집은 만들지 않았다. 수집한 단서가 카테고리에 따라 자동으로 꽂힌다.

| 보드 | Case Pack category |
|---|---|
| 💰 재무 | `finance`, `investment` |
| 🏭 사업 | `business`, `timeline` |
| ⚠️ 위험 | `risk` |

### AI 탐정 조수 — LLM이 필요한 것과 아닌 것

| 버튼 | 경로 | LLM |
|---|---|---|
| 💡 힌트 받기 | Tutor Agent (`hint`) | 선택적(없으면 템플릿 힌트) |
| 📖 이 용어가 뭐야? | 금융수첩 드로어 열기 | **불필요** |
| 🔢 이 숫자가 왜 중요해? | 마지막 수집 단서의 `educational_reason` | **불필요**(Case Pack 데이터) |
| 자유 질문 | Evidence Agent (`research`) | 선택적(없으면 원문 발췌 답변) |

답변 아래에는 근거 공시를 작게 표시하고, Evidence Validation 등급
(`SUPPORTED` / `PARTIALLY_SUPPORTED` / `UNSUPPORTED`)을 배지로 붙인다.

### 판단 화면

선택 전에 확보한 단서를 카테고리 배지와 함께 보여준다. 선택 후에는 5개 관점
(재무여력 / 시장성 / 위험 / 투자규모 / 판단 수정 가능성)을 막대와 함께
**충분히 조사 · 일부 조사 · 조사 부족**으로 정리한다.
**정답·오답 표현을 쓰지 않는다** — E2E가 `정답/오답/틀렸/맞았/성공/실패` 문자열을 금지한다.

## 4. 데모 안정성 설계

발표용이라 "무엇이 죽어도 어디까지는 굴러가는가"를 먼저 정했다.

| 실패 지점 | 결과 |
|---|---|
| LLM 자격증명 없음 | 힌트·자유질문 모두 결정론적 경로로 동작(품질만 떨어짐). 기본값이 이 상태다 |
| Evidence Agent 호출 실패 | 조수 말풍선에만 경고 표시, "조사실로 돌아가서 직접 읽어도 돼" 안내. **메인 루프는 계속 진행** |
| Tutor Agent 호출 실패 | 같은 방식으로 격리. 단서판/판단/Replay 모두 정상 |
| 검색 인덱스 없음 | `research`만 실패. 문서 열람 → 단서 수집 → 판단 → Replay는 Case Pack만으로 완주 가능 |
| Reality Replay | 항상 Case Pack의 `future_events`를 그대로 출력 — LLM을 타지 않아 deterministic |
| 진행이 꼬임 | 상단 `↺ 처음부터`(Reset) — 같은 사건을 새 세션으로 재시작 |

조사 포인트가 데모 흐름을 방해하면 첫 화면의 **`조사 포인트 사용` 체크를 끄면 된다**
(`points_enabled: false` → 서버가 차감을 건너뛴다).

## 5. 실행 방법

```bash
# 0) 전제 — Case Pack + 검색 인덱스
PYTHONIOENCODING=utf-8 python scripts/build_case_packs.py
PYTHONIOENCODING=utf-8 python scripts/build_case_search_index.py

# 1) 서버 실행 (LLM 없이도 완주 가능)
pip install -e ".[agent]"
PYTHONIOENCODING=utf-8 DART_DETECTIVE_LLM=off \
  uvicorn dart_detective.api:app --port 8000
# 브라우저에서 http://127.0.0.1:8000/  (자동으로 /app/ 으로 이동)

# LLM을 붙이려면(자격증명 필요)
PYTHONIOENCODING=utf-8 uvicorn dart_detective.api:app --port 8000
```

### E2E 실행 + 스크린샷 갱신

```bash
pip install playwright && python -m playwright install chromium

PYTHONIOENCODING=utf-8 python scripts/run_web_demo_e2e.py            # 서버 자동 기동
PYTHONIOENCODING=utf-8 python scripts/run_web_demo_e2e.py --headed --slow-mo 300   # 눈으로 보며
pytest -m integration tests/test_web_demo_e2e.py                     # 테스트로 실행
```

스크립트가 첫 화면부터 Reset까지 전부 눌러보며 화면마다 assert를 걸고
`docs/screenshots/`에 PNG 14장을 남긴다.

## 6. 시연 순서 (약 5분)

| # | 화면 | 말할 것 | 조작 |
|---|---|---|---|
| 1 | 사건 파일 보관함 | "사건 3개 전부 실제 DART 공시로 만들었습니다" | CASE 001 클릭 |
| 2 | 사건 파일 | "2023년 5월 23일로 이동합니다. **이 시점 이후 정보는 존재하지 않습니다**" | `조사 시작` |
| 3 | 조사실 | "책상 위 서류 5건. 전부 이 날짜 이전 공시입니다" | 첫 카드 클릭 |
| 4 | 공시 읽기 | "가공한 요약이 아니라 공시 원문입니다. 노란 형광펜이 단서" | 투자금액 줄 클릭 → 카드가 수첩으로 날아감 |
| 5 | 공시 읽기 | "자기자본 대비 31.8% — 용어가 열립니다" | 자기자본 줄 클릭 |
| 6 | 금융수첩 | "단서를 모으면 금융용어가 열립니다. 사전이 아니라 '이번 사건에서 왜 필요한가'" | 자기자본 클릭 |
| 7 | 조사실 → 재무 문서 | "회사 체력을 봐야죠" | 분기보고서 열고 현금·부채 단서 수집 |
| 8 | AI 조수 | "답을 알려주는 게 아니라 어디를 보라고만 합니다" | `💡 힌트 받기` |
| 9 | AI 조수 | "자유 질문은 공시를 검색해서 **원문 인용**으로만 답합니다" | "이 회사가 이 투자를 감당할 수 있어?" → 근거 공시 + 검증 배지 |
| 10 | 단서판 | "모은 단서가 재무/사업/위험으로 자동 분류됩니다" | 단서판 열기 |
| 11 | 판단 | "정답을 맞히는 게임이 아닙니다" | `규모 축소` 선택 |
| 12 | 판단 결과 | "무엇을 조사했고 무엇을 안 봤는지만 알려줍니다" | 커버리지 확인 |
| 13 | Reality Replay | **"이제 미래를 엽니다"** | `WHAT ACTUALLY HAPPENED?` |
| 14 | Timeline | "실제로는 5주 뒤 CB 4,400억을 발행했고, 1년 5개월 뒤 증설을 2년 미뤘습니다. 전부 실제 공시입니다" | 스크롤 |
| 15 | CASE COMPLETE | "발견한 용어와 조사 습관만 남깁니다. 점수는 없습니다" | `↺ 처음부터` 로 리셋 시연 |

> 백업 플랜: 네트워크·LLM이 죽으면 8·9번만 건너뛰고 그대로 진행한다. 나머지는 전부
> Case Pack + 로컬 인덱스로 동작한다.

## 7. 스크린샷

| 파일 | 화면 |
|---|---|
| `01-case-select.png` | 사건 파일 보관함 |
| `02-case-file.png` | 사건 파일(MISSION, CONFIDENTIAL 도장) |
| `03-desk.png` | 조사실(서류 카드) |
| `04-document-read.png` | 공시 원문 + 형광펜 단서 |
| `05-clue-collected.png` | 단서 획득 토스트 + 금융용어 발견 |
| `06-notebook.png` | 금융수첩(용어 상세) |
| `07-clue-board.png` | 사건 단서판(포스트잇 3분류) |
| `08-assistant.png` | AI 탐정 조수(힌트 + 자유질문 + 근거 공시 + 검증 배지) |
| `09-assistant-failure-isolated.png` | **Agent 호출을 강제로 끊었을 때** — 조수만 경고, 게임은 계속 |
| `10-decision-options.png` | 판단 선택지 + 확보 단서 |
| `11-decision-result.png` | 나의 판단 근거(조사 커버리지) |
| `12-reality-replay.png` | Reality Replay 타임라인 |
| `13-case-complete.png` | CASE COMPLETE 도장 |
| `14-reset.png` | Reset 후 초기 상태 |

E2E 스크립트는 9번 화면을 만들 때 실제로 `research` 요청만 골라 `route.abort()`로 끊고,
경고 문구가 뜨는지 · 수집한 단서 수가 그대로인지를 assert한다. "Agent가 죽어도 메인 게임은
진행 가능"이 문서상의 주장이 아니라 테스트로 강제된다.

## 8. 만들지 않은 것

- 캐릭터 이동 / 전투 / 물리엔진 / 맵
- 자유로운 단서 그래프 편집(카드 자동 분류로 대체)
- 점수·랭킹·업적 시스템(발견 용어와 조사 습관 요약만)
- 로그인 / 저장 / 멀티플레이
- 복잡한 애니메이션(트랜지션 6종만: 단서 비행 · 용어 반짝임 · 포스트잇 등장 ·
  잠금 흔들림 · 타임라인 순차 등장 · CASE COMPLETE 도장)

## 9. 남은 일

- 세션이 `InMemorySaver`라 서버 재시작 시 진행이 사라진다(발표용으로는 Reset이면 충분)
- 모바일 레이아웃은 최소한만 대응(드로어 전체폭 전환)
- 화면 낭독(스크린리더) 대응은 미적용
