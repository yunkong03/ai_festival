#!/usr/bin/env python3
"""배포된 데모가 잠들지 않게 주기적으로 깨워둔다.

Render 무료 플랜은 **15분간 인바운드 트래픽이 없으면 절전**하고, 다음 접속에서
기상까지 약 1분이 걸린다. 심사·시연 기간에는 그 1분이 치명적이라 미리 깨워둔다.

주의:
  - 이 스크립트는 실행 중인 컴퓨터가 켜져 있어야 한다. 노트북을 남에게 맡기거나
    닫아둘 상황이면 **외부 무료 모니터링(cron-job.org, UptimeRobot 등)으로
    /health를 10분마다 호출**하게 두는 편이 확실하다. docs/deploy.md 참고.
  - 24시간 내내 깨워두면 무료 플랜의 750시간/월을 거의 다 쓴다(한 달 ≈ 730시간).
    행사 기간에만 켜라.

사용법:
    PYTHONIOENCODING=utf-8 python scripts/keep_warm.py --url https://dart-detective.onrender.com
    PYTHONIOENCODING=utf-8 python scripts/keep_warm.py --url ... --interval 600 --hours 8
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime


def ping(url: str, timeout: int) -> tuple[bool, str, float]:
    t0 = time.time()
    try:
        with urllib.request.urlopen(url + "/health", timeout=timeout) as r:
            body = json.loads(r.read().decode())
        dt = time.time() - t0
        return True, f"ok · 세션 {body.get('active_sessions')}/{body.get('max_sessions')}", dt
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}", time.time() - t0
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {str(e)[:60]}", time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="예: https://dart-detective.onrender.com")
    ap.add_argument("--interval", type=int, default=600,
                    help="핑 간격(초). 기본 600 = 10분 (절전 기준 15분보다 짧게)")
    ap.add_argument("--hours", type=float, default=0,
                    help="몇 시간 동안 유지할지. 0이면 Ctrl+C까지 계속")
    ap.add_argument("--timeout", type=int, default=90,
                    help="자고 있으면 기상에 1분쯤 걸리므로 넉넉히")
    args = ap.parse_args()

    url = args.url.rstrip("/")
    deadline = time.time() + args.hours * 3600 if args.hours else None
    print(f"[keep-warm] {url} · {args.interval}s 간격"
          f"{f' · {args.hours}시간 동안' if args.hours else ' · Ctrl+C로 종료'}")

    n_ok = n_fail = 0
    try:
        while deadline is None or time.time() < deadline:
            ok, msg, dt = ping(url, args.timeout)
            n_ok, n_fail = n_ok + ok, n_fail + (not ok)
            stamp = datetime.now().strftime("%H:%M:%S")
            mark = "✔" if ok else "✘"
            slow = "  (기상 중이었던 듯)" if ok and dt > 5 else ""
            print(f"  {stamp} {mark} {msg} · {dt:.1f}s{slow}", flush=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[keep-warm] 중단")
    print(f"[keep-warm] 성공 {n_ok} / 실패 {n_fail}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
