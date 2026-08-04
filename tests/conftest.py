import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dart_corpus.config import default_corpus_root  # noqa: E402


@pytest.fixture(scope="session")
def corpus_root():
    root = default_corpus_root()
    assert root.exists(), f"corpus root not found: {root}"
    return root
