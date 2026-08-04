import json

from dart_corpus.contract.manifest import DocumentRecord
from dart_corpus.parsing.canonical_parser import parse_document
from dart_corpus.parsing.document_ir import (
    DocumentIR, NodeKind, ParagraphIR, ParseQuality, ParserWarning, SectionIR,
    SourceFileIR, SourceLocation, TableCellIR, TableIR, WarningCode,
)
from dart_corpus.parsing.serialization import (
    document_ir_from_dict, document_ir_to_dict, document_ir_to_json_line,
    load_document_irs_jsonl, save_document_irs_jsonl,
)


def _sample_ir() -> DocumentIR:
    section = SectionIR(
        node_id="d::f.xml::n0", title_text="I. 회사의 개요", source=SourceLocation("f.xml", 0),
        section_id="d::f.xml::n0", parent_section_id="ROOT", level=1, level_confident=True,
        section_hierarchy=[], start_order_index=0, end_order_index=2,
    )
    table = TableIR(
        node_id="d::f.xml::n1", section_hierarchy=["I. 회사의 개요"], source=SourceLocation("f.xml", 1),
        raw_cells=[TableCellIR(row=0, col=0, text="a", rowspan=1, colspan=1, tag="TD")],
        raw_rows=[[TableCellIR(row=0, col=0, text="a", rowspan=1, colspan=1, tag="TD")]],
        normalized_rows=[["a"]], header_row_indices=[], n_declared_cols=1, actual_col_counts=[1],
        normalized_title_guess=None, title_confirmed=False, unit_text=None, period_text=None,
        consolidation_basis="연결", consolidation_basis_reason="matched '연결' in section_hierarchy title='I. 회사의 개요'",
    )
    paragraph = ParagraphIR(
        node_id="d::f.xml::n2", section_hierarchy=["I. 회사의 개요"], text="본문",
        source=SourceLocation("f.xml", 2), is_footnote_like=False,
    )
    warning = ParserWarning("d", "f.xml", WarningCode.TABLE_METADATA_UNCERTAIN, "info", "uncertain")
    source_file = SourceFileIR(
        rel_path="f.xml", is_attachment=False, content_format="dart_xml", schema_version="dart4.xsd",
        content_sha256="0" * 64, declared_encoding=None, actual_encoding_used="utf-8",
    )
    quality = ParseQuality(tier="structured", schema_version="dart4.xsd")
    return DocumentIR(
        doc_id="d", source_files=[source_file], nodes=[section, table, paragraph],
        warnings=[warning], parse_quality=quality,
    )


def test_document_ir_to_dict_is_json_serializable():
    ir = _sample_ir()
    d = document_ir_to_dict(ir)
    json.dumps(d, ensure_ascii=False)  # 예외 없이 직렬화되어야 함


def test_document_ir_to_dict_uses_enum_values_not_enum_objects():
    ir = _sample_ir()
    d = document_ir_to_dict(ir)
    assert d["nodes"][0]["kind"] == "section"
    assert d["nodes"][1]["kind"] == "table"
    assert d["nodes"][2]["kind"] == "paragraph"
    assert d["warnings"][0]["code"] == "table_metadata_uncertain"


def test_document_ir_round_trip_preserves_all_fields():
    ir = _sample_ir()
    restored = document_ir_from_dict(document_ir_to_dict(ir))
    assert restored == ir


def test_document_ir_round_trip_through_json_line():
    ir = _sample_ir()
    line = document_ir_to_json_line(ir)
    assert "\n" not in line
    restored = document_ir_from_dict(json.loads(line))
    assert restored == ir


def test_document_ir_to_dict_is_deterministic_across_calls():
    ir = _sample_ir()
    assert document_ir_to_json_line(ir) == document_ir_to_json_line(ir)


def test_document_ir_carries_schema_version_parser_version_and_snapshot_id():
    ir = _sample_ir()
    ir.corpus_snapshot_id = "snap_deadbeefcafebabe"
    d = document_ir_to_dict(ir)
    assert d["schema_version"] == ir.schema_version
    assert d["parser_version"] == ir.parser_version
    assert d["corpus_snapshot_id"] == "snap_deadbeefcafebabe"
    restored = document_ir_from_dict(d)
    assert restored.corpus_snapshot_id == "snap_deadbeefcafebabe"
    assert restored.schema_version == ir.schema_version
    assert restored.parser_version == ir.parser_version


def test_save_and_load_document_irs_jsonl_round_trips(tmp_path):
    irs = [_sample_ir(), _sample_ir()]
    irs[1].doc_id = "d2"
    path = tmp_path / "out.jsonl"
    save_document_irs_jsonl(irs, path)
    loaded = load_document_irs_jsonl(path)
    assert loaded == irs


def test_real_parsed_document_round_trips(corpus_root):
    doc = DocumentRecord(
        doc_id="periodic_20231114001884", corp_code="00000000", corp_name="HD현대일렉트릭",
        listed_name="테스트", stock_code="000000", industry="IT", sector="테스트섹터",
        doc_group="periodic", doc_subtype="quarter", derived_subtype="quarter",
        report_nm="테스트보고서", rcept_no="20231114001884", rcept_dt="20231114",
        flr_nm="테스트", is_correction=False,
        file_path="raw/periodic/HD현대일렉트릭/20231114001884_quarter_2023_09",
        file_format="xml", n_files=1,
    )
    ir = parse_document(doc, corpus_root)
    restored = document_ir_from_dict(document_ir_to_dict(ir))
    assert restored == ir
