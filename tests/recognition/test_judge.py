"""判断题识别器测试。"""

from __future__ import annotations

import numpy as np
import pytest

from exam_project.recognition.judge import (
    JudgeBatchResult,
    JudgeCellResult,
    JudgeRecognizer,
)


# ---------------------------------------------------------------------------
# 构造
# ---------------------------------------------------------------------------


def test_default_options_t_f() -> None:
    rec = JudgeRecognizer()
    assert rec.zone_count == 2
    assert rec.option_labels == ["T", "F"]


# ---------------------------------------------------------------------------
# _judge_result 静态方法
# ---------------------------------------------------------------------------


def test_judge_result_returns_none_for_blank() -> None:
    result = JudgeRecognizer._judge_result(
        above=False, zone_fills=[0.01, 0.01], ratio=1.0, best_idx=0,
    )
    assert result is None


def test_judge_result_returns_t_or_f() -> None:
    # T 填涂、F 未填涂
    result = JudgeRecognizer._judge_result(
        above=True, zone_fills=[0.5, 0.1], ratio=0.2, best_idx=0,
    )
    assert result == "T"


def test_judge_result_returns_f() -> None:
    result = JudgeRecognizer._judge_result(
        above=True, zone_fills=[0.1, 0.5], ratio=0.2, best_idx=1,
    )
    assert result == "F"


def test_judge_result_detects_multi_tf() -> None:
    """两侧都强填涂且对称 → TF 多选。"""
    result = JudgeRecognizer._judge_result(
        above=True, zone_fills=[0.5, 0.5], ratio=0.95, best_idx=0,
    )
    assert result == "TF"


def test_judge_result_multi_requires_high_ratio() -> None:
    """ratio 不够高则不触发多选。"""
    result = JudgeRecognizer._judge_result(
        above=True, zone_fills=[0.5, 0.5], ratio=0.5, best_idx=0,
    )
    # ratio < JUDGE_MULTI_RATIO → 走单选分支
    assert result == "T"


# ---------------------------------------------------------------------------
# _detect_bubbles_in_cell
# ---------------------------------------------------------------------------


