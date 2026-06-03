"""BubbleRecognizerBase 测试。

构造参数校验、识别逻辑用合成图覆盖。
cv2 像素细节不单测。
"""

from __future__ import annotations

import numpy as np
import pytest

from exam_project.recognition.bubble_base import (
    BubbleRecognizerBase,
    ZoneAnalysis,
)


# ---------------------------------------------------------------------------
# 构造
# ---------------------------------------------------------------------------


def test_default_labels_are_a_b_c_d() -> None:
    rec = BubbleRecognizerBase()
    assert rec.option_labels == ["A", "B", "C", "D"]


def test_custom_labels() -> None:
    rec = BubbleRecognizerBase(zone_count=3, option_labels=["T", "F", "?"])
    assert rec.zone_count == 3
    assert rec.option_labels == ["T", "F", "?"]


def test_invalid_zone_count_raises() -> None:
    with pytest.raises(ValueError, match="zone_count"):
        BubbleRecognizerBase(zone_count=0)


def test_invalid_margin_raises() -> None:
    with pytest.raises(ValueError, match="margin"):
        BubbleRecognizerBase(margin=-1)


# ---------------------------------------------------------------------------
# 合成图识别
# ---------------------------------------------------------------------------


def _make_filled_choice_image(zone: int, zone_count: int = 4, w: int = 400, h: int = 100) -> np.ndarray:
    """生成一张把指定 zone 涂满的灰度图。"""
    image = np.full((h, w), 255, dtype=np.uint8)  # 白底
    zone_w = w // zone_count
    x0 = zone * zone_w
    x1 = (zone + 1) * zone_w
    image[:, x0 + 5: x1 - 5] = 0  # 涂黑
    return image


def test_recognize_returns_correct_option() -> None:
    rec = BubbleRecognizerBase(threshold=0.05)
    image = _make_filled_choice_image(zone=1)
    assert rec.recognize(image) == "B"


def test_recognize_returns_none_for_blank() -> None:
    rec = BubbleRecognizerBase(threshold=0.05)
    image = np.full((100, 400), 255, dtype=np.uint8)
    assert rec.recognize(image) is None


def test_recognize_with_custom_options() -> None:
    rec = BubbleRecognizerBase(threshold=0.05, option_labels=["甲", "乙", "丙", "丁"])
    image = _make_filled_choice_image(zone=2)
    assert rec.recognize(image) == "丙"


def test_recognize_multizone_returns_none() -> None:
    """多选应当返回 None（一个题里涂了多个）。"""
    rec = BubbleRecognizerBase(threshold=0.05, multi_threshold=0.05)
    image = np.full((100, 400), 255, dtype=np.uint8)
    image[:, 100:140] = 0
    image[:, 200:240] = 0
    assert rec.recognize(image) is None


def test_recognize_with_viz_returns_three_values() -> None:
    rec = BubbleRecognizerBase(margin=0)  # 显式 margin=0 避免裁剪改变 shape
    image = _make_filled_choice_image(zone=0)
    result, viz, fills = rec.recognize_with_viz(image)
    assert result == "A"
    assert viz.ndim == 3
    assert viz.shape == (100, 400, 3)
    assert len(fills) == 4
    assert fills[0] > 0  # 涂黑的 zone 填涂率应当 > 0


def test_recognize_with_trim_margin() -> None:
    rec = BubbleRecognizerBase(margin=10, threshold=0.05)
    image = np.full((100, 400), 255, dtype=np.uint8)
    # 涂在中间 zone（裁剪后还能看到）
    image[:, 100:140] = 0
    assert rec.recognize(image) == "B"


def test_recognize_margin_too_large_returns_untouched() -> None:
    """margin 大于等于半边时不应裁剪。"""
    rec = BubbleRecognizerBase(margin=60, threshold=0.05)  # 60 > 100/2
    image = _make_filled_choice_image(zone=1)
    # 不应抛异常
    result = rec.recognize(image)
    assert result in ("A", "B", "C", "D")


# ---------------------------------------------------------------------------
# ZoneAnalysis
# ---------------------------------------------------------------------------


def test_zone_analysis_is_frozen() -> None:
    z = ZoneAnalysis(zone_fills=(0.1, 0.2), best_idx=1, above_threshold=True, is_multi=False)
    with pytest.raises(Exception):
        z.best_idx = 0  # type: ignore[misc]


def test_zone_analysis_as_dict_roundtrip() -> None:
    z = ZoneAnalysis(zone_fills=(0.1, 0.5, 0.3), best_idx=1, above_threshold=True, is_multi=False)
    d = z.as_dict()
    assert d["best_idx"] == 1
    assert d["zone_fills"] == [0.1, 0.5, 0.3]
    assert d["above_threshold"] is True
    assert d["is_multi"] is False


# ---------------------------------------------------------------------------
# _find_gaps
# ---------------------------------------------------------------------------


def test_find_gaps_finds_blank_band_in_middle() -> None:
    """白色段 = 间隙。"""
    binary = np.full((10, 10), 255, dtype=np.uint8)
    binary[3:5, :] = 0  # 中间两行白
    gaps = BubbleRecognizerBase._find_gaps(binary, axis=0, min_gap=2, w=10, h=10)
    assert (3, 5) in gaps


def test_find_gaps_skips_short_bands() -> None:
    """min_gap 过滤掉短间隙。"""
    binary = np.full((10, 10), 255, dtype=np.uint8)
    binary[3, :] = 0  # 1px 间隙
    gaps = BubbleRecognizerBase._find_gaps(binary, axis=0, min_gap=2, w=10, h=10)
    assert (3, 4) not in gaps


def test_find_gaps_axis_1_finds_vertical_gaps() -> None:
    """列方向的间隙。"""
    binary = np.full((10, 10), 255, dtype=np.uint8)
    binary[:, 3:5] = 0
    gaps = BubbleRecognizerBase._find_gaps(binary, axis=1, min_gap=2, w=10, h=10)
    assert (3, 5) in gaps
