"""Parse Audit — 문서별 파싱 품질 감사 레코드. DocumentIR 자체(구조 데이터)와 분리해서
"이 문서를 어떻게 파싱했는지"만 요약한다(전체 corpus 실행 후 structured/partial/
fallback 분포·warning code 분포를 사람이 훑어보기 위한 용도).

raw_text_len/node_text_len 계산은 scripts/run_parser_pilot.py의 text 보존율 로직과
동일한 정의(공백 정규화 후 문자 수 비교)를 쓴다 — scripts/는 패키지가 아니라 import
대상이 아니므로 여기 다시 둔다(로직 자체는 15줄 내외로 작아 중복 비용이 낮음).
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from dart_corpus.contract.manifest import DocumentRecord
from dart_corpus.contract.paths import resolve_corpus_path
from dart_corpus.parsing.document_ir import DocumentIR, ParagraphIR, SectionIR, TableIR, WarningCode

_STRIP_TAGS_RE = re.compile(r"<[^>]+>")


def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _raw_text_len_for_doc(doc: DocumentRecord, corpus_root: Path) -> int:
    doc_dir = resolve_corpus_path(corpus_root, doc.file_path)
    total = 0
    if doc.file_format == "pdf+html":
        viewer_path = doc_dir / f"{doc.rcept_no}_viewer.html"
        raw = viewer_path.read_bytes().decode("utf-8", errors="replace")
        total += len(_normalize_ws(_STRIP_TAGS_RE.sub("", raw)))
    else:
        for p in doc_dir.iterdir():
            if p.suffix.lower() == ".xml":
                raw = p.read_bytes().decode("utf-8", errors="replace")
                total += len(_normalize_ws(_STRIP_TAGS_RE.sub("", raw)))
    return total


def _node_text_len(nodes: list) -> int:
    total = 0
    for n in nodes:
        if isinstance(n, ParagraphIR):
            total += len(_normalize_ws(n.text))
        elif isinstance(n, SectionIR):
            total += len(_normalize_ws(n.title_text))
        elif isinstance(n, TableIR):
            total += sum(len(_normalize_ws(c.text)) for c in n.raw_cells)
    return total


@dataclass
class SourceFileAudit:
    rel_path: str
    content_format: str
    declared_encoding: str | None
    detected_encoding: str
    is_attachment: bool


@dataclass
class ParseAuditRecord:
    doc_id: str
    doc_group: str
    source_files: list[SourceFileAudit] = field(default_factory=list)
    parse_quality_tier: str = ""
    schema_version: str | None = None
    used_sanitizer: bool = False
    used_encoding_recovery: bool = False
    used_fallback_parser: bool = False
    warning_codes: list[str] = field(default_factory=list)
    n_nodes: int = 0
    n_sections: int = 0
    n_tables: int = 0
    n_paragraphs: int = 0
    text_preservation_ratio: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "ParseAuditRecord":
        d = dict(d)
        d["source_files"] = [SourceFileAudit(**sf) for sf in d["source_files"]]
        return ParseAuditRecord(**d)


def build_parse_audit(doc: DocumentRecord, ir: DocumentIR, corpus_root: Path) -> ParseAuditRecord:
    source_files = [
        SourceFileAudit(
            rel_path=sf.rel_path, content_format=sf.content_format, declared_encoding=sf.declared_encoding,
            detected_encoding=sf.actual_encoding_used, is_attachment=sf.is_attachment,
        )
        for sf in ir.source_files
    ]
    warning_codes = sorted({w.code.value for w in ir.warnings})
    used_sanitizer = any(w.code == WarningCode.SANITIZED_ENTITY for w in ir.warnings)
    used_encoding_recovery = any(sf.actual_encoding_used.endswith("(replace)") for sf in ir.source_files)
    used_fallback_parser = (
        (ir.parse_quality is not None and ir.parse_quality.tier == "fallback")
        or any(w.code in (WarningCode.PARSE_FAILED, WarningCode.ROUTER_FALLBACK_PARSER) for w in ir.warnings)
    )

    raw_len = _raw_text_len_for_doc(doc, corpus_root)
    text_preservation_ratio = (_node_text_len(ir.nodes) / raw_len) if raw_len else None

    return ParseAuditRecord(
        doc_id=doc.doc_id,
        doc_group=doc.doc_group,
        source_files=source_files,
        parse_quality_tier=ir.parse_quality.tier if ir.parse_quality else "",
        schema_version=ir.parse_quality.schema_version if ir.parse_quality else None,
        used_sanitizer=used_sanitizer,
        used_encoding_recovery=used_encoding_recovery,
        used_fallback_parser=used_fallback_parser,
        warning_codes=warning_codes,
        n_nodes=len(ir.nodes),
        n_sections=sum(1 for n in ir.nodes if isinstance(n, SectionIR)),
        n_tables=sum(1 for n in ir.nodes if isinstance(n, TableIR)),
        n_paragraphs=sum(1 for n in ir.nodes if isinstance(n, ParagraphIR)),
        text_preservation_ratio=text_preservation_ratio,
    )


def save_parse_audits_jsonl(audits: list[ParseAuditRecord], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for audit in audits:
            f.write(json.dumps(audit.to_dict(), ensure_ascii=False))
            f.write("\n")


def load_parse_audits_jsonl(path: Path) -> list[ParseAuditRecord]:
    audits = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            audits.append(ParseAuditRecord.from_dict(json.loads(line)))
    return audits
