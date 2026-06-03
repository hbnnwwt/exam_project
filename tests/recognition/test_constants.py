"""识别层常量测试。"""

from __future__ import annotations

import pytest

from exam_project.recognition import constants


def test_image_exts_contains_common_formats() -> None:
    for ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif"):
        assert ext in constants.IMAGE_EXTS


def test_image_exts_is_frozenset() -> None:
    assert isinstance(constants.IMAGE_EXTS, frozenset)


def test_is_image_file_recognizes_known_formats() -> None:
    assert constants.is_image_file("foo.png")
    assert constants.is_image_file("FOO.PNG")  # 大小写不敏感
    assert constants.is_image_file("foo.jpeg")
    assert constants.is_image_file("foo.tiff")
    assert not constants.is_image_file("foo.txt")
    assert not constants.is_image_file("foo")


def test_natural_sort_key_orders_by_number() -> None:
    paths = ["kaojuan_10.png", "kaojuan_2.png", "kaojuan_1.png"]
    keys = [constants.natural_sort_key(p) for p in paths]
    # 按数字排序：1, 2, 10
    assert sorted(paths, key=constants.natural_sort_key) == [
        "kaojuan_1.png",
        "kaojuan_2.png",
        "kaojuan_10.png",
    ]
    # 确认是数字 key，不是字符串 key
    assert isinstance(keys[0][1], int)


def test_natural_sort_key_handles_no_digits() -> None:
    """无数字时整个文件名作为单个字符串 key。"""
    key = constants.natural_sort_key("foo.png")
    assert key == ["foo.png"]


def test_sorted_image_paths_returns_list() -> None:
    paths = ["b.png", "a.png", "c.png"]
    result = constants.sorted_image_paths(paths)
    assert isinstance(result, list)
    assert result == ["a.png", "b.png", "c.png"]


def test_morph_kernel_is_2_tuple() -> None:
    assert isinstance(constants.MORPH_KERNEL, tuple)
    assert len(constants.MORPH_KERNEL) == 2


def test_judge_constants_in_expected_ranges() -> None:
    """判断题阈值应当满足不变量：低 < 高，min < multi。"""
    assert constants.JUDGE_STAIN_FILL_LOW < constants.JUDGE_STAIN_FILL_HIGH
    assert constants.JUDGE_STAIN_FILL_HIGH < constants.JUDGE_MULTI_FILL
    assert 0 < constants.JUDGE_STAIN_RATIO < 1
    assert 0 < constants.JUDGE_VALID_RATIO < 1
    assert constants.JUDGE_BLOB_AREA_MIN < constants.JUDGE_BLOB_AREA_MAX
    assert constants.JUDGE_BLOB_ASPECT_MIN < constants.JUDGE_BLOB_ASPECT_MAX


def test_default_api_models_non_empty() -> None:
    assert constants.DEFAULT_BASE_URL.startswith("http")
    assert constants.DEFAULT_LLM_MODEL
    assert constants.DEFAULT_OCR_MODEL
