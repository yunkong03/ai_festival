#!/usr/bin/env python3
"""Hugging Face Space(Docker SDK)로 밀어 넣을 배포 디렉터리를 만든다.

이 저장소에는 데모에 필요 없는 대용량 산출물(DocumentIR 8.6GB, 원본 코퍼스)이 섞여 있다.
그래서 저장소를 통째로 push하지 않고, **Dockerfile이 COPY하는 것과 정확히 같은 파일 집합**만
`dist/hf-space/`에 모아 별도 git 저장소로 push한다.

사용법:
    PYTHONIOENCODING=utf-8 python scripts/prepare_hf_space.py
    PYTHONIOENCODING=utf-8 python scripts/prepare_hf_space.py --out dist/hf-space --title "공시 탐정사무소"

만들어진 뒤:
    cd dist/hf-space
    git init && git add -A && git commit -m "deploy: 공시 탐정사무소 웹 데모"
    git remote add origin https://huggingface.co/spaces/<user>/<space>
    git push -u origin main            # HF 토큰으로 로그인
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO / "dist" / "hf-space"

# Dockerfile의 COPY 목록과 1:1로 맞춘다. 여기가 어긋나면 이미지 빌드가 깨진다.
COPY_TREES = [
    ("src/dart_detective", "src/dart_detective"),
]
COPY_FILES = [
    ("Dockerfile", "Dockerfile"),
    ("scripts/build_case_search_index.py", "scripts/build_case_search_index.py"),
    ("scripts/case_pack_render.py", "scripts/case_pack_render.py"),
]
CASE_PACK_GLOBS = ["CASE-*.json", "index.json"]

SPACE_README = """---
title: {title}
emoji: 🔍
colorFrom: yellow
colorTo: green
sdk: docker
app_port: 7860
pinned: false
short_description: 실제 DART 공시로 하는 금융 추리 게임 데모
---

# 🔍 {title}

실제 DART 전자공시로 만든 금융 탐정게임 데모입니다.

과거 특정 시점으로 이동해 **그때까지 공개된 공시만** 조사하고, 단서와 금융용어를 모아
판단을 내립니다. 판단을 확정하면 그 뒤 실제로 무슨 일이 있었는지(Reality Replay)가 열립니다.

## 플레이 방법

1. 사건을 고르고 `조사 시작`
2. 책상 위 서류를 열어 **노란 형광펜 문장**을 클릭 → 단서 수집
3. 단서를 모으면 금융수첩에 용어가 열립니다
4. 막히면 🕵️ 조수에게 힌트를 요청하세요 (답은 알려주지 않습니다)
5. `판단하기` → 선택 후 **WHAT ACTUALLY HAPPENED?**

## 규칙

- 모든 사건·숫자·문장은 실제 공시에서 나옵니다. 가상의 수치를 만들지 않습니다.
- 조사 시점 이후의 문서는 검색 계층에서 차단됩니다(Point-in-Time Retrieval).
- 정답·오답을 채점하지 않습니다. 무엇을 보고 판단했는지만 정리해 줍니다.

## 참고

- 세션은 서버 메모리에 있습니다. Space가 잠자기에서 깨어나면 진행이 초기화됩니다
  (상단 `↺ 처음부터`로 언제든 리셋할 수 있습니다).
- 기본값은 LLM 없이 도는 결정론적 모드입니다. 힌트와 자유질문도 그대로 동작합니다.
"""


def copy_tree(src: Path, dst: Path) -> int:
    if not src.exists():
        raise SystemExit(f"없는 경로: {src}")
    shutil.copytree(
        src, dst,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
    )
    return sum(1 for _ in dst.rglob("*") if _.is_file())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--title", default="공시 탐정사무소")
    ap.add_argument("--check", action="store_true",
                    help="복사 후 인덱스 빌드 + 임포트 스모크까지 실행")
    args = ap.parse_args()

    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    n_files = 0
    for src_rel, dst_rel in COPY_TREES:
        n_files += copy_tree(REPO / src_rel, out / dst_rel)
    for src_rel, dst_rel in COPY_FILES:
        target = out / dst_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / src_rel, target)
        n_files += 1

    packs_src = REPO / "data" / "artifacts" / "case_packs"
    packs_dst = out / "data" / "artifacts" / "case_packs"
    packs_dst.mkdir(parents=True, exist_ok=True)
    n_packs = 0
    for pattern in CASE_PACK_GLOBS:
        for p in sorted(packs_src.glob(pattern)):
            shutil.copy2(p, packs_dst / p.name)
            n_files += 1
            n_packs += 1
    if n_packs == 0:
        raise SystemExit(
            f"Case Pack이 없다: {packs_src}\n"
            "먼저 `python scripts/build_case_packs.py`를 실행하라."
        )

    (out / "README.md").write_text(SPACE_README.format(title=args.title), encoding="utf-8")
    (out / ".gitattributes").write_text("*.json text eol=lf\n", encoding="utf-8")
    n_files += 2

    total_mb = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) / 1e6
    print(f"[ok] {n_files} files ({total_mb:.1f}MB) -> {out}")
    print(f"     Case Pack {n_packs}건 포함")

    if args.check:
        print("[check] 인덱스 빌드 + 임포트 스모크")
        env_path = str(out / "src")
        for cmd in (
            [sys.executable, "scripts/build_case_search_index.py"],
            [sys.executable, "-c", "from dart_detective.api import app; print('import ok')"],
        ):
            r = subprocess.run(cmd, cwd=str(out), capture_output=True, text=True,
                               encoding="utf-8", errors="replace",
                               env={"PYTHONPATH": env_path, "PYTHONIOENCODING": "utf-8",
                                    "PATH": __import__("os").environ.get("PATH", ""),
                                    "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")})
            if r.returncode != 0:
                print(r.stdout[-2000:], r.stderr[-2000:])
                raise SystemExit("[check] 실패 — Dockerfile COPY 목록을 확인하라")
            print("  ", (r.stdout.strip().splitlines() or ["ok"])[-1])
        # 스모크로 만든 인덱스는 지운다(이미지 빌드 때 다시 만든다)
        (packs_dst / "search_index.jsonl").unlink(missing_ok=True)

    print("\n다음 단계:")
    print(f"  cd {out}")
    print("  git init && git add -A && git commit -m 'deploy: 공시 탐정사무소 웹 데모'")
    print("  git remote add origin https://huggingface.co/spaces/<user>/<space>")
    print("  git push -u origin main")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
