# 배포 — 남이 볼 수 있게 올리기

## 0. 결론부터

**Streamlit은 쓰지 않는다.** 이미 FastAPI + 정적 SPA로 만들어 둔 화면이 있고,
Streamlit으로 옮기면 그걸 전부 버려야 한다.

- 형광펜 클릭으로 단서 수집, 단서가 수첩으로 날아가는 애니메이션, 드로어 3종,
  타임라인 순차 등장 — Streamlit 위젯으로는 만들 수 없거나 `st.components.html`로
  통째 iframe을 박아야 한다. 그럴 거면 지금 구조가 더 낫다.
- Streamlit은 매 인터랙션마다 스크립트를 재실행한다. LangGraph 세션 상태와
  `st.session_state`가 이중으로 생겨 상태 관리가 지금보다 복잡해진다.
- 지금 앱은 **평범한 FastAPI 컨테이너 하나**다. 배포 난이도도 Streamlit보다 낮으면 낮았지 높지 않다.

> ⚠️ **정정 (2026-08 실측):** 처음에 Hugging Face Spaces를 "무료"로 안내했으나 **틀렸다.**
> 실제로 push하자 `402 Payment Required`가 떴다:
> *"Static Spaces are free for everyone, but hosting Gradio and Docker Spaces on free
> cpu-basic requires a PRO subscription."*
> HF에서 **Docker Space는 PRO 구독($9/월)이 필요**하다. 무료는 Static Space뿐이고,
> 그건 파이썬 백엔드를 못 돌린다. 아래 표를 그에 맞게 고쳤다.

## 1. 옵션 비교 (2026-08, 각 제공사 공식 페이지 확인)

| 방법 | 비용 | 카드 | 공개 URL | 언제 |
|---|---|---|---|---|
| **Render 무료** | 무료(750시간/월) | 불필요 | ✅ 상시 | **상시 링크 1순위.** Dockerfile 그대로 빌드 |
| **Cloudflare Tunnel / ngrok** | 무료 | 불필요 | ✅ 임시 | **발표 당일 라이브.** 즉시 되고 콜드스타트 없음 |
| Hugging Face Spaces (Docker) | **PRO $9/월** | 필요 | ✅ 상시 | HF에 꼭 올려야 할 때만 |
| Google Cloud Run | 종량제(소규모 무료) | **필요** | ✅ 상시 | 카드 등록이 괜찮다면 |
| ~~Koyeb 무료~~ | **없어짐** | — | — | 가격 페이지 기준 Pro $29/월부터. "무료 512MB"는 옛 정보 |
| ~~Fly.io 무료~~ | **없어짐** | — | — | 신규 사용자 무료 티어 폐지 |
| GitHub Pages / Netlify / HF Static Space | 무료 | 불필요 | ✅ | ❌ **불가.** 정적 호스팅이라 Python 백엔드가 안 돈다 |

> 무료 티어는 자주 바뀐다. 이 문서에서만 두 번 틀렸다 — HF(무료인 줄 알았으나 Docker는 PRO),
> Koyeb(무료 컴퓨트가 이미 폐지). 블로그 글 말고 **제공사 가격 페이지를 직접** 볼 것.

### Render 무료 플랜 실제 조건

- 750 인스턴스 시간/월 (한 서비스를 상시로 켜두기 충분)
- **15분 유휴 시 절전.** 다음 접속에서 기상까지 **약 1분**(로딩 화면이 뜬다)
- 영구 디스크 없음 — 우리 앱은 디스크에 쓰지 않으니 무관
- 카드 없이 사용 가능

> 심사위원이 링크를 누르는 시점에 잠들어 있으면 1분을 기다린다. **발표 직전에 한 번
> 열어서 깨워두거나**, 라이브 시연은 Cloudflare Tunnel로 하는 편이 안전하다.

### 메모리 실측 — 512MB 무료 티어에 들어간다

무료 티어(Koyeb/Render 512MB)에 맞는지 직접 재봤다.

```
세션 5개 생성 + 문서 열람 + 자유질문 검색까지 돌린 뒤
python 프로세스 RSS: 88.4MB
```

여유가 크다. `DART_DETECTIVE_MAX_SESSIONS`(기본 50)로 상한이 걸려 있어 무한히 늘지도 않는다.

## 2. Render 무료로 배포 (권장)

저장소에 `render.yaml`(Blueprint)이 들어 있어서 클릭 몇 번이면 끝난다.

