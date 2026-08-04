import csv
import json

from dart_corpus.parsing.audit import ParseAuditRecord
from dart_corpus.parsing.gold_candidates import select_gold_candidates, write_annotation_template_csv, write_gold_candidates_jsonl


def _audit(doc_id, doc_group, tier, **overrides) -> ParseAuditRecord:
    base = dict(doc_id=doc_id, doc_group=doc_group, parse_quality_tier=tier, schema_version="dart4.xsd",
                n_tables=1, n_sections=1, n_paragraphs=1, n_nodes=3, warning_codes=[],
                text_preservation_ratio=0.9)
    base.update(overrides)
    return ParseAuditRecord(**base)


def _synthetic_audits():
    audits = []
    for group in ["periodic", "major", "exchange", "holding"]:
        for tier in ["structured", "partial", "fallback"]:
            for i in range(10):
                audits.append(_audit(f"{group}_{tier}_{i}", group, tier))
    return audits  # 4 groups * 3 tiers * 10 = 120 docs


def test_select_gold_candidates_covers_every_non_empty_stratum():
    audits = _synthetic_audits()
    candidates = select_gold_candidates(audits, target_total=90, seed=0)
    strata_present = {(c.doc_group, c.parse_quality_tier) for c in candidates}
    expected_strata = {(g, t) for g in ["periodic", "major", "exchange", "holding"]
                        for t in ["structured", "partial", "fallback"]}
    assert strata_present == expected_strata


def test_select_gold_candidates_respects_target_total_when_enough_docs():
    audits = _synthetic_audits()
    candidates = select_gold_candidates(audits, target_total=90, seed=0)
    assert len(candidates) == 90


def test_select_gold_candidates_never_exceeds_stratum_size():
    audits = _synthetic_audits()
    candidates = select_gold_candidates(audits, target_total=90, seed=0)
    from collections import Counter
    counts = Counter((c.doc_group, c.parse_quality_tier) for c in candidates)
    for key, n in counts.items():
        assert n <= 10  # 각 stratum엔 10건씩밖에 없음


def test_select_gold_candidates_is_deterministic_given_seed():
    audits = _synthetic_audits()
    c1 = select_gold_candidates(audits, target_total=90, seed=0)
    c2 = select_gold_candidates(audits, target_total=90, seed=0)
    assert [c.doc_id for c in c1] == [c.doc_id for c in c2]


def test_select_gold_candidates_records_selection_reason():
    audits = _synthetic_audits()
    candidates = select_gold_candidates(audits, target_total=90, seed=0)
    for c in candidates:
        assert c.selection_reason
        assert c.doc_group in c.selection_reason
        assert c.parse_quality_tier in c.selection_reason


def test_select_gold_candidates_handles_small_corpus_smaller_than_target():
    audits = [_audit("a", "periodic", "structured"), _audit("b", "major", "partial")]
    candidates = select_gold_candidates(audits, target_total=90, seed=0)
    assert len(candidates) == 2


def test_select_gold_candidates_empty_input_returns_empty():
    assert select_gold_candidates([], target_total=90, seed=0) == []


def test_write_gold_candidates_jsonl_is_valid_jsonl(tmp_path):
    audits = _synthetic_audits()
    candidates = select_gold_candidates(audits, target_total=20, seed=0)
    path = tmp_path / "parser_gold_candidates.jsonl"
    write_gold_candidates_jsonl(candidates, path)
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == len(candidates)
    for line in lines:
        d = json.loads(line)
        assert "doc_id" in d and "selection_reason" in d


def test_write_annotation_template_csv_has_blank_judgment_columns(tmp_path):
    audits = _synthetic_audits()
    candidates = select_gold_candidates(audits, target_total=20, seed=0)
    path = tmp_path / "template.csv"
    write_annotation_template_csv(candidates, path)
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(candidates)
    for row in rows:
        assert row["doc_id"]
        assert row["decision"] == ""
        assert row["reviewer_name"] == ""
        assert row["notes"] == ""
