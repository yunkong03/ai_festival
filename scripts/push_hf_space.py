#!/usr/bin/env python3
"""Hugging Face Space(Docker)로 웹 데모를 올린다.

`prepare_hf_space.py`로 배포 디렉터리를 조립하고 → Space를 만들고(있으면 재사용) →
파일을 업로드한다. git remote/자격증명 설정 없이 한 번에 끝난다.

사전 준비(한 번만):
    1. https://huggingface.co 가입
    2. https://huggingface.co/settings/tokens 에서 **Write** 토큰 발급
    3. hf auth login          # 토큰 붙여넣기

사용법:
    PYTHONIOENCODING=utf-8 python scripts/push_hf_space.py --repo-id <아이디>/dart-detective
    PYTHONIOENCODING=utf-8 python scripts/push_hf_space.py --repo-id dart-detective --private
    # --repo-id에 '/'가 없으면 로그인한 계정 이름을 앞에 붙인다
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO / "dist" / "hf-space"

LOGIN_HINT = """
로그인이 필요하다:
  1) https://huggingface.co/settings/tokens 에서 **Write** 권한 토큰 발급
  2) hf auth login          (토큰 붙여넣기)
  또는 --token hf_xxx 로 직접 전달
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-id", required=True,
                    help="예: myname/dart-detective (사용자명 생략 가능)")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--token", default=None, help="생략하면 `hf auth login` 결과를 쓴다")
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--title", default="공시 탐정사무소")
    ap.add_argument("--skip-prepare", action="store_true",
                    help="배포 디렉터리를 다시 만들지 않고 기존 것을 그대로 올린다")
    args = ap.parse_args()

    try:
        from huggingface_hub import HfApi
        from huggingface_hub.errors import HfHubHTTPError
    except ImportError:
        raise SystemExit("huggingface_hub이 없다:  pip install \"huggingface_hub[cli]\"")

    api = HfApi(token=args.token)

    # 1) 로그인 확인 — 여기서 막히면 나머지는 의미가 없다
    try:
        me = api.whoami()
    except Exception as exc:  # noqa: BLE001
        print(f"[auth] 인증 실패: {exc}")
        raise SystemExit(LOGIN_HINT)
    username = me.get("name") or me.get("email") or "?"
    print(f"[auth] 로그인됨: {username}")

    repo_id = args.repo_id if "/" in args.repo_id else f"{username}/{args.repo_id}"

    # 2) 배포 디렉터리 조립(Dockerfile이 COPY하는 파일 집합과 동일)
    out = Path(args.out)
    if not args.skip_prepare:
        print("[prepare] 배포 디렉터리 조립 + 스모크 검사")
        r = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "prepare_hf_space.py"),
             "--out", str(out), "--title", args.title, "--check"],
            cwd=str(REPO), text=True, encoding="utf-8", errors="replace",
        )
        if r.returncode != 0:
            raise SystemExit("[prepare] 실패 — 위 출력을 확인하라")
    if not (out / "Dockerfile").exists():
        raise SystemExit(f"{out}에 Dockerfile이 없다. --skip-prepare를 빼고 다시 실행하라.")

    n_files = sum(1 for p in out.rglob("*") if p.is_file() and ".git" not in p.parts)
    size_mb = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) / 1e6

    # 3) Space 생성(이미 있으면 재사용)
    print(f"[space] 생성/확인: {repo_id} (sdk=docker, "
          f"{'private' if args.private else 'public'})")
    try:
        api.create_repo(repo_id=repo_id, repo_type="space", space_sdk="docker",
                        private=args.private, exist_ok=True)
    except HfHubHTTPError as exc:
        raise SystemExit(f"[space] 생성 실패: {exc}")

    # 4) 업로드
    print(f"[upload] {n_files} files ({size_mb:.1f}MB) -> {repo_id}")
    api.upload_folder(
        repo_id=repo_id,
        repo_type="space",
        folder_path=str(out),
        commit_message="deploy: 공시 탐정사무소 웹 데모",
        ignore_patterns=["**/__pycache__/**", "*.pyc", ".git/**",
                         "**/search_index.jsonl"],
    )

    space_url = f"https://huggingface.co/spaces/{repo_id}"
    app_url = f"https://{repo_id.replace('/', '-').lower()}.hf.space"
    print("\n[done] 업로드 완료")
    print(f"  빌드 로그 : {space_url}   (Logs 탭에서 진행 상황 확인)")
    print(f"  게임 주소 : {app_url}     (빌드 2~5분 뒤 열림)")
    print("\n빌드가 끝나면 확인:")
    print(f"  PYTHONIOENCODING=utf-8 python scripts/run_web_demo_e2e.py --base-url {app_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