### 2-1. 코드가 GitHub에 있어야 한다

Render는 GitHub 저장소에서 Dockerfile을 빌드한다. 필요한 것은 전부
`github.com/yunkong03/ai_festival` main에 올라가 있다(Dockerfile, render.yaml,
`src/dart_detective/`, `data/artifacts/case_packs/*.json`).

### 2-2. Blueprint로 서비스 만들기

1. https://dashboard.render.com 가입 (GitHub 계정으로 로그인하면 저장소 연결이 같이 된다)
2. **New → Blueprint**
3. `ai_festival` 저장소 선택 → Render가 `render.yaml`을 읽는다
4. **Apply** → 빌드 시작

`render.yaml`이 지정하는 것:

| 항목 | 값 |
|---|---|
| runtime | `docker` (루트 `Dockerfile` 사용) |
| plan | `free` |
| region | `singapore` (한국에서 가장 가까움) |
| healthCheckPath | `/health` |
| env | `DART_DETECTIVE_LLM=off`, 세션 상한 30, TTL 1800초 |

빌드 로그는 서비스 페이지의 **Logs** 탭에 실시간으로 뜬다. 끝나면
`https://dart-detective-<해시>.onrender.com` 주소가 나온다.

### 2-3. 배포본 검증

빌드가 끝나면 **배포된 주소에 대고 브라우저 E2E를 그대로 돌린다.** 14화면이 전부
통과하면 진짜로 동작하는 것이다.

```bash
PYTHONIOENCODING=utf-8 python scripts/run_web_demo_e2e.py   --base-url https://<서비스주소>.onrender.com
```

> 첫 실행은 절전에서 깨우느라 느릴 수 있다. 한 번 브라우저로 열어 깨운 뒤 돌리면 빠르다.

### 2-4. (선택) LLM 켜기

Render 대시보드 → 서비스 → **Environment**:

| Key | Value |
|---|---|
| `DART_DETECTIVE_LLM` | `on` |
| `ANTHROPIC_API_KEY` | `sk-ant-...` (Secret) |

**공개 URL에 키를 붙이면 아무나 내 계정으로 호출한다.** 레이트 리밋이 없으므로
심사용 상시 공개라면 끄고 두는 편을 권한다.

### 2-5. 자주 걸리는 것

| 증상 | 원인 / 조치 |
|---|---|
| Blueprint에 저장소가 안 보임 | Render의 GitHub 앱에 해당 저장소 접근 권한을 줘야 한다(Configure account) |
| 빌드는 성공, 헬스체크 실패 | 앱이 `$PORT`를 읽어야 한다. Dockerfile CMD가 이미 그렇게 되어 있으니 수정하지 말 것 |
| 첫 접속이 1분 걸림 | 무료 플랜 절전. 정상이다 |
| 진행이 초기화됨 | 세션이 서버 메모리. 재기동하면 리셋(상단 `↺ 처음부터`) |

## 2. Hugging Face Spaces — **PRO 구독 필요**

### 2-1. 배포 디렉터리 만들기

> Docker Space는 무료 cpu-basic에서 돌지 않는다. PRO 구독이 있거나 결제할 의사가 있을 때만
> 이 절을 따르면 된다. 무료로 가려면 §1의 Koyeb / Cloudflare Tunnel을 보라.

저장소를 통째로 올리지 않는다. 이 저장소에는 데모에 필요 없는 대용량 산출물이 섞여 있다
(DocumentIR 8.6GB, 원본 코퍼스). Dockerfile이 COPY하는 것과 **정확히 같은 파일 집합**만 모은다.

```bash
PYTHONIOENCODING=utf-8 python scripts/prepare_hf_space.py --check
# -> dist/hf-space/  (26 files, 0.3MB)
#    --check: 인덱스 빌드 + 앱 임포트까지 실제로 돌려본다
```

만들어지는 것:

```
dist/hf-space/
├── README.md                       # HF Space 메타데이터(sdk: docker, app_port: 7860) + 플레이 설명
├── Dockerfile
├── src/dart_detective/             # 백엔드 + 정적 프론트(static/)
├── scripts/build_case_search_index.py, case_pack_render.py
└── data/artifacts/case_packs/CASE-00{1,2,3}.json, index.json
```

### 2-2. Space 만들고 push

**한 번만 준비:**

1. https://huggingface.co 가입
2. https://huggingface.co/settings/tokens → **New token** → Type **Write** → 복사
3. 로그인

