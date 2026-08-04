from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def default_corpus_root() -> Path:
    """Root of the DART corpus (contains manifest.jsonl, universe.csv, raw/).

    Overridable via DART_CORPUS_ROOT for CI or alternate checkouts.
    """
    env = os.environ.get("DART_CORPUS_ROOT")
    if env:
        return Path(env)
    return _PROJECT_ROOT / "data" / "3.공시" / "corpus"