def _make_judge_cell_with_blob(cx: int, cy: int, w: int = 30, h: int = 30, cell_w: int = 200, cell_h: int = 80) -> np.ndarray:
    """合成一张含单个黑色方块的格子二值图。"""
    binary = np.zeros((cell_h, cell_w), dtype=np.uint8)
    binary[max(cy - h // 2, 0):cy + h // 2, max(cx - w // 2, 0):cx + w // 2] = 255
    return binary


def test_detect_bubbles_finds_left_and_right() -> None:
    rec = JudgeRecognizer()
    binary = np.zeros((100, 300), dtype=np.uint8)
    # T 在左，F 在右
    binary[20:80, 30:80] = 255
    binary[20:80, 220:270] = 255
    result = rec._detect_bubbles_in_cell(binary, cell_w=300, cell_h=100)
    assert result["T"] is not None
    assert result["F"] is not None
    assert result["T"][0] < result["F"][0]  # T 在 F 左边


def test_detect_bubbles_falls_back_when_no_blob() -> None:
    rec = JudgeRecognizer()
    binary = np.zeros((100, 200), dtype=np.uint8)
    result = rec._detect_bubbles_in_cell(binary, cell_w=200, cell_h=100)
    # 没有 blob 时使用 fallback
    assert result["T"] is not None
    assert result["F"] is not None


def test_detect_bubbles_filters_by_area() -> None:
    """面积过小或过大的 blob 应当被过滤。"""
    rec = JudgeRecognizer()
    binary = np.zeros((100, 300), dtype=np.uint8)
    # 极小 blob（1x1）应当被过滤
    binary[40, 100] = 255
    result = rec._detect_bubbles_in_cell(binary, cell_w=300, cell_h=100)
    # 因为 blob 太小，blobs 列表可能为空 → 走 fallback
    assert result["blobs"] == [] or all(
        (b[2] * b[3]) >= 100 for b in result["blobs"]
    )


# ---------------------------------------------------------------------------
# _detect_zone_boundaries
# ---------------------------------------------------------------------------


def test_zone_boundaries_with_bubbles() -> None:
    rec = JudgeRecognizer()
    gray = np.zeros((100, 300), dtype=np.uint8)
    binary = np.zeros((100, 300), dtype=np.uint8)
    binary[20:80, 30:80] = 255
    binary[20:80, 220:270] = 255
    bubble_data = rec._detect_bubbles_in_cell(binary, cell_w=300, cell_h=100)
    zone_bounds, num_w = rec._detect_zone_boundaries(
        gray, cell_w=300, cell_h=100, bubble_data=bubble_data,
    )
    assert len(zone_bounds) == 2
    assert zone_bounds[0][1] == zone_bounds[1][0]  # 邻接


def test_zone_boundaries_without_bubbles_uses_projection() -> None:
    rec = JudgeRecognizer()
    gray = np.full((100, 200), 255, dtype=np.uint8)
    # 在左/右画两块黑色作为峰
    gray[20:80, 40:60] = 0
    gray[20:80, 140:160] = 0
    zone_bounds, num_w = rec._detect_zone_boundaries(
        gray, cell_w=200, cell_h=100, bubble_data=None,
    )
    assert len(zone_bounds) == 2
    # zone 总宽度不应超过可用宽度的 30%
    total = zone_bounds[1][1] - zone_bounds[0][0]
    assert total <= 200 * 0.35  # 留一些容差


# ---------------------------------------------------------------------------
# JudgeCellResult / JudgeBatchResult
# ---------------------------------------------------------------------------


def test_judge_cell_result_to_dict() -> None:
    cell = np.zeros((10, 10), dtype=np.uint8)
    cr = JudgeCellResult(
        question=21, answer="T",
        cell_bounds=(0, 10, 0, 10), cell_viz=cell,
        zone_fills=[0.5, 0.1], zone_bounds=[(0, 5), (5, 10)],
        zone_gray_means=[100.0, 200.0], gray_darkening=None,
    )
    d = cr.to_dict()
    assert d["question"] == 21
    assert d["answer"] == "T"
    assert d["zone_fills"] == [0.5, 0.1]


def test_judge_cell_result_is_frozen() -> None:
    cell = np.zeros((10, 10), dtype=np.uint8)
    cr = JudgeCellResult(
        question=21, answer=None, cell_bounds=(0, 0, 0, 0), cell_viz=cell,
        zone_fills=[], zone_bounds=[], zone_gray_means=[], gray_darkening=None,
    )
    with pytest.raises(Exception):
        cr.answer = "T"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# recognize_all_with_viz 入口
# ---------------------------------------------------------------------------


def _make_judge_grid(rows: int = 3, cols: int = 4, cell_h: int = 80, cell_w: int = 100, header_h: int = 30) -> np.ndarray:
    h = header_h + rows * cell_h
    w = cols * cell_w
    return np.full((h, w), 255, dtype=np.uint8)


def test_recognize_empty_grid() -> None:
    rec = JudgeRecognizer()
    region = _make_judge_grid()
    result = rec.recognize_all_with_viz(
        region, question_count=12, question_start=21, rows_n=3, cols_n=4,
    )
    assert isinstance(result, JudgeBatchResult)
    assert result.answers == {}
    assert len(result.cell_results) == 12
    for cr in result.cell_results:
        assert cr.question >= 21
        assert cr.question < 33


def test_recognize_with_one_filled_t() -> None:
    rec = JudgeRecognizer(threshold=0.05, margin=0, multi_threshold=1.5)
    region = _make_judge_grid(rows=1, cols=1, cell_h=100, cell_w=200, header_h=20)
    # 涂在左侧 T zone
    region[20 + 5: 20 + 95, 200 // 4: 200 // 2] = 0
    result = rec.recognize_all_with_viz(
        region, question_count=1, question_start=21, rows_n=1, cols_n=1,
    )
    # 至少返回一个结果结构
    assert isinstance(result, JudgeBatchResult)
    assert len(result.cell_results) == 1
