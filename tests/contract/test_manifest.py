from dart_corpus.contract.manifest import ManifestLoader, derive_subtype


def test_loads_4204_documents_with_string_codes(corpus_root):
    docs = ManifestLoader(corpus_root).load()
    assert len(docs) == 4204
    hanwha = next(d for d in docs if d.doc_id == "periodic_20260316001112")
    assert hanwha.corp_name == "한화에어로스페이스"
    assert isinstance(hanwha.corp_code, str)
    assert hanwha.file_path == "raw/periodic/한화에어로스페이스/20260316001112_annual_2025_12"


def test_flags_pdf_html_as_unsupported_not_dropped(corpus_root):
    loader = ManifestLoader(corpus_root)
    docs = loader.load()
    unsupported = loader.unsupported(docs)
    assert len(unsupported) == 3
    assert all(d.file_format == "pdf+html" for d in unsupported)
    assert all(d in docs for d in unsupported)


def test_major_doc_subtype_all_blank_and_derived_subtype_fills_it(corpus_root):
    docs = ManifestLoader(corpus_root).load()
    major_docs = [d for d in docs if d.doc_group == "major"]
    assert len(major_docs) == 598
    # [확인] corpus_coverage_strategy.md §0.1 — major doc_subtype 전부 빈 문자열
    assert all(d.doc_subtype == "" for d in major_docs)
    # derived_subtype은 비어있으면 안 됨(report_nm에서 뽑아냈어야 함)
    assert all(d.derived_subtype != "" for d in major_docs)


def test_derive_subtype_strips_correction_tag_and_extracts_parens():
    assert derive_subtype("주요사항보고서(유상증자결정)", "") == "유상증자결정"
    assert derive_subtype("[기재정정]주요사항보고서(유상증자결정)", "") == "유상증자결정"
    assert derive_subtype("단일판매ㆍ공급계약체결", "단일판매공급계약체결") == "단일판매공급계약체결"
