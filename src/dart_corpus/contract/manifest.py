from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

EXPECTED_DOCUMENT_COUNT = 4204

# report_nm에서 [기재정정] 태그 제거 후 괄호 안 내용을 유형명으로 파생시킨다.
# major의 doc_subtype이 598건 전부 빈 문자열([확인], corpus_coverage_strategy.md §0.1)이라
# Metadata Filter가 유형별로 거르려면 이 파생값이 필수다(interface_contract_draft.md §1).
_CORRECTION_TAG_RE = re.compile(r"^\[기재정정\]|\[첨부추가\]")
_PAREN_SUFFIX_RE = re.compile(r"\(([^()]+)\)\s*$")


def derive_subtype(report_nm: str, doc_subtype: str) -> str:
    """[확인] major의 doc_subtype은 전부 공백 — report_nm에서 파생한다.
    다른 doc_group은 이미 doc_subtype이 있으면 그걸 그대로 쓴다."""
    if doc_subtype:
        return doc_subtype
    cleaned = _CORRECTION_TAG_RE.sub("", report_nm).strip()
    m = _PAREN_SUFFIX_RE.search(cleaned)
    if m:
        return m.group(1)
    return cleaned or doc_subtype


@dataclass(frozen=True)
class DocumentRecord:
    doc_id: str
    corp_code: str
    corp_name: str
    listed_name: str
    stock_code: str
    industry: str
    sector: str
    doc_group: str
    doc_subtype: str          # 주의: major는 전 건 "" (빈 문자열) — [확인]
    derived_subtype: str       # 파생값(interface_contract_draft.md §1 신규 필드)
    report_nm: str
    rcept_no: str
    rcept_dt: str
    flr_nm: str
    is_correction: bool
    file_path: str
    file_format: str
    n_files: int
    base_year: int | None = None
    base_month: int | None = None


class ManifestLoader:
    SUPPORTED_FORMATS = {"xml"}

    def __init__(self, corpus_root: Path):
        self.corpus_root = Path(corpus_root)

    def load(self) -> list[DocumentRecord]:
        manifest_path = self.corpus_root / "manifest.jsonl"
        records: list[DocumentRecord] = []
        with open(manifest_path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                raw = json.loads(line)
                doc_subtype = raw.get("doc_subtype") or ""
                record = DocumentRecord(
                    doc_id=raw["doc_id"],
                    corp_code=str(raw["corp_code"]),
                    corp_name=raw["corp_name"],
                    listed_name=raw["listed_name"],
                    stock_code=str(raw["stock_code"]),
                    industry=raw["industry"],
                    sector=raw["sector"],
                    doc_group=raw["doc_group"],
                    doc_subtype=doc_subtype,
                    derived_subtype=derive_subtype(raw.get("report_nm", ""), doc_subtype),
                    report_nm=raw.get("report_nm", ""),
                    rcept_no=raw["rcept_no"],
                    rcept_dt=raw["rcept_dt"],
                    flr_nm=raw.get("flr_nm", ""),
                    is_correction=bool(raw["is_correction"]),
                    file_path=raw["file_path"],
                    file_format=raw["file_format"],
                    n_files=int(raw["n_files"]),
                    base_year=raw.get("base_year"),
                    base_month=raw.get("base_month"),
                )
                if record.file_format not in self.SUPPORTED_FORMATS:
                    logger.warning(
                        "unsupported file_format=%s doc_id=%s (manifest line %d) "
                        "— flagged as unsupported, XML parser will not process it",
                        record.file_format, record.doc_id, lineno,
                    )
                records.append(record)
        if len(records) != EXPECTED_DOCUMENT_COUNT:
            logger.warning(
                "manifest.jsonl document count=%d, expected %d",
                len(records), EXPECTED_DOCUMENT_COUNT,
            )
        return records

    def unsupported(self, records: list[DocumentRecord]) -> list[DocumentRecord]:
        return [r for r in records if r.file_format not in self.SUPPORTED_FORMATS]
