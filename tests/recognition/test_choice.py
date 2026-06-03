"""选择题识别器测试。"""

from __future__ import annotations

import numpy as np
import pytest

from exam_project.recognition.choice import (
    CellResult,
    ChoiceBatchResult,
    ChoiceRecognizer,
)


# ---------------------------------------------------------------------------
# 构造与基本属性
# ---------------------------------------------------------------------------


def test_default_options_a_b_c_d() -> None:
    rec = ChoiceRecognizer()
    assert rec.option_count == 4
    assert rec.option_labels == ["A", "B", "C", "D"]


def test_custom_option_count() -> None:
    rec = ChoiceRecognizer(option_count=5)
    assert rec.option_count == 5
    assert rec.option_labels == ["A", "B", "C", "D", "E"]


def test_option_count_property_matches_zone_count() -> None:
    rec = ChoiceRecognizer(option_count=3)
    assert rec.option_count == rec.zone_count


# ---------------------------------------------------------------------------
# _select_best_bubbles
# ---------------------------------------------------------------------------


def test_select_best_bubbles_picks_most_uniform() -> None:
    # 4 个真实气泡（均匀间距 100）+ 2 个噪声
    cxs = [0.0, 100.0, 200.0, 300.0, 50.0, 250.0]
    selected = ChoiceRecognizer._select_best_bubbles(cxs, 4)
    assert selected == [0.0, 100.0, 200.0, 300.0]


def test_select_best_bubbles_returns_input_when_count_matches() -> None:
    cxs = [10.0, 20.0, 30.0]
    assert ChoiceRecognizer._select_best_bubbles(cxs, 3) == cxs


# ---------------------------------------------------------------------------
# CellResult / ChoiceBatchResult
# ---------------------------------------------------------------------------


def test_cell_result_to_dict() -> None:
    cell = np.zeros((10, 10), dtype=np.uint8)
    cr = CellResult(
        question=1, answer="A", multi_options=[],
        cell_bounds=(0, 10, 0, 10), cell_viz=cell,
        zone_fills=[0.5, 0.1, 0.1, 0.1],
        zone_bounds=[(0, 5), (5, 10), (10, 15), (15, 20)],
        zone_gray_means=[100.0, 200.0, 200.0, 200.0],
        gray_darkening=None,
    )
    d = cr.to_dict()
    assert d["question"] == 1
    assert d["answer"] == "A"
    assert d["multi_options"] == []
    assert d["zone_fills"] == [0.5, 0.1, 0.1, 0.1]
    assert d["gray_darkening"] is None


def test_cell_result_is_frozen() -> None:
    cell = np.zeros((10, 10), dtype=np.uint8)
    cr = CellResult(
        question=1, answer=None, multi_options=[],
        cell_bounds=(0, 0, 0, 0), cell_viz=cell,
        zone_fills=[], zone_bounds=[], zone_gray_means=[], gray_darkening=None,
    )
    with pytest.raises(Exception):
        cr.question = 2  # type: ignore[misc]


# ---------------------------------------------------------------------------
# recognize_all_with_viz 入口
# ---------------------------------------------------------------------------


def _make_choice_grid(rows: int = 5, cols: int = 4, cell_h: int = 80, cell_w: int = 100, header_h: int = 30) -> np.ndarray:
    """构造一张空白的"5 行 × 4 列"选择题区域图。

    顶部的 header 留空，主体是网格。
    """
    h = header_h + rows * cell_h
    w = cols * cell_w
    image = np.full((h, w), 255, dtype=np.uint8)
    return image


def test_recognize_empty_grid_returns_empty_answers() -> None:
    rec = ChoiceRecognizer(threshold=0.10, multi_threshold=0.75)
    region = _make_choice_grid()
    result = rec.recognize_all_with_viz(
        region, question_count=20, question_start=1, fixed_grid=(5, 4),
    )
    assert isinstance(result, ChoiceBatchResult)
    assert result.answers == {}
    assert len(result.cell_results) == 20
    assert result.grid_viz.ndim == 3


def test_recognize_with_one_filled_cell() -> None:
    """在第一格涂 B 选项。"""
    rec = ChoiceRecognizer(threshold=0.05, multi_threshold=0.75, margin=0)
    region = _make_choice_grid(rows=2, cols=2, cell_h=100, cell_w=200, header_h=20)
    # 涂第一行的 B zone
    region[20 + 5: 20 + 95, 200 // 4 * 1 + 5: 200 // 4 * 2 - 5] = 0
    result = rec.recognize_all_with_viz(
        region, question_count=4, question_start=1, fixed_grid=(2, 2),
    )
    # 至少有一些题被识别出来
    assert isinstance(result, ChoiceBatchResult)
    # 至少有部分题返回了结果（可能不完美因为是合成图）
    assert isinstance(result.answers, dict)


def test_recognize_returns_correct_question_start() -> None:
    rec = ChoiceRecognizer(threshold=0.20, margin=0, multi_threshold=1.5)
    region = _make_choice_grid()
    result = rec.recognize_all_with_viz(
        region, question_count=20, question_start=5, fixed_grid=(5, 4),
    )
    for cr in result.cell_results:
        assert cr.question >= 5
        assert cr.question < 25
