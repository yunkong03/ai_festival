"""DocumentIR node -> chunking용 평문 텍스트. Parser 코드(src/dart_corpus/parsing/)는
건드리지 않고, DocumentIR을 읽기만 하는 별도 레이어."""
from __future__ import annotations

from dart_corpus.parsing.document_ir import DocumentNodeIR, ParagraphIR, SectionIR, TableIR


def table_to_text(table: TableIR) -> str:
    """normalized_rows가 있으면 그걸 deterministic하게 직렬화한다(같은 TableIR ->
    항상 같은 문자열). normalized_rows가 비어있으면(이론상만 가능 — emit_table은 cells가
    있을 때만 호출됨) raw_rows에서 최소한으로 재구성한다. row 단위로 별도 chunk를
    만들지 않는다 — 이 함수는 표 전체를 하나의 텍스트 블록으로만 반환한다."""
    lines: list[str] = []
    if table.title_confirmed and table.normalized_title_guess:
        lines.append(table.normalized_title_guess.strip())
    rows = table.normalized_rows if table.normalized_rows else [
        [c.text for c in row] for row in table.raw_rows
    ]
    for row in rows:
        lines.append(" | ".join(cell.strip() for cell in row))
    return "\n".join(lines)


def node_to_text(node: DocumentNodeIR) -> str:
    if isinstance(node, SectionIR):
        return node.title_text.strip()
    if isinstance(node, ParagraphIR):
        return node.text.strip()
    if isinstance(node, TableIR):
        return table_to_text(node).strip()
    return ""