```bash
pip install "huggingface_hub[cli]"
hf auth login          # 토큰 붙여넣기 (입력이 화면에 안 보이는 게 정상)
```

**푸시:**

```bash
PYTHONIOENCODING=utf-8 python scripts/push_hf_space.py --repo-id <아이디>/dart-detective
```

이 스크립트가 하는 일:

1. 로그인 확인(`whoami`) — 안 되어 있으면 여기서 안내하고 멈춘다
2. `prepare_hf_space.py --check` 실행 → 배포 디렉터리 조립 + 인덱스 빌드 + 임포트 스모크
3. Space 생성(`sdk=docker`, 이미 있으면 재사용)
4. 폴더 업로드

끝나면 두 개의 주소가 찍힌다.

- 빌드 로그: `https://huggingface.co/spaces/<아이디>/dart-detective` → **Logs** 탭
- 게임 주소: `https://<아이디>-dart-detective.hf.space` (빌드 2~5분 뒤)

비공개로 올리려면 `--private`. 나중에 Space Settings에서 공개로 바꿀 수 있다.

**빌드가 끝나면 배포본에 대고 E2E를 그대로 돌려 확인한다:**

```bash
PYTHONIOENCODING=utf-8 python scripts/run_web_demo_e2e.py   --base-url https://<아이디>-dart-detective.hf.space
```

#### git push로 하고 싶다면 (대안)

```bash
PYTHONIOENCODING=utf-8 python scripts/prepare_hf_space.py --check
cd dist/hf-space
git init && git add -A && git commit -m "deploy: 공시 탐정사무소 웹 데모"
git remote add origin https://huggingface.co/spaces/<아이디>/dart-detective
git push -u origin main      # username = HF 아이디, password = Write 토큰
```

Space를 먼저 웹에서 만들어야 하고(SDK: **Docker**), 토큰을 비밀번호 자리에 넣어야 한다.
`push_hf_space.py` 쪽이 이 두 단계를 없애준다.

#### 자주 걸리는 것

| 증상 | 원인 / 조치 |
|---|---|
| `402 Payment Required` | **Docker Space는 PRO 구독 필요.** 무료로 가려면 Koyeb/Render/터널 |
| `401 Unauthorized` | 토큰이 Read 권한. **Write**로 다시 발급 |
| 로그인했는데 `no token found` | WSL에서 `hf auth login`하고 Windows에서 실행하면 토큰 경로가 다르다. `HF_HOME=//wsl.localhost/<distro>/home/<user>/.cache/huggingface` 로 지정하거나 같은 쪽에서 로그인 |
| Space가 `Configuration error` | README.md YAML 헤더 문제. `prepare_hf_space.py`가 써 주므로 그 파일을 지우거나 덮어쓰지 말 것 |
| 빌드는 됐는데 화면이 안 뜸 | Space가 `app_port: 7860`을 읽는다. Dockerfile의 `EXPOSE`/`PORT`와 맞아야 한다(기본값 그대로면 맞다) |
| 한참 뒤 접속하니 느림 | 무료 `cpu-basic`은 유휴 시 잠든다. 첫 접속에서 깨어나는 데 수십 초 |
| 진행이 초기화됨 | 세션이 서버 메모리에 있다. Space가 재시작/기상하면 리셋된다(상단 `↺ 처음부터`) |

### 2-3. (선택) LLM 켜기

기본값은 LLM 없이 도는 결정론적 모드다. 켜려면 Space Settings → **Variables and secrets**:

| 종류 | 이름 | 값 |
|---|---|---|
| Secret | `ANTHROPIC_API_KEY` | `sk-ant-...` |
| Variable | `DART_DETECTIVE_LLM` | `on` |

**공개 URL에 키를 붙이면 아무나 내 계정으로 호출한다.** 심사용 상시 공개라면 끄고 두고,
시연할 때만 켜는 편을 권한다. 켤 거면 Space를 Private으로 두거나 발표 후 값을 지운다.

## 2-6. 행사 당일 운영 — 링크만 배포할 때

### "15분 이상 틀어두면 안 되나?" — 반대다

15분은 **켤 수 있는 시간이 아니라 아무도 안 들어올 때 자는 시간**이다.

