from __future__ import annotations

import logging
import unicodedata
from pathlib import Path

logger = logging.getLogger(__name__)


class PathResolutionError(FileNotFoundError):
    """A manifest-declared relative path could not be found on disk."""


def resolve_corpus_path(root: Path, relative_posix_path: str) -> Path:
    """Resolve a manifest `file_path` (always POSIX-separated, NFC Korean
    text) against the corpus root.

    Company-name directories under raw/<doc_group>/ are NFD-normalized on
    this WSL mount while manifest.jsonl stores NFC — a plain Path join
    silently fails to find them ([확인], 이번 세션 내내 재현됨). This walks
    the path one segment at a time: if the direct join exists, use it (fast
    path, also correct for ASCII segments); otherwise scan the parent
    directory and match by NFC-normalized name.
    """
    current = Path(root)
    for segment in relative_posix_path.split("/"):
        if not segment:
            continue
        candidate = current / segment
        if candidate.exists():
            current = candidate
            continue
        target_nfc = unicodedata.normalize("NFC", segment)
        match = None
        for child in current.iterdir():
            if unicodedata.normalize("NFC", child.name) == target_nfc:
                match = child
                break
        if match is None:
            raise PathResolutionError(
                f"cannot resolve segment {segment!r} under {current} "
                f"(from relative path {relative_posix_path!r})"
            )
        logger.debug("resolved NFD segment %r -> %s", segment, match)
        current = match
    return current


def list_xml_files(doc_dir: Path) -> list[Path]:
    return sorted(p for p in doc_dir.iterdir() if p.suffix.lower() == ".xml")
