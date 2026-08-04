"""Encoding 탐지 — declared(파일이 주장하는 인코딩)와 detected(실제로 디코딩에 쓴 인코딩)를
분리해서 둘 다 기록한다. exchange 파일은 `<meta charset="euc-kr">`라고 선언하지만 실제
바이트는 utf-8이다(workstream_a_documentir_contract.md §검증2, 실측: euc-kr로 디코딩하면
`illegal multibyte sequence` 에러). **선언을 신뢰하지 않고 UTF-8을 먼저 시도**하되,
UTF-8이 실패하는 진짜 다른 인코딩 파일도 있을 수 있으므로 fallback을 둔다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_XML_ENCODING_RE = re.compile(rb'<\?xml[^>]*\bencoding="([^"]+)"', re.IGNORECASE)
_HTML_META_CHARSET_RE = re.compile(rb'charset=["\']?([\w-]+)', re.IGNORECASE)


@dataclass(frozen=True)
class DecodeResult:
    text: str
    declared_encoding: str | None
    detected_encoding: str          # 실제로 디코딩에 성공한 인코딩(또는 "utf-8(replace)" 최후수단)
    mismatch: bool                    # declared가 있는데 detected와 다르면 True


def _extract_declared_encoding(raw: bytes) -> str | None:
    head = raw[:512]
    m = _XML_ENCODING_RE.search(head)
    if m:
        return m.group(1).decode("ascii", errors="replace").lower()
    m = _HTML_META_CHARSET_RE.search(head)
    if m:
        return m.group(1).decode("ascii", errors="replace").lower()
    return None


def _normalize_encoding_name(name: str) -> str:
    return name.lower().replace("_", "-")


def decode_with_fallback(raw: bytes) -> DecodeResult:
    """순서: (1) UTF-8 strict 시도 → 성공하면 그걸 씀(선언과 무관하게 우선).
    (2) 실패하면 선언된 인코딩으로 strict 시도. (3) 그것도 실패하면 UTF-8 + errors="replace"
    최후수단(정보 손실 있지만 파싱은 계속 진행). declared와 실제 쓴 인코딩이 다르면
    mismatch=True(ENCODING_DECLARATION_MISMATCH 경고의 근거)."""
    declared = _extract_declared_encoding(raw)

    try:
        text = raw.decode("utf-8", errors="strict")
        detected = "utf-8"
    except UnicodeDecodeError:
        text = None
        detected = None
        if declared:
            try:
                text = raw.decode(declared, errors="strict")
                detected = declared
            except (UnicodeDecodeError, LookupError):
                pass
        if text is None:
            text = raw.decode("utf-8", errors="replace")
            detected = "utf-8(replace)"

    mismatch = bool(declared) and _normalize_encoding_name(declared) != _normalize_encoding_name(detected.replace("(replace)", ""))
    return DecodeResult(text=text, declared_encoding=declared, detected_encoding=detected, mismatch=mismatch)
