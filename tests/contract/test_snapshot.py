import hashlib
import json

import pytest

from dart_corpus.contract.paths import resolve_corpus_path
from dart_corpus.contract.snapshot import (
    CorpusSnapshotReport,
    _peek_schema_version,
    build_snapshot_report,
    compute_corpus_snapshot,
    derive_corpus_snapshot_id,
    hash_source_files_for_document,
    sha256_of_file,
    validate,
)
from dart_corpus.contract.manifest import ManifestLoader


def test_peek_schema_version_dart4(corpus_root):
    doc_dir = resolve_corpus_path(corpus_root, "raw/periodic/한화에어로스페이스/20260316001112_annual_2025_12")
    assert _peek_schema_version(doc_dir / "20260316001112.xml") == "dart4.xsd"


def test_peek_schema_version_dart3(corpus_root):
    doc_dir = resolve_corpus_path(corpus_root, "raw/periodic/CJ제일제당/20230515002270_quarter_2023_03")
    assert _peek_schema_version(doc_dir / "20230515002270.xml") == "dart3.xsd"


def test_peek_schema_version_html_exchange(corpus_root):
    doc_dir = resolve_corpus_path(corpus_root, "raw/exchange/HD현대일렉트릭/20230131800162")
    assert _peek_schema_version(doc_dir / "20230131800162.xml") == "n/a_html"


def test_validate_passes_on_healthy_report():
    report = CorpusSnapshotReport(
        manifest_row_count=4204, universe_row_count=70,
        manifest_row_count_ok=True, universe_row_count_ok=True,
        major_doc_subtype_all_blank=True, corp_code_leading_zero_ok=True,
    )
    assert validate(report) == []


def test_validate_flags_broken_report():
    report = CorpusSnapshotReport(
        manifest_row_count=100, universe_row_count=70,
        manifest_row_count_ok=False, universe_row_count_ok=True,
        path_resolution_failures=["raw/major/없는회사/123"],
        major_doc_subtype_all_blank=False, corp_code_leading_zero_ok=False,
    )
    problems = validate(report)
    assert len(problems) == 4  # manifest count, path resolution, major subtype, corp_code


@pytest.mark.integration
def test_build_snapshot_report_full_corpus(corpus_root):
    """전체 4204건 대상 — 실제 코퍼스 규모 검증(느림, 수십초 소요 가능)."""
    report = build_snapshot_report(corpus_root)
    assert report.manifest_row_count == 4204
    assert report.universe_row_count == 70
    assert report.major_doc_subtype_all_blank is True
    assert report.corp_code_leading_zero_ok is True
    assert report.file_format_histogram.get("pdf+html") == 3
    assert report.file_format_histogram.get("xml") == 4201
    # [확인] dart3/dart4 스키마버전 혼재(워크스트림 A 설계 리포트 §2 신규 발견)
    assert "dart3.xsd" in report.schema_version_histogram
    assert "dart4.xsd" in report.schema_version_histogram
    assert "n/a_html" in report.schema_version_histogram
    assert report.path_resolution_failures == []


def test_sha256_of_file_matches_known_content(tmp_path):
    p = tmp_path / "f.txt"
    p.write_bytes(b"hello")
    assert sha256_of_file(p) == hashlib.sha256(b"hello").hexdigest()


def test_derive_corpus_snapshot_id_deterministic_and_prefixed():
    id1 = derive_corpus_snapshot_id("aaa", "bbb")
    id2 = derive_corpus_snapshot_id("aaa", "bbb")
    assert id1 == id2
    assert id1.startswith("snap_")


def test_derive_corpus_snapshot_id_changes_when_inputs_change():
    id1 = derive_corpus_snapshot_id("aaa", "bbb")
    id2 = derive_corpus_snapshot_id("aaa", "ccc")
    assert id1 != id2


