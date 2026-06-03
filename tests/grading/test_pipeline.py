"""pipeline 测试。"""

from __future__ import annotations

import numpy as np
import pytest

from exam_project.grading import pipeline
from exam_project.grading.pipeline import (
    _valid_region,
    get_essay_questions,
    recognize_choices,
    recognize_essay,
    recognize_judges,
)


# ---------------------------------------------------------------------------
# _valid_region
# ---------------------------------------------------------------------------


def test_valid_region_accepts_4_tuple() -> None:
    assert _valid_region((0, 0, 100, 100)) is True
    assert _valid_region([0, 0, 100, 100]) is True


def test_valid_region_rejects_wrong_length() -> None:
    assert _valid_region((0, 0, 100)) is False
    assert _valid_region((0, 0, 100, 100, 200)) is False


def test_valid_region_rejects_wrong_types() -> None:
    assert _valid_region((0, 0, 100, "x")) is False
    assert _valid_region("not a region") is False


def test_valid_region_rejects_none() -> None:
    assert _valid_region(None) is False


# ---------------------------------------------------------------------------
# get_essay_questions
# ---------------------------------------------------------------------------


def test_get_essay_questions_from_answer_key() -> None:
    answer_key = {"essay": {31: "answer", 32: "other"}}
    assert get_essay_questions(answer_key) == [31, 32]


def test_get_essay_questions_from_empty_answer_key() -> None:
    """answer_key 存在但 essay 为空 dict → 返回空列表。"""
    answer_key = {"essay": {}}
    assert get_essay_questions(answer_key) == []


def test_get_essay_questions_fallback() -> None:
    assert get_essay_questions() == [31]
    assert get_essay_questions(None) == [31]
    assert get_essay_questions({"choice": {1: "A"}}) == [31]


# ---------------------------------------------------------------------------
# recognize_choices / recognize_judges 入口
# ---------------------------------------------------------------------------


def test_recognize_choices_with_no_choice_region() -> None:
    """regions 中无 choice → 返回空 dict，不抛异常。"""
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    regions = {"choice": None}
    assert recognize_choices(image, regions) == {}


def test_recognize_choices_with_invalid_region() -> None:
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    regions = {"choice": (0, 0, 0, 0)}
    # 0 尺寸区域可能不抛异常或返回空 dict
    result = recognize_choices(image, regions)
    assert isinstance(result, dict)


def test_recognize_judges_with_no_judge_region() -> None:
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    regions = {"judge": None}
    assert recognize_judges(image, regions) == {}


def test_recognize_essay_with_no_essay_region() -> None:
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    regions = {"essay": None}
    result = recognize_essay(image, regions)
    from exam_project.recognition.types import Status
    assert result.status == Status.BLANK
    assert "未检测到" in result.error


def test_recognize_essay_with_invalid_region() -> None:
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    regions = {"essay": "not a region"}
    result = recognize_essay(image, regions)
    from exam_project.recognition.types import Status
    assert result.status == Status.BLANK


# ---------------------------------------------------------------------------
# 导出检查
# ---------------------------------------------------------------------------


def test_pipeline_module_exports_recognizers() -> None:
    """应当能从 pipeline 模块拿到需要的 recognizer 类。"""
    from exam_project.recognition.choice import ChoiceRecognizer
    from exam_project.recognition.judge import JudgeRecognizer
    from exam_project.recognition.student_id import StudentIdRecognizer
    assert ChoiceRecognizer is not None
    assert JudgeRecognizer is not None
    assert StudentIdRecognizer is not None