- 사람들이 계속 들어오면 **절대 안 잔다.** 오래 켜두는 게 문제가 아니다.
- 무료 한도는 750 인스턴스 시간/월인데 한 달이 약 730시간이다. 즉 **24시간 내내 켜둬도
  한 달치가 안 넘는다.** 다만 매달 24시간 유지하면 한도에 딱 붙으니, 행사 기간에만
  깨워두는 편이 안전하다.
- 진짜 위험은 **한산할 때 잠들었다가 심사위원이 첫 번째로 누르는 것** — 약 1분 로딩.

### 노트북을 남에게 맡기는 상황이라면: 터널 쓰지 마라

| | Render 링크 | Cloudflare Tunnel |
|---|---|---|
| 노트북이 절전/종료되면 | **무관, 계속 살아있음** | 링크 즉시 죽음 |
| 네트워크(와이파이) 바뀌면 | 무관 | 끊길 수 있음 |
| 맡은 분이 살릴 수 있나 | 살릴 일이 없음 | 터미널을 다시 띄워야 함 |
| 콜드스타트 | 잠들었으면 1분 | 없음 |

**남이 링크를 배포하는 구조면 Render만 쓴다.** 맡은 분은 아무것도 안 해도 된다.
터널은 내가 내 노트북 앞에서 직접 시연할 때만 의미가 있다.

### 잠들지 않게 하는 법 — **내가 오늘 한 번 설정한다. 맡은 분은 아무것도 안 한다**

깨우는 일은 노트북과 무관한 곳에서 돌아야 한다. 맡은 분에게 터미널 명령을 시키는 건
가장 나쁜 선택이다(저장소 clone + 파이썬 설치 + 노트북 상시 켜두기가 전부 필요해진다).

**A. GitHub Actions — 가입 불필요, 이미 있는 저장소에서 돈다 (권장)**

`.github/workflows/keep-warm.yml`이 저장소에 들어 있다. push하면 자동 활성화되고,
GitHub 서버가 10분마다 `/health`를 호출한다. 내 노트북은 꺼도 된다.

- 즉시 한 번 돌려보기: 저장소 **Actions** 탭 → *Keep demo warm* → **Run workflow**
- 행사 끝나면: 같은 화면 우측 `...` → **Disable workflow**
- 한계: GitHub 예약 실행은 서버가 붐비면 몇 분 밀릴 수 있다(정시 보장 아님)

**B. cron-job.org — 가입 필요하지만 정시성이 더 정확하다**

1. https://cron-job.org (무료, 카드 불필요)
2. URL `https://dart-detective.onrender.com/health`, 주기 **10분**
3. 행사 끝나면 job 비활성화

**C. 아무것도 안 하기** — 행사 직전에 브라우저로 한 번 열어 깨우면, 그 뒤로 관람객이
계속 들어오는 한 안 잔다. 관람이 뜸한 시간대에만 첫 접속자가 1분을 기다린다.

**D. `scripts/keep_warm.py`** — 내가 내 컴퓨터를 켜둘 수 있을 때만. 그 컴퓨터가 꺼지면
같이 멈춘다. **남에게 맡길 노트북에서 돌리면 안 된다.**

```bash
PYTHONIOENCODING=utf-8 python scripts/keep_warm.py   --url https://dart-detective.onrender.com --interval 600 --hours 8
```

### 동시 접속은 견디나 — 배포본 실측

배포된 주소에 12명이 동시에 붙어 각자 사건을 처음부터 끝까지 완주시켰다.

```
동시 플레이어 12명 · 전원 완주까지 5.5s
성공 12/12 · 요청 108건
응답시간  중앙값 514ms · p95 943ms · 최대 1098ms
active_sessions=12/100
```

세션 간 상태 격리와 Point-in-Time 차단도 동시 부하 상태에서 그대로 유지됐다.

세션이 늘어도 메모리가 늘지 않도록 **Retriever를 사건별로 공유**한다(읽기 전용).
로컬 실측으로 25세션 생성+플레이가 1.2초, RSS 85.6MB — 세션 수와 사실상 무관하다.
그래서 세션 상한을 100으로 뒀다(중간에 밀려나는 사람이 없도록).

### 맡기기 전 체크리스트

**내가 오늘 할 것**

- [ ] `.github/workflows/keep-warm.yml`을 push하고 Actions 탭에서 **Run workflow**로 한 번 확인
- [ ] 링크를 브라우저로 열어 한 판 끝까지 해본다(Reality Replay까지)
- [ ] LLM은 꺼진 상태 그대로 둔다(공개 URL이라 의도적)

