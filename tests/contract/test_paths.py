import unicodedata

import pytest

from dart_corpus.contract.paths import PathResolutionError, list_xml_files, resolve_corpus_path


def test_resolves_nfd_company_folder(corpus_root):
    # raw/major/삼성전자 는 manifest.jsonl엔 NFC로 적혀있지만 실제 이 WSL 마운트의
    # 디렉터리 엔트리는 NFD로 저장돼있다 — 그냥 Path 조인하면 존재 안 하는 걸로 나옴.
    resolved = resolve_corpus_path(corpus_root, "raw/major/삼성전자")
    assert resolved.is_dir()
    # 주의: resolved.name은 디스크상 NFD라 리터럴 "삼"(NFC)과 바이트 단위로 다르다 —
    # 이 assert 자체가 NFD/NFC 문제의 실물 사례라 normalize 없이 비교하면 실패한다.
    assert unicodedata.normalize("NFC", resolved.name) == "삼성전자"


def test_resolves_full_document_path_and_lists_xml(corpus_root):
    doc_dir = resolve_corpus_path(corpus_root, "raw/exchange/HD현대일렉트릭/20230131800162")
    xml_files = list_xml_files(doc_dir)
    assert [p.name for p in xml_files] == ["20230131800162.xml"]


def test_raises_on_missing_segment(corpus_root):
    with pytest.raises(PathResolutionError):
        resolve_corpus_path(corpus_root, "raw/major/이런회사는없음/00000000000000")
