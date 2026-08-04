from pathlib import Path

from dart_corpus.parsing.canonical_hash import (
    aggregate_hash,
    canonical_json_bytes,
    compute_parser_config_hash,
    document_ir_hash,
    document_ir_hash_from_dict,
)
from dart_corpus.parsing.document_ir import DocumentIR, ParseQuality


def test_canonical_json_bytes_ignores_key_insertion_order():
    a = {"b": 1, "a": 2}
    b = {"a": 2, "b": 1}
    assert canonical_json_bytes(a) == canonical_json_bytes(b)


def test_canonical_json_bytes_has_no_extra_whitespace():
    data = canonical_json_bytes({"a": 1, "b": [1, 2]})
    assert b" " not in data


def test_document_ir_hash_from_dict_is_deterministic():
    d = {"doc_id": "x", "nodes": [1, 2, 3]}
    assert document_ir_hash_from_dict(d) == document_ir_hash_from_dict(dict(d))


def test_document_ir_hash_from_dict_changes_when_content_changes():
    h1 = document_ir_hash_from_dict({"doc_id": "x"})
    h2 = document_ir_hash_from_dict({"doc_id": "y"})
    assert h1 != h2


def test_document_ir_hash_from_dict_is_64_char_hex():
    h = document_ir_hash_from_dict({"doc_id": "x"})
    assert len(h) == 64
    int(h, 16)  # 예외 없이 hex로 파싱되어야 함


def test_document_ir_hash_matches_hash_from_dict_of_same_document():
    ir = DocumentIR(doc_id="d1", parse_quality=ParseQuality(tier="structured", schema_version="dart4.xsd"))
    from dart_corpus.parsing.serialization import document_ir_to_dict
    assert document_ir_hash(ir) == document_ir_hash_from_dict(document_ir_to_dict(ir))


def test_aggregate_hash_is_independent_of_input_order():
    pairs_a = [("doc1", "hash1"), ("doc2", "hash2")]
    pairs_b = [("doc2", "hash2"), ("doc1", "hash1")]
    assert aggregate_hash(pairs_a) == aggregate_hash(pairs_b)


def test_aggregate_hash_changes_when_any_pair_hash_changes():
    pairs_a = [("doc1", "hash1"), ("doc2", "hash2")]
    pairs_b = [("doc1", "hash1"), ("doc2", "DIFFERENT")]
    assert aggregate_hash(pairs_a) != aggregate_hash(pairs_b)


def test_aggregate_hash_is_deterministic():
    pairs = [("doc1", "hash1"), ("doc2", "hash2")]
    assert aggregate_hash(pairs) == aggregate_hash(list(pairs))


def test_compute_parser_config_hash_changes_when_file_content_changes(tmp_path):
    f1 = tmp_path / "a.py"
    f1.write_text("x = 1", encoding="utf-8")
    h1 = compute_parser_config_hash([f1])
    f1.write_text("x = 2", encoding="utf-8")
    h2 = compute_parser_config_hash([f1])
    assert h1 != h2


def test_compute_parser_config_hash_is_independent_of_path_list_order(tmp_path):
    f1 = tmp_path / "a.py"
    f2 = tmp_path / "b.py"
    f1.write_text("a", encoding="utf-8")
    f2.write_text("b", encoding="utf-8")
    assert compute_parser_config_hash([f1, f2]) == compute_parser_config_hash([f2, f1])


def test_compute_parser_config_hash_stable_across_calls(tmp_path):
    f1 = tmp_path / "a.py"
    f1.write_text("stable content", encoding="utf-8")
    assert compute_parser_config_hash([f1]) == compute_parser_config_hash([f1])