**맡은 분께 전달할 것 — 이게 전부다**

```
https://dart-detective.onrender.com

이 링크만 보내주시면 됩니다.
설치할 것도, 실행할 것도 없습니다. 노트북은 꺼두셔도 됩니다.
화면이 이상하면 오른쪽 위 "↺ 처음부터"를 누르면 됩니다.
```

**행사 후**

- [ ] Actions 탭에서 *Keep demo warm* **Disable**(무료 750시간/월 아끼기)

## 3. Docker 직접 (Render / Fly.io / Cloud Run / 사내 서버)

```bash
docker build -t dart-detective .
docker run -p 7860:7860 dart-detective
# http://localhost:7860
```

- 포트는 `PORT` 환경변수를 읽는다(기본 7860). Render/Cloud Run은 자동 주입된다.
- **워커는 반드시 1개.** `--workers 2` 이상이면 세션이 워커마다 따로 생겨 게임이 중간에 끊긴다
  (세션이 프로세스 메모리의 `InMemorySaver`에 있다). Dockerfile의 CMD에 `--workers 1`이 박혀 있다.
- 헬스체크는 `GET /health`.

## 4. 발표 당일용 — 터널 (배포 없이 링크 공유)

가장 빠르고 안전한 방법. 내 노트북에서 서버를 띄우고 임시 공개 URL만 뚫는다.

```bash
# 터미널 1
PYTHONIOENCODING=utf-8 DART_DETECTIVE_LLM=off \
  uvicorn dart_detective.api:app --port 8000

# 터미널 2 (둘 중 하나)
cloudflared tunnel --url http://localhost:8000     # 설치: winget install Cloudflare.cloudflared
ngrok http 8000
```

출력된 `https://...trycloudflare.com` 링크를 공유하면 된다. 노트북을 끄면 링크도 죽는다.
심사위원이 나중에 다시 볼 링크가 필요하면 HF Spaces를, 발표 중 라이브 시연만 필요하면
터널을 쓰면 된다. **둘 다 해두는 게 가장 안전하다.**

## 5. 공개 배포 시 주의 — 실제로 손본 것

| 문제 | 조치 |
|---|---|
| 세션이 무한히 쌓임(`InMemorySaver` + retriever가 세션마다) | `GameServer(max_sessions=50, session_ttl_sec=1800)` — 유휴 세션부터 버리고, 상한 초과 시 오래된 순으로 회수. `end()`에서 checkpoint(`delete_thread`)까지 함께 정리 |
| 멀티 워커에서 세션 유실 | Dockerfile CMD에 `--workers 1` 고정 + 문서화 |
| LLM 키 남용 | 기본 `DART_DETECTIVE_LLM=off`. 켜지 않으면 API 호출 자체가 없다 |
| 이미지 비대 | `.dockerignore` + 필요한 파일만 COPY → 배포 디렉터리 0.3MB |
| 운영 상태 파악 | `GET /health`에 `active_sessions / max_sessions / session_ttl_sec / cases` 노출 |

환경변수로 조절할 수 있다.

| 변수 | 기본값 | 설명 |
|---|---|---|
| `DART_DETECTIVE_LLM` | (미설정=on) | `off`면 LLM을 아예 호출하지 않는다 |
| `DART_DETECTIVE_MAX_SESSIONS` | `50` | 동시 세션 상한 |
| `DART_DETECTIVE_SESSION_TTL` | `1800` | 유휴 세션 만료(초) |
| `PORT` | `7860` | 리슨 포트 |

### 아직 안 한 것 (공개 규모가 커지면 필요)

- **레이트 리밋 없음.** LLM을 켠 채로 공개하면 `research` 호출을 무제한으로 맞을 수 있다.
  켤 거라면 리버스 프록시(Cloudflare)나 미들웨어로 IP당 제한을 걸어야 한다.
- **인증 없음.** 링크를 아는 사람은 누구나 플레이한다. 비공개가 필요하면 HF Space를
  Private으로 두거나 Cloudflare Access를 건다.
- **세션 영속성 없음.** 서버가 재시작하면 진행이 사라진다(상단 `↺ 처음부터`로 복구).
  필요하면 `build_graph(checkpointer=SqliteSaver(...))`로 교체.

### 데이터 관련

Case Pack에는 DART 전자공시 **원문 발췌**가 들어 있다. 공개 배포 시 출처(금융감독원 DART)를
화면이나 README에 밝히는 편이 안전하다. 현재 Space README에 "실제 DART 전자공시로 만들었다"고
적어 두었다.

