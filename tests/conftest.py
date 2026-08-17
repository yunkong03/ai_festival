import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
# scripts/ 는 Case Pack 빌더/렌더러를 테스트에서 직접 import하기 위해 추가한다.
sys.path.insert(0, str(REPO / "scripts"))

from dart_corpus.config import default_corpus_root  # noqa: E402


@pytest.fixture(scope="session")
def corpus_root():
    root = default_corpus_root()
    assert root.exists(), f"corpus root not found: {root}"
    return root
