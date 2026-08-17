#!/usr/bin/env python3
"""웹 데모 E2E 실행 + 스크린샷 캡처.

첫 화면(사건 선택)부터 Reality Replay / CASE COMPLETE까지 실제 브라우저로 전부 눌러보고,
각 화면을 docs/screenshots/에 PNG로 저장한다. 화면마다 assert가 걸려 있어서 UI가 깨지면
스크린샷이 아니라 테스트가 먼저 실패한다.

전제:
    pip install playwright && python -m playwright install chromium

사용법:
    PYTHONIOENCODING=utf-8 python scripts/run_web_demo_e2e.py
    PYTHONIOENCODING=utf-8 python scripts/run_web_demo_e2e.py --base-url http://127.0.0.1:8000
    PYTHONIOENCODING=utf-8 python scripts/run_web_demo_e2e.py --headed --slow-mo 300
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SHOTS = REPO / "docs" / "screenshots"
DEFAULT_PORT = 8765


def server_alive(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(base_url + "/health", timeout=1.5) as r:
            return json.loads(r.read().decode())["status"] == "ok"
    except Exception:
        return False


def spawn_server(port: int) -> subprocess.Popen:
    env = {**os.environ, "PYTHONPATH": str(REPO / "src"), "PYTHONIOENCODING": "utf-8",
           "DART_DETECTIVE_LLM": os.environ.get("DART_DETECTIVE_LLM", "off")}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "dart_detective.api:app",
         "--port", str(port), "--log-level", "warning"],
        cwd=str(REPO), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(60):
        if server_alive(base):
            return proc
        time.sleep(0.5)
    proc.terminate()
    raise SystemExit("uvicorn 기동 실패")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=None,
                    help="이미 떠 있는 서버 주소. 생략하면 --port로 새로 띄운다")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--out", default=str(SHOTS))
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--slow-mo", type=int, default=0)
    ap.add_argument("--case", default="CASE-001")
    args = ap.parse_args()

    from playwright.sync_api import expect, sync_playwright

    # --base-url을 명시하지 않았으면 --port를 기준으로 삼는다. 그래야 테스트가 다른
    # 포트를 지정했을 때 남아 있는 다른 서버에 붙지 않는다.
    base_url = args.base_url or f"http://127.0.0.1:{args.port}"
    proc = None
    if not server_alive(base_url):
        print(f"[server] 기동 중… {base_url}")
        proc = spawn_server(args.port)
        base_url = f"http://127.0.0.1:{args.port}"
    print(f"[server] ready: {base_url}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    shots: list[str] = []
    step = 0

    def shot(page, name: str, full: bool = False) -> None:
        nonlocal step
        step += 1
        path = out / f"{step:02d}-{name}.png"
        page.screenshot(path=str(path), full_page=full)
        shots.append(path.name)
        print(f"  [shot] {path.name}")

    try:
      with sync_playwright() as p:
          browser = p.chromium.launch(headless=not args.headed, slow_mo=args.slow_mo)
          # device_scale_factor=1 — 저장소에 커밋할 파일이라 용량을 억제한다(2x면 4배).
          page = browser.new_page(viewport={"width": 1280, "height": 900},
                                  device_scale_factor=1)
          errors: list[str] = []
          fault = {"injecting": False}   # 의도적으로 요청을 죽이는 구간 표시

          def note_error(text: str) -> None:
              if not fault["injecting"]:
                  errors.append(text)

          page.on("pageerror", lambda e: note_error(str(e)))
          page.on("console", lambda m: note_error(m.text) if m.type == "error" else None)

          # ---------------------------------------------------- 1. 사건 선택
          print("[1] 사건 파일 보관함")
          page.goto(base_url + "/app/", wait_until="networkidle")
          page.wait_for_selector(".case-card")
          assert page.locator(".case-card").count() >= 1, "사건 카드가 없다"
          shot(page, "case-select")

          # ---------------------------------------------------- 2. 사건 파일
          print("[2] 사건 파일")
          page.locator(".case-card").first.click()
          page.wait_for_selector("#screen-casefile.active")
          assert page.locator("#cfMission").inner_text().strip(), "MISSION이 비었다"
          assert page.locator("#cfDate").inner_text().strip(), "시점 표시가 없다"
          shot(page, "case-file")

          # ---------------------------------------------------- 3. 조사실
          print("[3] 조사실")
          page.click("#btnStart")
          page.wait_for_selector("#screen-desk.active .doc-card")
          n_docs = page.locator(".doc-card").count()
          assert n_docs >= 4, f"문서 카드가 {n_docs}개뿐"
          shot(page, "desk")

          # ---------------------------------------------------- 4. 공시 읽기 + 단서 수집
          print("[4] 공시 읽기 · 단서 수집")
          page.locator(".doc-card").first.click()
          page.wait_for_selector("#screen-doc.active mark.clue")
          n_clues = page.locator("mark.clue").count()
          assert n_clues >= 1, "형광펜 단서가 없다"
          shot(page, "document-read")

          before = int(page.locator("#btnBoard").get_attribute("data-count"))
          page.locator("mark.clue").first.click()
          page.wait_for_selector("mark.clue.collected")
          page.wait_for_timeout(700)  # 수첩으로 날아가는 애니메이션
          shot(page, "clue-collected")
          after = int(page.locator("#btnBoard").get_attribute("data-count"))
          assert after > before, "단서 수집이 상태에 반영되지 않았다"

          # 남은 형광펜도 모두 수집(단서판/판단 화면을 채우기 위해)
          for i in range(1, min(n_clues, 4)):
              marks = page.locator("mark.clue:not(.collected)")
              if marks.count() == 0:
                  break
              marks.first.click()
              page.wait_for_timeout(350)

          # ---------------------------------------------------- 5. 금융수첩
          print("[5] 금융수첩")
          page.click("#btnNotebook")
          page.wait_for_selector("#drawerNotebook.open")
          assert page.locator(".term-row").count() >= 3, "용어 목록이 비었다"
          unlocked = page.locator(".term-row.found")
          assert unlocked.count() >= 1, "단서를 모았는데 열린 용어가 없다"
          unlocked.first.click()
          page.wait_for_selector(".term-detail")
          assert "이번 사건에서는" in page.locator(".term-detail").inner_text()
          page.wait_for_timeout(450)   # 드로어 슬라이드 인 종료 후 캡처
          shot(page, "notebook")

          # ---------------------------------------------------- 6. 사건 단서판
          print("[6] 사건 단서판")
          page.click("#btnBoard")
          page.wait_for_selector("#drawerBoard.open")
          assert page.locator(".sticky-note").count() >= 1, "단서판이 비었다"
          page.wait_for_timeout(450)
          shot(page, "clue-board")

          # ---------------------------------------------------- 7. AI 탐정 조수
          print("[7] AI 탐정 조수")
          page.click("#btnAssistant")
          page.wait_for_selector("#drawerAssistant.open")
          page.click("#qHint")
          page.wait_for_function(
              "() => document.querySelectorAll('#chat .msg.bot').length >= 2 && "
              "!document.querySelector('#chat .msg.bot:last-child').textContent.includes('생각 중')",
              timeout=20000)
          hint_text = page.locator("#chat .msg.bot").last.inner_text()
          assert "힌트 Level" in hint_text, f"힌트가 안 나옴: {hint_text[:80]}"

          page.click("#qNumber")
          page.wait_for_timeout(300)
          page.fill("#askInput", "이 회사가 이 투자를 감당할 수 있어?")
          page.click("#askForm button[type=submit]")
          page.wait_for_selector("#chat .msg.bot .badge", timeout=30000)
          badge = page.locator("#chat .msg.bot .badge").last.inner_text()
          assert badge in {"SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED"}, badge
          assert page.locator("#chat .msg.bot .cites").count() >= 1, "근거 공시 표시가 없다"
          page.wait_for_timeout(450)
          shot(page, "assistant")

          # ---------------------------------------------------- 7b. Agent 장애 격리
          print("[7b] Evidence Agent 장애 격리 확인")

          def kill_research(route):
              body = route.request.post_data or ""
              if '"action":"research"' in body.replace(" ", ""):
                  route.abort()          # 자유 질문만 죽인다
              else:
                  route.continue_()

          fault["injecting"] = True
          page.route("**/actions", kill_research)
          page.fill("#askInput", "이 질문은 실패해야 한다")
          page.click("#askForm button[type=submit]")
          page.wait_for_selector("#chat .msg.bot.warn", timeout=15000)
          warn = page.locator("#chat .msg.bot.warn").last.inner_text()
          assert "조사실로 돌아가서" in warn, f"장애 안내 문구가 없다: {warn[:80]}"
          page.unroute("**/actions", kill_research)
          fault["injecting"] = False

          # 메인 루프는 계속 진행 가능해야 한다 — 단서 수집이 여전히 동작하는지 확인
          board_count = page.locator("#btnBoard").get_attribute("data-count")
          page.click("#backdrop")
          page.wait_for_timeout(300)
          assert page.locator("#btnBoard").get_attribute("data-count") == board_count
          shot(page, "assistant-failure-isolated")

          # ---------------------------------------------------- 8. Replay 잠금 확인
          print("[8] Reality Replay 잠금 확인 (판단 전)")
          page.click("#btnBackDesk")          # 공시 읽기 → 조사실(허브)
          page.wait_for_selector("#screen-desk.active")
          assert page.locator(".doc-card.opened").count() >= 1, "열어본 문서 표시가 없다"
          page.click("#btnGoDecision")
          page.wait_for_selector("#screen-decision.active .option-card")
          assert page.locator("#decResult").is_hidden(), "판단 전인데 결과가 보인다"
          shot(page, "decision-options")

          # ---------------------------------------------------- 9. 판단
          print("[9] 판단")
          page.locator(".option-card").nth(1).click()
          page.wait_for_selector("#decResult:not([hidden]) .cov-row")
          result_text = page.locator("#decResult").inner_text()
          # 정답/오답 표현을 쓰지 않는다 — 조사 커버리지 언어만 쓴다
          for banned in ("정답", "오답", "틀렸", "맞았", "성공", "실패"):
              assert banned not in result_text, f"판단 결과에 '{banned}' 표현 사용됨"
          assert any(v in result_text for v in ("충분히 조사", "일부 조사", "조사 부족"))
          assert page.locator(".cov-row").count() >= 5, "조사 관점 요약이 5개 미만"
          shot(page, "decision-result", full=True)

          # ---------------------------------------------------- 10. Reality Replay
          print("[10] Reality Replay")
          page.click("#btnGoReplay")
          page.wait_for_selector("#screen-replay.active #replayOpen:not([hidden])")
          page.wait_for_timeout(2600)  # 타임라인 순차 등장
          n_items = page.locator(".tl-item").count()
          assert n_items >= 2, "타임라인이 비었다"
          assert page.locator(".tl-item.mine").count() == 1, "내 선택 항목이 없다"
          tl_text = page.locator("#timeline").inner_text()
          shot(page, "reality-replay", full=True)

          # ---------------------------------------------------- 11. CASE COMPLETE
          print("[11] CASE COMPLETE")
          page.click("#btnGoComplete")
          page.wait_for_selector("#screen-complete.active .stamp-clear")
          page.wait_for_timeout(900)   # 도장 애니메이션이 끝난 뒤 캡처
          assert "CASE COMPLETE" in page.locator(".stamp-clear").inner_text()
          assert page.locator("#cpTerms .chip").count() >= 3, "발견 용어 요약이 비었다"
          shot(page, "case-complete")

          # ---------------------------------------------------- 12. Reset
          print("[12] Reset")
          page.click("#btnReset")
          page.wait_for_selector("#screen-casefile.active")
          assert page.locator("#btnBoard").get_attribute("data-count") == "0", "Reset 후 단서가 남았다"
          shot(page, "reset")

          assert not errors, f"브라우저 콘솔 에러: {errors[:3]}"
          browser.close()

    finally:
        if proc:
            proc.terminate()   # 실패해도 띄운 서버를 남기지 않는다

    try:
        where = out.relative_to(REPO)
    except ValueError:
        where = out            # --out이 저장소 밖(pytest tmp_path 등)
    print(f"\n[done] 스크린샷 {len(shots)}장 -> {where}")
    for s in shots:
        print("  -", s)
    print("\nE2E 통과: 사건 선택 → 사건 파일 → 조사실 → 공시 읽기 → 단서 수집 → "
          "금융수첩 → 단서판 → AI 조수 → 판단 → Reality Replay → CASE COMPLETE → Reset")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