## 6. 확인한 것 / 확인하지 못한 것

### `docker build`는 이 개발 환경에서 돌릴 수 없다

컨테이너 런타임이 아예 없다. 전부 확인했다.

| 확인 대상 | 결과 |
|---|---|
| Windows PATH의 `docker` / `podman` | 없음 |
| Docker Desktop 설치 경로 · 서비스 | 없음 |
| WSL(Ubuntu-22.04) 안의 `docker` / `podman` | 없음 |
| WSL에서 apt로 설치 | `sudo`가 비밀번호를 요구 → 비대화식으로 불가 |

그래서 **빌드 대신 빌드가 깨지는 지점을 정적으로 검증**했다.

```bash
PYTHONIOENCODING=utf-8 python scripts/check_dockerfile.py
```

검사 항목:

1. COPY 원본이 빌드 컨텍스트에 실제로 존재하는가
2. 그 원본이 `.dockerignore`에 걸려 컨텍스트에서 빠지지는 않는가 — **가장 흔한 함정**
3. 다중 소스 COPY의 목적지가 `/`로 끝나는가(안 끝나면 docker가 거부한다)
4. `RUN`이 실행하는 스크립트가 그 시점까지 COPY되어 있는가
5. pip 의존성이 대상 플랫폼(linux/py3.12) 휠로 해석되는가

현재 결과: **통과**(COPY 원본 7건, `.dockerignore` 규칙 25개, pip 휠 47개 해석).
검증기 자체는 결함을 심은 Dockerfile로 테스트한다(`tests/test_check_dockerfile.py`) —
제외된 COPY·없는 원본·잘못된 목적지·순서 뒤바뀐 RUN·CMD 누락을 모두 잡는다.

> pip 해석 시 `uvloop`은 목록에 안 잡힌다. 휠이 없어서가 아니라 `sys_platform != 'win32'`
> 마커가 현재(Windows) 인터프리터 기준으로 평가되기 때문이다. 실제 리눅스 빌드에서는
> 정상적으로 설치된다.

### 그 외에 실제로 돌려본 것

- Dockerfile이 COPY하는 파일 집합만 모은 트리에서 → 검색 인덱스 빌드 → 앱 임포트 →
  uvicorn 기동 → **브라우저 E2E 완주**(14화면, 사건 선택부터 Reality Replay·Reset까지).
  즉 이미지에 들어갈 파일 목록에 빠진 게 없다.
- `_source_docs.jsonl`(50MB 캐시) 없이 인덱스가 빌드된다 — 미래 문서 chunk가 202→102로
  줄지만 Point-in-Time 필터가 어차피 걸러내므로 플레이에는 영향이 없다.
- 세션 상한/TTL 회수(상한 2로 두고 3개 시작 → 2개 유지).
- `prepare_hf_space.py --check`로 배포 디렉터리 조립 후 인덱스 빌드 + 임포트 스모크.

### 아직 못 한 것

- **이미지 레이어 실행은 검증하지 못했다.** 정적 검증은 "COPY/RUN 선언이 말이 되는가"까지다.
  베이스 이미지 pull, `pip install`의 실제 실행, 컨테이너 안에서의 파일 권한은 확인 대상 밖이다.
- HF Spaces에 실제 push는 하지 않았다(계정/토큰 필요).

### Docker가 있는 환경에서 확인하는 법

Docker Desktop을 설치했거나 다른 리눅스 머신이 있다면 아래 3줄이면 끝난다.
마지막 줄은 **컨테이너에 대고 브라우저 E2E를 그대로 돌린다** — 통과하면 진짜로 배포 가능하다는 뜻이다.

```bash
docker build -t dart-detective .
docker run -d -p 7860:7860 --name dart-demo dart-detective

PYTHONIOENCODING=utf-8 python scripts/run_web_demo_e2e.py --base-url http://127.0.0.1:7860
# -> "E2E 통과: 사건 선택 → ... → CASE COMPLETE → Reset"

docker logs dart-demo        # 문제가 있으면 여기부터
docker rm -f dart-demo
```

HF Spaces에 push하면 같은 빌드를 서버에서 수행하고, 실패 시 Space 페이지의 빌드 로그에
그대로 찍힌다. 로컬 Docker가 없다면 그게 사실상 다음 검증 지점이다.
