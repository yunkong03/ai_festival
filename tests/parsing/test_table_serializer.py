from dart_corpus.parsing.document_ir import TableCellIR
from dart_corpus.parsing.table_serializer import (
    compute_shape_diagnostics, detect_header_row_indices, expand_normalized_rows,
    extract_table_metadata, group_into_raw_rows, infer_consolidation_basis, shape_mismatch_warning,
)


# --- fixture: dart3 TD 중심 표(실측: periodic/major/holding dart3 문서는 TD가 우세) ---
def test_dart3_td_table_grouping_and_shape():
    cells = [
        TableCellIR(row=0, col=0, text="구분", tag="TD"),
        TableCellIR(row=0, col=1, text="당기", tag="TD"),
        TableCellIR(row=1, col=0, text="자산총계", tag="TD"),
        TableCellIR(row=1, col=1, text="1,000", tag="TD"),
    ]
    raw_rows = group_into_raw_rows(cells)
    assert len(raw_rows) == 2
    n_declared, actual_counts = compute_shape_diagnostics(raw_rows)
    assert n_declared == 2
    assert actual_counts == [2, 2]
    assert shape_mismatch_warning("d", "r", "n1", actual_counts, n_declared) is None


# --- fixture: dart4 TE 중심 표(실측: periodic dart4 문서는 TE가 우세) ---
def test_dart4_te_table_common_cell_handling():
    cells = [
        TableCellIR(row=0, col=0, text="구분", tag="TE"),
        TableCellIR(row=0, col=1, text="당기", tag="TE"),
        TableCellIR(row=1, col=0, text="매출액", tag="TE"),
        TableCellIR(row=1, col=1, text="2,000", tag="TE"),
    ]
    raw_rows = group_into_raw_rows(cells)
    normalized = expand_normalized_rows(raw_rows)
    assert normalized == [["구분", "당기"], ["매출액", "2,000"]]


# --- fixture: rowspan/colspan 표(실측: 240건 파일럿에서 13,631회 발생 — 흔한 패턴) ---
def test_rowspan_colspan_expands_to_rectangular_grid():
    # row0: "구분"(rowspan=2) | "금액"(colspan=2)
    # row1:                  | "당기" | "전기"
    cells = [
        TableCellIR(row=0, col=0, text="구분", rowspan=2, colspan=1, tag="TH"),
        TableCellIR(row=0, col=1, text="금액", rowspan=1, colspan=2, tag="TH"),
        TableCellIR(row=1, col=1, text="당기", tag="TH"),
        TableCellIR(row=1, col=2, text="전기", tag="TH"),
    ]
    raw_rows = group_into_raw_rows(cells)
    normalized = expand_normalized_rows(raw_rows)
    assert normalized == [
        ["구분", "금액", "금액"],
        ["구분", "당기", "전기"],
    ]


# --- fixture: 다중 header 표(실측: 아모레퍼시픽 periodic_20240516000601 "2-1. 연결
# 재무상태표" TABLE-GROUP — 첫 TR이 전부 TH 태그인 컬럼헤더 행, 이후 TR은 전부 TE) ---
def test_multi_row_header_detection_by_th_majority():
    cells = [
        TableCellIR(row=0, col=0, text="", tag="TH"),
        TableCellIR(row=0, col=1, text="제 19 기 1분기말", tag="TH"),
        TableCellIR(row=0, col=2, text="제 18 기말", tag="TH"),
        TableCellIR(row=1, col=0, text="자산", tag="TE"),
        TableCellIR(row=1, col=1, text="", tag="TE"),
        TableCellIR(row=1, col=2, text="", tag="TE"),
        TableCellIR(row=2, col=0, text="유동자산", tag="TE"),
        TableCellIR(row=2, col=1, text="2,103,110,604,841", tag="TE"),
        TableCellIR(row=2, col=2, text="1,952,196,456,821", tag="TE"),
    ]
    raw_rows = group_into_raw_rows(cells)
    header_rows = detect_header_row_indices(raw_rows)
    assert header_rows == [0]


def test_shape_mismatch_warning_fires_on_ragged_rows():
    cells = [
        TableCellIR(row=0, col=0, text="a", tag="TD"),
        TableCellIR(row=0, col=1, text="b", tag="TD"),
        TableCellIR(row=1, col=0, text="c", tag="TD"),
        TableCellIR(row=1, col=1, text="d", tag="TD"),
        TableCellIR(row=2, col=0, text="e", tag="TD"),   # row2는 1칸뿐 — shape mismatch
    ]
    raw_rows = group_into_raw_rows(cells)
    n_declared, actual_counts = compute_shape_diagnostics(raw_rows)
    assert n_declared == 2
    assert actual_counts == [2, 2, 1]
    w = shape_mismatch_warning("d", "r", "n1", actual_counts, n_declared)
    assert w is not None
    assert "2" in w.message and "rows" in w.message


def test_table_metadata_confirmed_with_unit_and_period():
    meta = extract_table_metadata("2-1. 연결 재무상태표 (단위 : 원) 제 19 기 1분기말")
    assert meta.title_confirmed is True
    assert meta.unit_text == "원"
    assert meta.period_text == "제 19 기"


def test_table_metadata_confirmed_title_but_uncertain_unit_period():
    meta = extract_table_metadata("2-1. 연결 재무상태표")
    assert meta.title_confirmed is True
    assert meta.unit_text is None
    assert meta.period_text is None


def test_table_metadata_no_embedded_title_is_none_not_guessed():
    meta = extract_table_metadata(None)
    assert meta.title_confirmed is False
    assert meta.title is None
    assert meta.unit_text is None
    assert meta.period_text is None


# --- consolidation_basis: section_hierarchy 기반 연결/별도 추론 ---
def test_consolidation_basis_matched_from_nearest_hierarchy_title():
    basis, reason = infer_consolidation_basis(["2. 재무제표", "2-1. 연결 재무상태표"])
    assert basis == "연결"
    assert "2-1. 연결 재무상태표" in reason


def test_consolidation_basis_matches_separate():
    basis, reason = infer_consolidation_basis(["3. 별도재무제표", "3-1. 별도 재무상태표"])
    assert basis == "별도"
    assert "3-1. 별도 재무상태표" in reason


def test_consolidation_basis_nearest_title_wins_over_farther_ancestor():
    # 조부모가 "연결", 부모가 "별도"인 드문 케이스 — 더 가까운(마지막) 쪽을 신뢰한다
    basis, reason = infer_consolidation_basis(["I. 연결재무제표", "가. 별도재무제표 주석"])
    assert basis == "별도"


def test_consolidation_basis_ambiguous_same_title_returns_none():
    basis, reason = infer_consolidation_basis(["연결 및 별도 재무제표 비교"])
    assert basis is None
    assert "ambiguous" in reason


def test_consolidation_basis_no_marker_returns_none_without_reason():
    basis, reason = infer_consolidation_basis(["II. 사업의 내용", "1. 사업개요"])
    assert basis is None
    assert reason is None


def test_consolidation_basis_empty_hierarchy_returns_none():
    basis, reason = infer_consolidation_basis([])
    assert basis is None
    assert reason is None
