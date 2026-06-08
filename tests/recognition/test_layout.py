"""版面分析配置与回退逻辑测试。

cv2 实际像素运算不在单测范围。
此处覆盖：
- LayoutConfig 默认值与 from_dict
- _fallback_region 数学正确性
- _normalize_fallback 边界处理
"""

from __future__ import annotations

import pytest

from exam_project.recognition.layout import (
    LayoutConfig,
    LayoutAnalyzer,
    PageRegions,
    _normalize_fallback,
)


# ---------------------------------------------------------------------------
# LayoutConfig 默认值
# ---------------------------------------------------------------------------


def test_default_config_has_expected_fallbacks() -> None:
    config = LayoutConfig()
    assert "student_id" in config.page1_fallback
    assert "choice" in config.page1_fallback
    assert "judge" in config.page2_fallback
    assert "essay" in config.page2_fallback
    # 元组格式
    for value in config.page1_fallback.values():
        assert isinstance(value, tuple)
        assert len(value) == 2
        assert 0 <= value[0] < value[1] <= 1


def test_default_config_pages_is_none() -> None:
    assert LayoutConfig().pages is None


# ---------------------------------------------------------------------------
# LayoutConfig.from_dict
# ---------------------------------------------------------------------------


def test_from_dict_with_valid_layout() -> None:
    data = {
        "layout": {
            "page1_fallback": {"student_id": [0.10, 0.30], "choice": [0.35, 0.85]},
            "page2_fallback": {"judge": [0.10, 0.50], "essay": [0.55, 0.95]},
        }
    }
    config = LayoutConfig.from_dict(data)
    assert config.page1_fallback["student_id"] == (0.10, 0.30)
    assert config.page1_fallback["choice"] == (0.35, 0.85)
    assert config.page2_fallback["judge"] == (0.10, 0.50)
    assert config.page2_fallback["essay"] == (0.55, 0.95)


def test_from_dict_with_pages() -> None:
    data = {
        "_pages": [
            {"sections": [{"type": "student_id"}, {"type": "choice"}]},
            {"sections": [{"type": "judge"}, {"type": "essay"}]},
        ]
    }
    config = LayoutConfig.from_dict(data)
    assert config.pages is not None
    assert len(config.pages) == 2


def test_from_dict_preserves_page_specific_fallbacks_for_repeated_sections() -> None:
    data = {
        "layout": {
            "page1_fallback": {"choice": [0.10, 0.20]},
            "page2_fallback": {"choice": [0.70, 0.90]},
        }
    }

    config = LayoutConfig.from_dict(data)

    assert config.page_fallbacks[1]["choice"] == (0.10, 0.20)
    assert config.page_fallbacks[2]["choice"] == (0.70, 0.90)


def test_from_dict_with_empty_dict_uses_defaults() -> None:
    config = LayoutConfig.from_dict({})
    assert config.page1_fallback["student_id"] == (0.06, 0.26)


def test_from_dict_with_invalid_input_returns_defaults() -> None:
    # 整个 data 不是字典：应回退到默认值
    config = LayoutConfig.from_dict("not a dict")  # type: ignore[arg-type]
    assert config.page1_fallback == LayoutConfig().page1_fallback


def test_from_dict_with_invalid_value_uses_default_for_that_key() -> None:
    data = {
        "layout": {
            "page1_fallback": {
                "student_id": "not a list",  # 非法值
                "choice": [0.30, 0.85],  # 合法
            }
        }
    }
    config = LayoutConfig.from_dict(data)
    # student_id 回退到默认
    assert config.page1_fallback["student_id"] == (0.06, 0.26)
    # choice 接受
    assert config.page1_fallback["choice"] == (0.30, 0.85)


def test_from_dict_with_wrong_length_list_uses_default() -> None:
    data = {"layout": {"page1_fallback": {"student_id": [0.1, 0.2, 0.3]}}}
    config = LayoutConfig.from_dict(data)
    assert config.page1_fallback["student_id"] == (0.06, 0.26)


# ---------------------------------------------------------------------------
# _normalize_fallback
# ---------------------------------------------------------------------------


def test_normalize_returns_defaults_when_raw_is_none() -> None:
    defaults = {"a": (0.0, 0.5), "b": (0.5, 1.0)}
    assert _normalize_fallback(None, defaults) == defaults


def test_normalize_returns_defaults_when_raw_is_not_dict() -> None:
    defaults = {"a": (0.0, 0.5)}
    assert _normalize_fallback("string", defaults) == defaults
    assert _normalize_fallback([], defaults) == defaults


def test_normalize_preserves_all_default_keys() -> None:
    """normalize 应当返回所有默认键的完整集合，不是 partial dict。"""
    raw = {"student_id": [0.1, 0.3]}  # 只覆盖一个
    result = _normalize_fallback(raw, {
        "student_id": (0.0, 0.1),
        "choice": (0.2, 0.8),
    })
    assert set(result.keys()) == {"student_id", "choice"}


