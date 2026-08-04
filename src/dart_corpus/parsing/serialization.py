"""DocumentIR JSON/JSONL 직렬화 — Parser의 유일한 산출물을 디스크에 결정론적으로
저장/복원한다. dataclasses.asdict를 쓰지 않는 이유: NodeKind/WarningCode가 Enum이라
asdict만으로는 JSON에 그대로 못 넣고(Enum 객체가 남음), DocumentNodeIR이 Union
(SectionIR|TableIR|ParagraphIR)이라 복원 시 "kind" 판별자로 실제 타입을 골라야 한다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from dart_corpus.parsing.document_ir import (
    DocumentIR, NodeKind, ParagraphIR, ParseQuality, ParserWarning, SectionIR,
    SourceFileIR, SourceLocation, TableCellIR, TableIR, WarningCode,
)


def _source_location_to_dict(loc: SourceLocation | None) -> dict | None:
    if loc is None:
        return None
    return {"rel_path": loc.rel_path, "order_index": loc.order_index, "byte_offset": loc.byte_offset}


def _source_location_from_dict(d: dict | None) -> SourceLocation | None:
    if d is None:
        return None
    return SourceLocation(rel_path=d["rel_path"], order_index=d["order_index"], byte_offset=d.get("byte_offset"))


def _source_file_to_dict(sf: SourceFileIR) -> dict:
    return {
        "rel_path": sf.rel_path, "is_attachment": sf.is_attachment, "content_format": sf.content_format,
        "schema_version": sf.schema_version, "content_sha256": sf.content_sha256,
        "declared_encoding": sf.declared_encoding, "actual_encoding_used": sf.actual_encoding_used,
    }


def _source_file_from_dict(d: dict) -> SourceFileIR:
    return SourceFileIR(**d)


def _table_cell_to_dict(c: TableCellIR) -> dict:
    return {"row": c.row, "col": c.col, "text": c.text, "rowspan": c.rowspan, "colspan": c.colspan, "tag": c.tag}


def _table_cell_from_dict(d: dict) -> TableCellIR:
    return TableCellIR(**d)


def _node_to_dict(node) -> dict:
    if isinstance(node, SectionIR):
        return {
            "kind": node.kind.value, "node_id": node.node_id, "title_text": node.title_text,
            "source": _source_location_to_dict(node.source), "section_id": node.section_id,
            "parent_section_id": node.parent_section_id, "level": node.level,
            "level_confident": node.level_confident, "section_hierarchy": list(node.section_hierarchy),
            "start_order_index": node.start_order_index, "end_order_index": node.end_order_index,
        }
    if isinstance(node, TableIR):
        return {
            "kind": node.kind.value, "node_id": node.node_id, "section_hierarchy": list(node.section_hierarchy),
            "source": _source_location_to_dict(node.source),
            "raw_cells": [_table_cell_to_dict(c) for c in node.raw_cells],
            "raw_rows": [[_table_cell_to_dict(c) for c in row] for row in node.raw_rows],
            "normalized_rows": [list(row) for row in node.normalized_rows],
            "header_row_indices": list(node.header_row_indices),
            "n_declared_cols": node.n_declared_cols, "actual_col_counts": list(node.actual_col_counts),
            "normalized_title_guess": node.normalized_title_guess, "title_confirmed": node.title_confirmed,
            "unit_text": node.unit_text, "period_text": node.period_text,
            "consolidation_basis": node.consolidation_basis,
            "consolidation_basis_reason": node.consolidation_basis_reason,
        }
    if isinstance(node, ParagraphIR):
        return {
            "kind": node.kind.value, "node_id": node.node_id, "section_hierarchy": list(node.section_hierarchy),
            "text": node.text, "source": _source_location_to_dict(node.source),
            "is_footnote_like": node.is_footnote_like,
        }
    raise TypeError(f"unknown DocumentIR node type: {type(node)!r}")


def _node_from_dict(d: dict):
    kind = d["kind"]
    if kind == NodeKind.SECTION.value:
        return SectionIR(
            node_id=d["node_id"], kind=NodeKind.SECTION, title_text=d["title_text"],
            source=_source_location_from_dict(d["source"]), section_id=d["section_id"],
            parent_section_id=d["parent_section_id"], level=d["level"],
            level_confident=d["level_confident"], section_hierarchy=list(d["section_hierarchy"]),
            start_order_index=d["start_order_index"], end_order_index=d["end_order_index"],
        )
    if kind == NodeKind.TABLE.value:
        return TableIR(
            node_id=d["node_id"], kind=NodeKind.TABLE, section_hierarchy=list(d["section_hierarchy"]),
            source=_source_location_from_dict(d["source"]),
            raw_cells=[_table_cell_from_dict(c) for c in d["raw_cells"]],
            raw_rows=[[_table_cell_from_dict(c) for c in row] for row in d["raw_rows"]],
            normalized_rows=[list(row) for row in d["normalized_rows"]],
            header_row_indices=list(d["header_row_indices"]),
            n_declared_cols=d["n_declared_cols"], actual_col_counts=list(d["actual_col_counts"]),
            normalized_title_guess=d["normalized_title_guess"], title_confirmed=d["title_confirmed"],
            unit_text=d["unit_text"], period_text=d["period_text"],
            consolidation_basis=d.get("consolidation_basis"),
            consolidation_basis_reason=d.get("consolidation_basis_reason"),
        )
    if kind == NodeKind.PARAGRAPH.value:
        return ParagraphIR(
            node_id=d["node_id"], kind=NodeKind.PARAGRAPH, section_hierarchy=list(d["section_hierarchy"]),
            text=d["text"], source=_source_location_from_dict(d["source"]),
            is_footnote_like=d["is_footnote_like"],
        )
    raise ValueError(f"unknown DocumentIR node kind: {kind!r}")


def _warning_to_dict(w: ParserWarning) -> dict:
    return {"doc_id": w.doc_id, "rel_path": w.rel_path, "code": w.code.value, "severity": w.severity, "message": w.message}


def _warning_from_dict(d: dict) -> ParserWarning:
    return ParserWarning(doc_id=d["doc_id"], rel_path=d["rel_path"], code=WarningCode(d["code"]),
                          severity=d["severity"], message=d["message"])


def _quality_to_dict(q: ParseQuality) -> dict:
    return {
        "tier": q.tier, "schema_version": q.schema_version,
        "n_sanitized_entities": q.n_sanitized_entities,
        "n_unresolved_section_depth": q.n_unresolved_section_depth,
        "n_tables_with_merged_cells": q.n_tables_with_merged_cells,
        "router_matched_expected_parser": q.router_matched_expected_parser,
    }


def _quality_from_dict(d: dict) -> ParseQuality:
    return ParseQuality(**d)


def document_ir_to_dict(ir: DocumentIR) -> dict:
    """필드 순서가 항상 동일해서(고정 literal dict) 같은 DocumentIR은 항상 같은
    JSON 문자열로 직렬화된다(determinism — set/dict 순회 의존 없음)."""
    return {
        "doc_id": ir.doc_id,
        "schema_version": ir.schema_version,
        "parser_version": ir.parser_version,
        "corpus_snapshot_id": ir.corpus_snapshot_id,
        "source_files": [_source_file_to_dict(sf) for sf in ir.source_files],
        "nodes": [_node_to_dict(n) for n in ir.nodes],
        "warnings": [_warning_to_dict(w) for w in ir.warnings],
        "parse_quality": _quality_to_dict(ir.parse_quality) if ir.parse_quality is not None else None,
    }


def document_ir_from_dict(d: dict) -> DocumentIR:
    return DocumentIR(
        doc_id=d["doc_id"],
        source_files=[_source_file_from_dict(sf) for sf in d["source_files"]],
        nodes=[_node_from_dict(n) for n in d["nodes"]],
        warnings=[_warning_from_dict(w) for w in d["warnings"]],
        parse_quality=_quality_from_dict(d["parse_quality"]) if d.get("parse_quality") is not None else None,
        schema_version=d["schema_version"],
        parser_version=d["parser_version"],
        corpus_snapshot_id=d.get("corpus_snapshot_id"),
    )


def document_ir_to_json_line(ir: DocumentIR) -> str:
    return json.dumps(document_ir_to_dict(ir), ensure_ascii=False)


def save_document_irs_jsonl(irs: Iterable[DocumentIR], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for ir in irs:
            f.write(document_ir_to_json_line(ir))
            f.write("\n")


def load_document_irs_jsonl(path: Path) -> list[DocumentIR]:
    irs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            irs.append(document_ir_from_dict(json.loads(line)))
    return irs