def test_hash_source_files_for_document_matches_actual_file_bytes(corpus_root):
    doc = next(r for r in ManifestLoader(corpus_root).load() if r.doc_id == "periodic_20231114001884")
    hashes = hash_source_files_for_document(corpus_root, doc)
    doc_dir = resolve_corpus_path(corpus_root, doc.file_path)
    assert set(hashes.keys()) == {p.name for p in doc_dir.iterdir() if p.suffix.lower() == ".xml"}
    for rel_path, digest in hashes.items():
        assert digest == sha256_of_file(doc_dir / rel_path)


def test_hash_source_files_for_document_handles_pdf_html(corpus_root):
    doc = next(r for r in ManifestLoader(corpus_root).load() if r.doc_id == "periodic_20260513000860")
    hashes = hash_source_files_for_document(corpus_root, doc)
    assert "20260513000860.pdf" in hashes
    assert "20260513000860_viewer.html" in hashes


def _write_tiny_synthetic_corpus(tmp_path):
    manifest_line = json.dumps({
        "doc_id": "periodic_00000000000000", "corp_code": "00000001", "corp_name": "테스트기업",
        "listed_name": "테스트", "stock_code": "000000", "industry": "IT", "sector": "테스트섹터",
        "doc_group": "periodic", "doc_subtype": "annual", "report_nm": "테스트보고서",
        "rcept_no": "00000000000000", "rcept_dt": "20260101", "flr_nm": "테스트",
        "is_correction": False, "file_path": "raw/periodic/테스트기업/00000000000000",
        "file_format": "xml", "n_files": 1,
    }, ensure_ascii=False)
    (tmp_path / "manifest.jsonl").write_text(manifest_line + "\n", encoding="utf-8")
    (tmp_path / "universe.csv").write_text(
        "corp_code,stock_code,corp_name,listed_name,corp_eng_name,market,industry,sector_no,sector,"
        "listing_date,fiscal_month,market_cap,n_periodic,n_major,n_exchange,n_holding,note\n"
        "00000001,000000,테스트기업,테스트,Test Co,KOSPI,IT,1,테스트섹터,20000101,12,1000,1,1,1,1,\n",
        encoding="utf-8",
    )
    return tmp_path


def test_compute_corpus_snapshot_hashes_manifest_and_universe_files(tmp_path):
    _write_tiny_synthetic_corpus(tmp_path)
    manifest_bytes = (tmp_path / "manifest.jsonl").read_bytes()
    universe_bytes = (tmp_path / "universe.csv").read_bytes()
    snap = compute_corpus_snapshot(tmp_path, hash_source_files=False)
    assert snap.manifest_sha256 == hashlib.sha256(manifest_bytes).hexdigest()
    assert snap.universe_sha256 == hashlib.sha256(universe_bytes).hexdigest()
    assert snap.corpus_snapshot_id == derive_corpus_snapshot_id(snap.manifest_sha256, snap.universe_sha256)
    assert snap.source_file_hashes == {}


def test_compute_corpus_snapshot_to_dict_is_json_serializable(tmp_path):
    _write_tiny_synthetic_corpus(tmp_path)
    snap = compute_corpus_snapshot(tmp_path, hash_source_files=False)
    d = snap.to_dict()
    json.dumps(d, ensure_ascii=False)  # 예외 없이 직렬화되어야 함
    assert d["corpus_snapshot_id"] == snap.corpus_snapshot_id
    assert d["manifest_sha256"] == snap.manifest_sha256
    assert "report" in d


@pytest.mark.integration
def test_compute_corpus_snapshot_without_hashing_matches_real_corpus_counts(corpus_root):
    snap = compute_corpus_snapshot(corpus_root, hash_source_files=False)
    assert len(snap.manifest_sha256) == 64
    assert snap.report.manifest_row_count == 4204
    assert snap.source_file_hashes == {}


@pytest.mark.integration
def test_compute_corpus_snapshot_hashes_all_4204_documents(corpus_root):
    snap = compute_corpus_snapshot(corpus_root, hash_source_files=True)
    assert snap.n_documents_verified == 4204
    assert len(snap.source_file_hashes) == 4204
    assert snap.n_source_files_hashed > 4204  # 다건 첨부 있는 문서들 때문에 파일 수 > 문서 수
