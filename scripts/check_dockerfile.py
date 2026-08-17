#!/usr/bin/env python3
"""Dockerfile 정적 검증 — 컨테이너 런타임 없이 빌드 실패 요인을 미리 잡는다.

`docker build`를 대신하지는 못한다. 다만 실제로 자주 깨지는 지점을 확인한다:

  1) COPY 원본이 빌드 컨텍스트에 실제로 존재하는가
  2) 그 원본이 .dockerignore에 걸려 **컨텍스트에서 제외**되지는 않는가 (가장 흔한 함정)
  3) 다중 소스 COPY의 목적지가 '/'로 끝나는가 (안 끝나면 docker가 거부한다)
  4) RUN에서 실행하는 스크립트가 그 시점까지 COPY되어 있는가
  5) pip 의존성이 대상 플랫폼(linux/py3.12) 휠로 해석되는가

사용법:
    PYTHONIOENCODING=utf-8 python scripts/check_dockerfile.py
    PYTHONIOENCODING=utf-8 python scripts/check_dockerfile.py --skip-pip
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- .dockerignore
class DockerIgnore:
    """docker의 .dockerignore 매칭(단순화판) — 마지막에 매치된 규칙이 이긴다."""

    def __init__(self, text: str):
        self.rules: list[tuple[str, bool]] = []   # (pattern, is_negation)
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            neg = line.startswith("!")
            if neg:
                line = line[1:].strip()
            self.rules.append((line.rstrip("/"), neg))

    def excluded(self, rel_path: str) -> str | None:
        """제외되면 매치된 패턴을, 아니면 None을 반환."""
        p = PurePosixPath(rel_path)
        # 자기 자신과 모든 상위 디렉터리에 대해 규칙을 적용한다
        candidates = [str(p)] + [str(parent) for parent in p.parents if str(parent) != "."]
        hit: str | None = None
        for pattern, neg in self.rules:
            matched = any(
                fnmatch.fnmatch(c, pattern) or fnmatch.fnmatch(c, pattern + "/*")
                or c == pattern
                for c in candidates
            )
            if not matched and "**" in pattern:
                simple = pattern.replace("**/", "*")
                matched = any(fnmatch.fnmatch(c, simple) for c in candidates)
            if matched:
                hit = None if neg else pattern
        return hit


# ---------------------------------------------------------------- Dockerfile 파싱
def parse_instructions(text: str) -> list[tuple[int, str, str]]:
    """(줄번호, 명령어, 인자) 목록. 백슬래시 줄바꿈을 이어붙인다."""
    out: list[tuple[int, str, str]] = []
    buf, start = "", 0
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        stripped = line.strip()
        if not buf and (not stripped or stripped.startswith("#")):
            continue
        if not buf:
            start = i
        if stripped.endswith("\\"):
            buf += stripped[:-1].strip() + " "
            continue
        buf += stripped
        parts = buf.split(None, 1)
        if parts:
            out.append((start, parts[0].upper(), parts[1] if len(parts) > 1 else ""))
        buf = ""
    return out


def check(dockerfile: Path, context: Path, skip_pip: bool) -> list[str]:
    problems: list[str] = []
    text = dockerfile.read_text(encoding="utf-8")
    instructions = parse_instructions(text)

    di_path = context / ".dockerignore"
    ignore = DockerIgnore(di_path.read_text(encoding="utf-8") if di_path.exists() else "")
    print(f"[ctx] {context}")
    print(f"[ignore] {'.dockerignore 규칙 ' + str(len(ignore.rules)) + '개' if di_path.exists() else '없음'}")

    if not any(cmd == "FROM" for _, cmd, _ in instructions):
        problems.append("FROM 명령이 없다")

    copied: list[str] = []          # 컨테이너 안에 들어간 경로(RUN 검증용)
    n_copy_src = 0

    for lineno, cmd, args in instructions:
        if cmd not in {"COPY", "ADD"}:
            continue
        tokens = [t for t in args.split() if not t.startswith("--")]
        if len(tokens) < 2:
            problems.append(f"L{lineno}: {cmd} 인자가 부족하다: {args!r}")
            continue
        *sources, dest = tokens

        if len(sources) > 1 and not dest.endswith("/"):
            problems.append(
                f"L{lineno}: 소스가 {len(sources)}개인데 목적지 {dest!r}가 '/'로 끝나지 않는다 "
                f"(docker가 거부한다)")

        for src in sources:
            n_copy_src += 1
            src_path = context / src
            if not src_path.exists():
                problems.append(f"L{lineno}: COPY 원본이 없다 → {src}")
                continue
            hit = ignore.excluded(src.rstrip("/"))
            if hit:
                problems.append(
                    f"L{lineno}: COPY 원본이 .dockerignore로 제외됐다 → {src} (패턴 {hit!r})")
            if src_path.is_dir():
                inside = [p for p in src_path.rglob("*") if p.is_file()]
                kept = [p for p in inside
                        if not ignore.excluded(p.relative_to(context).as_posix())]
                if not kept:
                    problems.append(f"L{lineno}: {src} 안의 파일이 전부 제외됐다")
                copied.append(dest.rstrip("/") + "/")
            else:
                copied.append(dest if not dest.endswith("/") else dest + src_path.name)

    print(f"[copy] 원본 {n_copy_src}건 검사")

    # RUN이 실행하는 로컬 스크립트가 그 전에 COPY됐는지
    workdir = "/"
    for lineno, cmd, args in instructions:
        if cmd == "WORKDIR":
            workdir = args.strip()
        if cmd != "RUN":
            continue
        for m in re.finditer(r"python\s+([\w./-]+\.py)", args):
            script = m.group(1)
            abs_script = script if script.startswith("/") else f"{workdir.rstrip('/')}/{script}"
            if not any(abs_script == c or (c.endswith("/") and abs_script.startswith(c))
                       for c in copied):
                problems.append(
                    f"L{lineno}: RUN이 {script}를 실행하는데 그 시점까지 COPY되지 않았다")

    # CMD/ENTRYPOINT 존재 여부
    if not any(cmd in {"CMD", "ENTRYPOINT"} for _, cmd, _ in instructions):
        problems.append("CMD/ENTRYPOINT가 없다")

    # pip 의존성 해석
    if not skip_pip:
        pkgs: list[str] = []
        for _, cmd, args in instructions:
            if cmd == "RUN" and "pip install" in args:
                pkgs += re.findall(r'"([^"]+)"', args)
        if pkgs:
            print(f"[pip] {len(pkgs)}개 패키지를 linux/py3.12 휠로 해석 시도")
            with tempfile.TemporaryDirectory() as td:
                r = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--dry-run", "--ignore-installed",
                     "--only-binary=:all:", "--python-version", "3.12",
                     "--platform", "manylinux2014_x86_64", "--target", td, *pkgs],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                )
            if r.returncode != 0:
                problems.append("pip 의존성 해석 실패:\n" + r.stdout[-1500:] + r.stderr[-1500:])
            else:
                line = next((l for l in r.stdout.splitlines() if l.startswith("Would install")), "")
                print(f"[pip] OK — {len(line.split()) - 2}개 휠 해석됨")

    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dockerfile", default=str(REPO / "Dockerfile"))
    ap.add_argument("--context", default=str(REPO))
    ap.add_argument("--skip-pip", action="store_true")
    args = ap.parse_args()

    problems = check(Path(args.dockerfile), Path(args.context), args.skip_pip)

    print()
    if problems:
        print(f"[FAIL] 문제 {len(problems)}건")
        for p in problems:
            print("  -", p)
        return 1
    print("[OK] 정적 검증 통과 — COPY 경로 · .dockerignore · 다중소스 목적지 · "
          "RUN 선행조건 · pip 해석")
    print("     주의: 이건 `docker build`가 아니다. 이미지 레이어 실행은 검증하지 않는다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
