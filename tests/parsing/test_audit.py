import json

from dart_corpus.contract.manifest import DocumentRecord
from dart_corpus.parsing.audit import build_parse_audit, load_parse_audits_jsonl, save_parse_audits_jsonl
from dart_corpus.parsing.canonical_parser import parse_document
from dart_corpus.parsing.document_ir import (
    DocumentIR, ParagraphIR, ParseQuality, ParserWarning, SourceFileIR, SourceLocation, WarningCode,
)
from dart_corpus.parsing.sniff import CONTENT_DART_XML


def _doc(**overrides) -> DocumentRecord:
    base = dict(
        doc_id="periodic_00000000000000", corp_code="00000000", corp_name="테스트기업",
        listed_name="테스트", stock_code="000000", industry="IT", sector="테스트섹터",
        doc_group="periodic", doc_subtype="annual", derived_subtype="annual",
        report_nm="테스트보고서", rcept_no="00000000000000", rcept_dt="20260101",
        flr_nm="테스트", is_correction=False, file_path="raw/periodic/테스트기업/00000000000000",
        file_format="xml", n_files=1,
    )
    base.update(overrides)
    return DocumentRecord(**base)


def _write_raw_xml(tmp_path, text: str):
    doc_dir = tmp_path / "raw" / "periodic" / "테스트기업" / "00000000000000"
    doc_dir.mkdir(parents=True, exist_ok=True)
    (doc_dir / "00000000000000.xml").write_text(text, encoding="utf-8")
    return tmp_path


def _source_file(**overrides) -> SourceFileIR:
    base = dict(
        rel_path="00000000000000.xml", is_attachment=False, content_format=CONTENT_DART_XML,
        schema_version="dart4.xsd", content_sha256="0" * 64, declared_encoding=None,
        actual_encoding_used="utf-8",
    )
    base.update(overrides)
    return SourceFileIR(**base)


def test_build_parse_audit_computes_basic_counts_and_ratio(tmp_path):
    corpus_root = _write_raw_xml(tmp_path, "<?xml version=\"1.0\"?><DOCUMENT><P>본문 텍스트</P></DOCUMENT>")
    doc = _doc()
    ir = DocumentIR(
        doc_id=doc.doc_id, source_files=[_source_file()],
        nodes=[ParagraphIR(node_id="n0", section_hierarchy=[], text="본문 텍스트",
                            source=SourceLocation("00000000000000.xml", 0), is_footnote_like=False)],
        warnings=[], parse_quality=ParseQuality(tier="structured", schema_version="dart4.xsd"),
    )
    audit = build_parse_audit(doc, ir, corpus_root)
    assert audit.doc_id == doc.doc_id
    assert audit.doc_group == "periodic"
    assert audit.n_nodes == 1
    assert audit.n_paragraphs == 1
    assert audit.n_sections == 0
    assert audit.n_tables == 0
    assert audit.parse_quality_tier == "structured"
    assert audit.schema_version == "dart4.xsd"
    assert audit.used_sanitizer is False
    assert audit.used_encoding_recovery is False
    assert audit.used_fallback_parser is False
    assert audit.warning_codes == []
    assert audit.text_preservation_ratio is not None
    assert audit.text_preservation_ratio > 0
    assert len(audit.source_files) == 1
    assert audit.source_files[0].rel_path == "00000000000000.xml"
    assert audit.source_files[0].is_attachment is False


def test_build_parse_audit_flags_sanitizer_and_fallback(tmp_path):
    corpus_root = _write_raw_xml(tmp_path, "<?xml version=\"1.0\"?><DOCUMENT><P>x</P></DOCUMENT>")
    doc = _doc()
    ir = DocumentIR(
        doc_id=doc.doc_id, source_files=[_source_file()],
        nodes=[ParagraphIR(node_id="n0", section_hierarchy=[], text="x",
                            source=SourceLocation("00000000000000.xml", 0), is_footnote_like=False)],
        warnings=[
            ParserWarning(doc.doc_id, "00000000000000.xml", WarningCode.SANITIZED_ENTITY, "info", "sanitized"),
            ParserWarning(doc.doc_id, "00000000000000.xml", WarningCode.PARSE_FAILED, "error", "failed"),
        ],
        parse_quality=ParseQuality(tier="fallback", schema_version=None),
    )
    audit = build_parse_audit(doc, ir, corpus_root)
    assert audit.used_sanitizer is True
    assert audit.used_fallback_parser is True
    assert set(audit.warning_codes) == {"sanitized_entity", "parse_failed"}


