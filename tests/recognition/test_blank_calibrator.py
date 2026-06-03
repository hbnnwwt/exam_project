"""空白答卷校准模块测试。"""

from __future__ import annotations

import json
import numpy as np
import pytest

from exam_project.recognition.blank_calibrator import (
    DEFAULT_CHOICE_GRID,
    DEFAULT_JUDGE_GRID,
    ZONE_COUNT_CHOICE,
    ZONE_COUNT_JUDGE,
    _cell_zone_gray_stats,
    _detect_zone_bounds,
    _page_section_types,
    get_choice_baseline_dict,
    get_choice_zone_bounds,
    get_judge_baseline_dict,
    get_judge_zone_bounds,
    load_baseline,
    save_baseline,
)


# ---------------------------------------------------------------------------
# _page_section_types
# ---------------------------------------------------------------------------


def test_page_section_types_with_dict_format() -> None:
    spec = {"sections": [{"type": "choice"}, {"type": "judge"}]}
    assert _page_section_types(spec) == ["choice", "judge"]


def test_page_section_types_with_list_of_strings() -> None:
    assert _page_section_types(["choice", "judge"]) == ["choice", "judge"]


def test_page_section_types_with_mixed_list() -> None:
    spec = [{"type": "choice"}, "judge", {"other": "x"}, ""]
    result = _page_section_types(spec)
    assert "choice" in result
    assert "judge" in result
    assert "" not in result


def test_page_section_types_empty() -> None:
    assert _page_section_types(None) == []
    assert _page_section_types([]) == []


# ---------------------------------------------------------------------------
# _cell_zone_gray_stats
# ---------------------------------------------------------------------------


def test_cell_zone_gray_stats_white_zones() -> None:
    """全白图各 zone 灰度均值应接近 255。"""
    cell = np.full((50, 200), 255, dtype=np.uint8)
    bounds = [(0, 50), (50, 100), (100, 150), (150, 200)]
    stats = _cell_zone_gray_stats(cell, bounds)
    assert len(stats) == 4
    for s in stats:
        assert s["mean"] == pytest.approx(255.0)
        assert s["std"] == pytest.approx(0.0)


def test_cell_zone_gray_stats_black_zones() -> None:
    """全黑图各 zone 均值应接近 0。"""
    cell = np.zeros((50, 200), dtype=np.uint8)
    bounds = [(0, 50), (50, 100), (100, 150), (150, 200)]
    stats = _cell_zone_gray_stats(cell, bounds)
    for s in stats:
        assert s["mean"] == pytest.approx(0.0)


def test_cell_zone_gray_stats_different_zones() -> None:
    """不同 zone 有不同均值。"""
    cell = np.full((50, 200), 255, dtype=np.uint8)
    cell[:, 50:100] = 0  # 中间涂黑
    bounds = [(0, 50), (50, 100), (100, 150), (150, 200)]
    stats = _cell_zone_gray_stats(cell, bounds)
    assert stats[0]["mean"] == pytest.approx(255.0)
    assert stats[1]["mean"] == pytest.approx(0.0)
    assert stats[2]["mean"] == pytest.approx(255.0)


# ---------------------------------------------------------------------------
# _detect_zone_bounds
# ---------------------------------------------------------------------------


def test_detect_zone_bounds_returns_floats() -> None:
    cell = np.full((100, 200), 255, dtype=np.uint8)
    bounds = _detect_zone_bounds(cell, zone_count=4)
    assert len(bounds) == 4
    for left, right in bounds:
        assert 0 <= left < right <= 1


def test_detect_zone_bounds_2_zones_for_judge() -> None:
    cell = np.full((100, 200), 255, dtype=np.uint8)
    bounds = _detect_zone_bounds(cell, zone_count=2)
    assert len(bounds) == 2


def test_detect_zone_bounds_custom_num_w_ratio() -> None:
    cell = np.full((100, 200), 255, dtype=np.uint8)
    bounds = _detect_zone_bounds(cell, zone_count=4, num_w_ratio=0.10)
    assert len(bounds) == 4


# ---------------------------------------------------------------------------
# save_baseline / load_baseline
# ---------------------------------------------------------------------------


def test_save_and_load_baseline(tmp_path) -> None:
    path = tmp_path / "baseline.json"
    data = {
        "choice": {
            "questions": {
                "1": {"zones": [{"mean": 200.0, "std": 5.0}], "zone_bounds_rel": [[0.2, 0.4]]}
            }
        }
    }
    save_baseline(data, path)
    loaded = load_baseline(path)
    assert loaded == data


def test_load_baseline_missing_returns_none(tmp_path) -> None:
    assert load_baseline(tmp_path / "missing.json") is None


def test_save_baseline_creates_parent_dirs(tmp_path) -> None:
    path = tmp_path / "nested" / "sub" / "baseline.json"
    save_baseline({"x": 1}, path)
    assert path.is_file()


# ---------------------------------------------------------------------------
# 提取辅助
# ---------------------------------------------------------------------------


def test_get_choice_baseline_dict_extracts_means() -> None:
    baseline = {
        "choice": {
            "questions": {
                "1": {"zones": [{"mean": 100.0}, {"mean": 200.0}]},
                "2": {"zones": [{"mean": 150.0}, {"mean": 250.0}]},
            }
        }
    }
    result = get_choice_baseline_dict(baseline)
    assert result == {1: [100.0, 200.0], 2: [150.0, 250.0]}


def test_get_judge_baseline_dict_extracts_means() -> None:
    baseline = {
        "judge": {
            "questions": {
                "21": {"zones": [{"mean": 180.0}, {"mean": 220.0}]},
            }
        }
    }
    result = get_judge_baseline_dict(baseline)
    assert result == {21: [180.0, 220.0]}


def test_get_baseline_dict_with_none_returns_none() -> None:
    assert get_choice_baseline_dict(None) is None
    assert get_judge_baseline_dict(None) is None


def test_get_choice_zone_bounds_extracts_bounds() -> None:
    baseline = {
        "choice": {
            "questions": {
                "1": {"zone_bounds_rel": [(0.2, 0.4), (0.4, 0.6)]},
            }
        }
    }
    result = get_choice_zone_bounds(baseline)
    assert result == {1: [(0.2, 0.4), (0.4, 0.6)]}


def test_get_judge_zone_bounds_extracts_bounds() -> None:
    baseline = {
        "judge": {
            "questions": {
                "21": {"zone_bounds_rel": [(0.2, 0.5), (0.5, 0.8)]},
            }
        }
    }
    result = get_judge_zone_bounds(baseline)
    assert result == {21: [(0.2, 0.5), (0.5, 0.8)]}


def test_get_zone_bounds_missing_keeps_dict_empty() -> None:
    baseline = {"choice": {"questions": {"1": {}}}}
    assert get_choice_zone_bounds(baseline) == {}


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------


def test_default_grids_have_required_keys() -> None:
    for grid in (DEFAULT_CHOICE_GRID, DEFAULT_JUDGE_GRID):
        for key in ("rows", "cols", "question_start", "question_count"):
            assert key in grid


def test_zone_counts() -> None:
    assert ZONE_COUNT_CHOICE == 4
    assert ZONE_COUNT_JUDGE == 2
