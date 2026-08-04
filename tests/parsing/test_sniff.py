from dart_corpus.parsing.sniff import CONTENT_DART_XML, CONTENT_KIND_HTML, CONTENT_PDF, CONTENT_UNKNOWN, sniff_content_type


def test_sniffs_dart_xml():
    raw = b'<?xml version="1.0" encoding="utf-8"?>\n\n<DOCUMENT xsi:noNamespaceSchemaLocation="dart4.xsd">'
    assert sniff_content_type(raw) == CONTENT_DART_XML


def test_sniffs_kind_html_even_with_xml_extension():
    raw = b'<html>\n <head>\n  <meta content="gdi" http-equiv="X-UA-TextLayoutMetrics">'
    assert sniff_content_type(raw) == CONTENT_KIND_HTML


def test_sniffs_pdf_magic_bytes():
    raw = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"
    assert sniff_content_type(raw) == CONTENT_PDF


def test_unknown_for_garbage():
    assert sniff_content_type(b"\x00\x01\x02 not a real document") == CONTENT_UNKNOWN