def test_build_parse_audit_flags_encoding_recovery_when_replace_used(tmp_path):
    corpus_root = _write_raw_xml(tmp_path, "<?xml version=\"1.0\"?><DOCUMENT><P>x</P></DOCUMENT>")
    doc = _doc()
    ir = DocumentIR(
        doc_id=doc.doc_id, source_files=[_source_file(actual_encoding_used="utf-8(replace)")],
        nodes=[], warnings=[], parse_quality=ParseQuality(tier="partial", schema_version="dart4.xsd"),
    )
    audit = build_parse_audit(doc, ir, corpus_root)
    assert audit.used_encoding_recovery is True


def test_parse_audit_to_dict_is_json_serializable(tmp_path):
    corpus_root = _write_raw_xml(tmp_path, "<?xml version=\"1.0\"?><DOCUMENT><P>x</P></DOCUMENT>")
    doc = _doc()
    ir = DocumentIR(doc_id=doc.doc_id, source_files=[_source_file()], nodes=[], warnings=[],
                     parse_quality=ParseQuality(tier="structured", schema_version="dart4.xsd"))
    audit = build_parse_audit(doc, ir, corpus_root)
    d = audit.to_dict()
    json.dumps(d, ensure_ascii=False)
    assert d["doc_id"] == doc.doc_id


def test_save_parse_audits_jsonl_writes_one_line_per_record(tmp_path):
    corpus_root = _write_raw_xml(tmp_path, "<?xml version=\"1.0\"?><DOCUMENT><P>x</P></DOCUMENT>")
    doc = _doc()
    ir = DocumentIR(doc_id=doc.doc_id, source_files=[_source_file()], nodes=[], warnings=[],
                     parse_quality=ParseQuality(tier="structured", schema_version="dart4.xsd"))
    audits = [build_parse_audit(doc, ir, corpus_root), build_parse_audit(doc, ir, corpus_root)]
    out_path = tmp_path / "parse_audit.jsonl"
    save_parse_audits_jsonl(audits, out_path)
    lines = out_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    for line in lines:
        json.loads(line)  # 예외 없이 파싱되어야 함


def test_load_parse_audits_jsonl_round_trips(tmp_path):
    corpus_root = _write_raw_xml(tmp_path, "<?xml version=\"1.0\"?><DOCUMENT><P>x</P></DOCUMENT>")
    doc = _doc()
    ir = DocumentIR(doc_id=doc.doc_id, source_files=[_source_file()], nodes=[], warnings=[],
                     parse_quality=ParseQuality(tier="structured", schema_version="dart4.xsd"))
    audits = [build_parse_audit(doc, ir, corpus_root)]
    out_path = tmp_path / "parse_audit.jsonl"
    save_parse_audits_jsonl(audits, out_path)
    loaded = load_parse_audits_jsonl(out_path)
    assert loaded == audits


def test_real_document_parse_audit_matches_ir(corpus_root):
    doc = _doc(
        doc_id="periodic_20231114001884", corp_name="HD현대일렉트릭",
        rcept_no="20231114001884", file_path="raw/periodic/HD현대일렉트릭/20231114001884_quarter_2023_09",
    )
    ir = parse_document(doc, corpus_root)
    audit = build_parse_audit(doc, ir, corpus_root)
    assert audit.parse_quality_tier == ir.parse_quality.tier
    assert audit.schema_version == ir.parse_quality.schema_version
    assert len(audit.source_files) == len(ir.source_files)
    assert audit.n_nodes == len(ir.nodes)
    assert 0 < audit.text_preservation_ratio < 2