# ---------------------------------------------------------------------------
# _fallback_region 数学
# ---------------------------------------------------------------------------


def test_fallback_region_computes_correct_rect() -> None:
    # image h=1000, w=800
    rect = LayoutAnalyzer._fallback_region(1000, 800, (0.1, 0.5))
    x, y, w, h = rect
    assert x == 0
    assert w == 800
    assert y == 100
    assert h == 400  # 1000 * (0.5 - 0.1) = 400


def test_fallback_region_full_height() -> None:
    rect = LayoutAnalyzer._fallback_region(500, 400, (0.0, 1.0))
    x, y, w, h = rect
    assert y == 0
    assert h == 500


# ---------------------------------------------------------------------------
# PageRegions
# ---------------------------------------------------------------------------


def test_page_regions_all_none_by_default() -> None:
    regions = PageRegions()
    assert regions.student_id is None
    assert regions.choice is None
    assert regions.judge is None
    assert regions.essay is None
    assert regions.boxes == ()


def test_page_regions_to_dict_roundtrip() -> None:
    regions = PageRegions(
        student_id=(10, 20, 100, 30),
        choice=(10, 100, 100, 200),
        image_size=(800, 1000),
        boxes=((10, 20, 100, 30), (10, 100, 100, 200)),
    )
    data = regions.to_dict()
    assert data["student_id"] == (10, 20, 100, 30)
    assert data["choice"] == (10, 100, 100, 200)
    assert data["image_size"] == (800, 1000)
    assert len(data["boxes"]) == 2


def test_page_regions_is_frozen() -> None:
    regions = PageRegions(student_id=(0, 0, 10, 10))
    with pytest.raises(Exception):
        regions.student_id = (0, 0, 5, 5)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# analyze 入口形状契约（happy path with synthetic image）
# ---------------------------------------------------------------------------


def test_analyze_returns_page_regions() -> None:
    import numpy as np
    analyzer = LayoutAnalyzer()
    image = np.full((400, 400, 3), 255, dtype=np.uint8)
    binary = np.zeros((400, 400), dtype=np.uint8)
    regions = analyzer.analyze(image, binary, page=1)
    assert isinstance(regions, PageRegions)
    # 二值全黑：无内容，回退到固定比例
    assert regions.student_id is not None
    assert regions.choice is not None


def test_analyze_multipage_empty_returns_empty() -> None:
    analyzer = LayoutAnalyzer()
    result = analyzer.analyze_multipage([], [])
    assert result == []


def test_analyze_multipage_mismatched_length_raises() -> None:
    import numpy as np
    analyzer = LayoutAnalyzer()
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    bin_ = np.zeros((100, 100), dtype=np.uint8)
    with pytest.raises(ValueError, match="数量必须一致"):
        analyzer.analyze_multipage([img], [bin_, bin_])


def test_filter_boxes_keeps_wide_judge_region() -> None:
    import cv2
    import numpy as np

    analyzer = LayoutAnalyzer()
    mask = np.zeros((2000, 5000), dtype=np.uint8)
    cv2.rectangle(mask, (200, 900), (4490, 1635), 255, 2)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = analyzer._filter_boxes(contours, mask.size)

    assert boxes == [(199, 899, 4293, 738)]


def test_filter_boxes_rejects_overly_flat_header_line() -> None:
    import cv2
    import numpy as np

    analyzer = LayoutAnalyzer()
    mask = np.zeros((2000, 5000), dtype=np.uint8)
    cv2.rectangle(mask, (200, 300), (4500, 600), 255, 2)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = analyzer._filter_boxes(contours, mask.size)

    assert boxes == []


def test_regions_from_spec_matches_boxes_by_fallback_overlap() -> None:
    data = {
        "layout": {
            "page2_fallback": {
                "judge": [0.0, 0.1613],
                "essay": [0.183, 0.927],
            }
        }
    }
    analyzer = LayoutAnalyzer(LayoutConfig.from_dict(data))
    essay_box = (171, 1869, 4319, 3829)
    regions = analyzer._regions_from_spec(
        [essay_box],
        {"sections": [{"type": "judge"}, {"type": "essay"}]},
        h=6736,
        w=4764,
    )

    assert regions.judge == (0, 897, 4764, 875)
    assert regions.essay == essay_box


def test_fallback_regions_from_spec_uses_current_page_fallback_ratios() -> None:
    data = {
        "layout": {
            "page1_fallback": {"choice": [0.10, 0.20]},
            "page2_fallback": {"choice": [0.70, 0.90]},
        },
        "_pages": [
            {"page_number": 1, "sections": [{"type": "choice"}]},
            {"page_number": 2, "sections": [{"type": "choice"}]},
        ],
    }
    analyzer = LayoutAnalyzer(LayoutConfig.from_dict(data))

    page1 = analyzer.fallback_regions_from_spec(data["_pages"][0], h=1000, w=800)
    page2 = analyzer.fallback_regions_from_spec(data["_pages"][1], h=1000, w=800)

    assert page1["choice"][1] < 300
    assert page2["choice"][1] > 600
