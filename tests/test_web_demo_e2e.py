"""웹 데모 브라우저 E2E — 실제 Chromium으로 첫 화면부터 Reality Replay까지 눌러본다.

느리고(브라우저 기동) 외부 바이너리가 필요해서 integration 마크를 단다.

    pip install playwright && python -m playwright install chromium
    pytest -m integration tests/test_web_demo_e2e.py

스크린샷까지 갱신하려면 스크립트를 직접 실행한다:
    PYTHONIOENCODING=utf-8 python scripts/run_web_demo_e2e.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

playwright = pytest.importorskip("playwright.sync_api",
                                 reason="playwright 미설치 — pip install playwright")


@pytest.mark.integration
def test_full_web_demo_playthrough(tmp_path):
    """사건 선택 → 조사 → 단서 수집 → 판단 → Reality Replay → CASE COMPLETE → Reset."""
    result = subprocess.run(
        [sys.executable, "scripts/run_web_demo_e2e.py",
         "--port", "8791", "--out", str(tmp_path)],
        cwd=str(REPO), capture_output=True, text=True, timeout=600,
        encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]
    assert "E2E 통과" in result.stdout
    assert len(list(tmp_path.glob("*.png"))) >= 12
