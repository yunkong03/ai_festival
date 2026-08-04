"""실제 content type sniffing — manifest.file_format이나 확장자를 신뢰하지 않는다
(workstream_a_documentir_contract.md §검증1: file_format="xml"은 "내용이 XML"이라는
보장이 아니다 — exchange 1469건은 .xml 확장자인데 실제로는 HTML이다, 실측 확인됨).

이 모듈은 raw bytes만 보고 실제 content type을 판별한다.
"""
from __future__ import annotations

import re

_XML_DECL_RE = re.compile(rb"^\s*<\?xml\b", re.IGNORECASE)
_DART_DOCUMENT_RE = re.compile(rb"<DOCUMENT\b", re.IGNORECASE)
_HTML_RE = re.compile(rb"^\s*<(?:!doctype\s+html|html\b)", re.IGNORECASE)
_PDF_MAGIC = b"%PDF"

CONTENT_DART_XML = "dart_xml"
CONTENT_KIND_HTML = "kind_html"
CONTENT_PDF = "pdf"
CONTENT_UNKNOWN = "unknown"


def sniff_content_type(raw: bytes) -> str:
    """raw 파일 바이트만 보고 실제 콘텐츠 종류를 판별한다(확장자/manifest 필드 안 봄).

    순서: PDF 매직바이트 → HTML 루트 → XML 선언+DOCUMENT 루트 → unknown.
    HTML을 XML보다 먼저 확인하는 이유: exchange 파일은 <?xml?> 선언이 아예 없고
    바로 <html>로 시작하므로 순서가 결과에 영향 없지만, 방어적으로 더 구체적인
    신호(PDF 매직, HTML 루트)를 먼저 본다.
    """
    head = raw[:512]
    if head.lstrip().startswith(_PDF_MAGIC):
        return CONTENT_PDF
    if _HTML_RE.match(head):
        return CONTENT_KIND_HTML
    if _XML_DECL_RE.match(head) or _DART_DOCUMENT_RE.search(raw[:2000]):
        return CONTENT_DART_XML
    return CONTENT_UNKNOWN
