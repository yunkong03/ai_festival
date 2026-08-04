from dart_corpus.parsing.encoding import decode_with_fallback


def test_utf8_declared_and_actual_no_mismatch():
    raw = '<?xml version="1.0" encoding="utf-8"?><P>안녕</P>'.encode("utf-8")
    result = decode_with_fallback(raw)
    assert result.detected_encoding == "utf-8"
    assert result.declared_encoding == "utf-8"
    assert result.mismatch is False


def test_declared_euckr_but_actual_utf8_flags_mismatch():
    # 실측 재현: exchange 파일이 <meta charset="euc-kr">라고 선언하지만 실제 바이트는 utf-8
    # (workstream_a_documentir_contract.md §검증2, exchange_20230406800008 실물 확인).
    html = '<html><head><meta content="text/html; charset=euc-kr" http-equiv="Content-Type"></head><body>한글</body></html>'
    raw = html.encode("utf-8")   # 선언은 euc-kr이지만 실제로는 utf-8로 인코딩된 바이트
    result = decode_with_fallback(raw)
    assert result.declared_encoding == "euc-kr"
    assert result.detected_encoding == "utf-8"   # utf-8을 먼저 시도해서 성공 — 선언 무시하고 우선
    assert result.mismatch is True
    assert "한글" in result.text


def test_genuinely_euckr_encoded_bytes_fallback_to_declared():
    html = '<html><head><meta charset="euc-kr"></head><body>한글</body></html>'
    raw = html.encode("euc-kr")   # 이번엔 진짜로 euc-kr 바이트
    result = decode_with_fallback(raw)
    # utf-8 strict가 실패해야 하고(진짜 euc-kr 바이트라서), declared로 fallback 성공
    assert result.detected_encoding == "euc-kr"
    assert result.mismatch is False
    assert "한글" in result.text


def test_last_resort_utf8_replace_when_nothing_works():
    raw = b"\xff\xfe\x00\x01 garbage not text-like at all \xfa"
    result = decode_with_fallback(raw)
    assert result.detected_encoding == "utf-8(replace)"
    # 예외 안 나고 뭐라도 반환됨
    assert isinstance(result.text, str)
