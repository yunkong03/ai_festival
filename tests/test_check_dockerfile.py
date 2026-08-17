"""Dockerfile 정적 검증기 자체를 검증한다.

이 검증기가 `docker build`를 대신하는 자리에 있으므로, "통과했다"는 말이 의미를 가지려면
심어둔 결함을 실제로 잡아야 한다.
"""
from __future__ import annotations

from pathlib import Path

from check_dockerfile import DockerIgnore, check

REPO = Path(__file__).resolve().parent.parent


def _write(base: Path, rel: str, content: str = "x") -> None:
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_real_dockerfile_passes_static_check():
    problems = check(REPO / "Dockerfile", REPO, skip_pip=True)
    assert problems == [], problems


def test_detects_planted_defects(tmp_path):
    _write(tmp_path, "keep/a.txt")
    _write(tmp_path, "skipme/b.txt")
    _write(tmp_path, "one.txt")
    _write(tmp_path, "two.txt")
    _write(tmp_path, ".dockerignore", "skipme/\n")
    _write(tmp_path, "Dockerfile", "\n".join([
        "FROM python:3.12-slim",
        "WORKDIR /app",
        "COPY keep/ /app/keep/",
        "COPY skipme/ /app/skipme/",          # .dockerignore로 제외됨
        "COPY nosuchfile.txt /app/",          # 존재하지 않음
        "COPY one.txt two.txt /app/dest",     # 다중 소스인데 목적지가 '/'로 안 끝남
        "RUN python scripts/notcopied.py",    # COPY 전에 실행
    ]))

    problems = check(tmp_path / "Dockerfile", tmp_path, skip_pip=True)
    joined = "\n".join(problems)
    assert "dockerignore로 제외" in joined
    assert "COPY 원본이 없다" in joined
    assert "'/'로 끝나지 않는다" in joined
    assert "COPY되지 않았다" in joined
    assert "CMD/ENTRYPOINT가 없다" in joined


def test_dockerignore_negation_rescues_path():
    ig = DockerIgnore("data/\n!data/keep.json\n")
    assert ig.excluded("data/other.json")
    assert ig.excluded("data/keep.json") is None


def test_dockerignore_matches_parent_directory():
    ig = DockerIgnore("build/\n")
    assert ig.excluded("build/sub/file.txt")
    assert ig.excluded("src/file.txt") is None
