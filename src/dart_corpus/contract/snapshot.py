"""Corpus Snapshot 생성기 + 검증기 (workstream_a_documentir_design.md §1).

파싱을 시작하기 전에 통과해야 하는 게이트 — manifest/universe 행수, 파일포맷 분포,
경로 해석 성공률, n_files 대조, 스키마버전(dart3/dart4) 히스토그램, major
doc_subtype 공백 여부, corp_code 앞자리 0 보존 여부를 확인한다. 이 단계에서는
XML 본문 구조를 파싱하지 않는다 — 스키마버전 확인용으로 파일 앞부분 몇백 바이트만
읽는다(Parser Phase가 아니라 Snapshot Phase).
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from dart_corpus.contract.manifest import EXPECTED_DOCUMENT_COUNT, DocumentRecord, ManifestLoader
from dart_corpus.contract.paths import PathResolutionError, list_xml_files, resolve_corpus_path
from dart_corpus.contract.universe import EXPECTED_COMPANY_COUNT, UniverseLoader

logger = logging.getLogger(__name__)

# DART XML 문서의 스키마 선언(<DOCUMENT xsi:noNamespaceSchemaLocation="dart4.xsd">)만 읽는다.
# exchange(KIND HTML)는 이 선언 자체가 없다 — "n/a_html"로 분류.
_SCHEMA_RE = re.compile(r'noNamespaceSchemaLocation="([^"]+)"')
_SCHEMA_PEEK_BYTES = 400   # [확인] 선언은 파일 맨 앞 300바이트 안에 항상 나옴(이번 세션 실측)

# doc_group별 기대 파서 정책(workstream_a_documentir_design.md §4) — snapshot 단계에서는
# 이 정보를 "스키마버전 히스토그램을 잴 대상인지"만 판단하는 데 쓴다(실제 파싱은 안 함).
_DART_XML_GROUPS = {"periodic", "major", "holding"}


@dataclass
class CorpusSnapshotReport:
    manifest_row_count: int
    universe_row_count: int
    manifest_row_count_ok: bool
    universe_row_count_ok: bool
    file_format_histogram: dict[str, int] = field(default_factory=dict)
    doc_group_histogram: dict[str, int] = field(default_factory=dict)
    schema_version_histogram: dict[str, int] = field(default_factory=dict)
    n_files_mismatch: list[str] = field(default_factory=list)          # doc_id 목록
    path_resolution_failures: list[str] = field(default_factory=list)   # file_path 목록
    major_doc_subtype_all_blank: bool = False
    corp_code_leading_zero_ok: bool = False


def _peek_schema_version(xml_path: Path) -> str:
    try:
        with open(xml_path, encoding="utf-8", errors="replace") as f:
            head = f.read(_SCHEMA_PEEK_BYTES)
    except OSError:
        return "unreadable"
    m = _SCHEMA_RE.search(head)
    if m:
        return m.group(1)
    if head.lstrip().startswith("<html") or head.lstrip().startswith("<!"):
        return "n/a_html"
    return "unknown"


def build_snapshot_report(corpus_root: Path) -> CorpusSnapshotReport:
    corpus_root = Path(corpus_root)
    manifest_records = ManifestLoader(corpus_root).load()
    universe_records = UniverseLoader(corpus_root).load()

    report = CorpusSnapshotReport(
        manifest_row_count=len(manifest_records),
        universe_row_count=len(universe_records),
        manifest_row_count_ok=len(manifest_records) == EXPECTED_DOCUMENT_COUNT,
        universe_row_count_ok=len(universe_records) == EXPECTED_COMPANY_COUNT,
    )

    for rec in manifest_records:
        report.file_format_histogram[rec.file_format] = report.file_format_histogram.get(rec.file_format, 0) + 1
        report.doc_group_histogram[rec.doc_group] = report.doc_group_histogram.get(rec.doc_group, 0) + 1

    major_subtypes = {r.doc_subtype for r in manifest_records if r.doc_group == "major"}
    report.major_doc_subtype_all_blank = major_subtypes == {""}

    # corp_code 앞자리 0 보존 확인: 8자리 문자열이고, 실제로 '0'으로 시작하는 사례가
    # 하나라도 있어야 "보존됐다"고 말할 수 있다(전부 non-zero-leading이면 이 체크가
    # 아무 의미 없이 통과해버리는 걸 방지).
    corp_codes = {r.corp_code for r in manifest_records}
    all_are_8char_str = all(isinstance(c, str) and len(c) == 8 for c in corp_codes)
    any_leading_zero = any(c.startswith("0") for c in corp_codes)
    report.corp_code_leading_zero_ok = all_are_8char_str and any_leading_zero

    for rec in manifest_records:
        _check_document_on_disk(corpus_root, rec, report)

    return report


def _check_document_on_disk(corpus_root: Path, rec: DocumentRecord, report: CorpusSnapshotReport) -> None:
    try:
        doc_dir = resolve_corpus_path(corpus_root, rec.file_path)
    except PathResolutionError:
        report.path_resolution_failures.append(rec.file_path)
        return

    if rec.file_format != "xml":
        return  # pdf+html 3건은 xml 파일 목록/스키마버전 체크 대상이 아님(§9 별도 처리)

    xml_files = list_xml_files(doc_dir)
    if len(xml_files) != rec.n_files:
        report.n_files_mismatch.append(rec.doc_id)

    if rec.doc_group not in _DART_XML_GROUPS and rec.doc_group != "exchange":
        return
    main_file = next((p for p in xml_files if p.stem == rec.rcept_no), xml_files[0] if xml_files else None)
    if main_file is None:
        return
    version = _peek_schema_version(main_file)
    report.schema_version_histogram[version] = report.schema_version_histogram.get(version, 0) + 1


def validate(report: CorpusSnapshotReport) -> list[str]:
    """게이트 통과 여부 판정 — 실패 목록을 반환(비어있으면 통과, 파싱 단계 진행 가능)."""
    problems: list[str] = []
    if not report.manifest_row_count_ok:
        problems.append(f"manifest 행수 {report.manifest_row_count} != 기대값 {EXPECTED_DOCUMENT_COUNT}")
    if not report.universe_row_count_ok:
        problems.append(f"universe 행수 {report.universe_row_count} != 기대값 {EXPECTED_COMPANY_COUNT}")
    if report.path_resolution_failures:
        problems.append(f"경로 해석 실패 {len(report.path_resolution_failures)}건")
    if not report.major_doc_subtype_all_blank:
        problems.append("major doc_subtype이 전부 공백이라는 [확인]된 전제가 깨짐 — derive_subtype 로직 재검토 필요")
    if not report.corp_code_leading_zero_ok:
        problems.append("corp_code 앞자리 0 보존 실패(또는 검증 자체가 무의미한 데이터)")
    # n_files_mismatch는 게이트 실패가 아니라 경고로만(문서 하나하나 실제 원인이 다를 수 있음 — §다음단계에서 개별 조사)
    return problems


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def derive_corpus_snapshot_id(manifest_sha256: str, universe_sha256: str) -> str:
    """manifest/universe 해시만으로 결정되는 스냅샷 ID — 코퍼스 원본이 바뀌지 않는 한
    재실행해도 항상 같은 값(DocumentIR.corpus_snapshot_id로 역참조하기 위한 안정 키)."""
    digest = hashlib.sha256(f"{manifest_sha256}|{universe_sha256}".encode("utf-8")).hexdigest()
    return f"snap_{digest[:16]}"


def hash_source_files_for_document(corpus_root: Path, rec: DocumentRecord) -> dict[str, str]:
    """문서 1건의 실제 원본 파일(들)에 대한 rel_path -> SHA-256. pdf+html은 pdf+viewer.html
    둘 다, xml은 doc_dir 안의 모든 .xml(첨부 포함)을 대상으로 한다."""
    doc_dir = resolve_corpus_path(corpus_root, rec.file_path)
    hashes: dict[str, str] = {}
    if rec.file_format == "pdf+html":
        for name in (f"{rec.rcept_no}.pdf", f"{rec.rcept_no}_viewer.html"):
            path = doc_dir / name
            if path.exists():
                hashes[name] = sha256_of_file(path)
        return hashes
    for xml_path in list_xml_files(doc_dir):
        hashes[xml_path.name] = sha256_of_file(xml_path)
    return hashes


@dataclass
class CorpusSnapshot:
    corpus_snapshot_id: str
    manifest_sha256: str
    universe_sha256: str
    report: CorpusSnapshotReport
    n_documents_verified: int
    n_source_files_hashed: int
    source_file_hashes: dict[str, dict[str, str]] = field(default_factory=dict)   # doc_id -> {rel_path: sha256}

    def to_dict(self) -> dict:
        return {
            "corpus_snapshot_id": self.corpus_snapshot_id,
            "manifest_sha256": self.manifest_sha256,
            "universe_sha256": self.universe_sha256,
            "report": asdict(self.report),
            "n_documents_verified": self.n_documents_verified,
            "n_source_files_hashed": self.n_source_files_hashed,
            "source_file_hashes": self.source_file_hashes,
        }


def compute_corpus_snapshot(corpus_root: Path, *, hash_source_files: bool = True) -> CorpusSnapshot:
    """게이트 리포트(build_snapshot_report) + manifest/universe/source-file SHA-256 +
    corpus_snapshot_id를 합쳐 corpus_snapshot.json으로 직렬화 가능한 형태를 만든다.
    hash_source_files=False면 source_file_hashes는 비워둔다(빠른 검증용 — 전체 4204건
    해시는 파일 I/O가 무거워서 기본은 True지만 단위테스트에선 끈다)."""
    corpus_root = Path(corpus_root)
    manifest_sha256 = sha256_of_file(corpus_root / "manifest.jsonl")
    universe_sha256 = sha256_of_file(corpus_root / "universe.csv")
    corpus_snapshot_id = derive_corpus_snapshot_id(manifest_sha256, universe_sha256)

    report = build_snapshot_report(corpus_root)

    source_file_hashes: dict[str, dict[str, str]] = {}
    n_source_files_hashed = 0
    n_documents_verified = 0
    if hash_source_files:
        manifest_records = ManifestLoader(corpus_root).load()
        for rec in manifest_records:
            try:
                hashes = hash_source_files_for_document(corpus_root, rec)
            except PathResolutionError:
                continue
            source_file_hashes[rec.doc_id] = hashes
            n_source_files_hashed += len(hashes)
            n_documents_verified += 1

    return CorpusSnapshot(
        corpus_snapshot_id=corpus_snapshot_id,
        manifest_sha256=manifest_sha256,
        universe_sha256=universe_sha256,
        report=report,
        n_documents_verified=n_documents_verified,
        n_source_files_hashed=n_source_files_hashed,
        source_file_hashes=source_file_hashes,
    )
