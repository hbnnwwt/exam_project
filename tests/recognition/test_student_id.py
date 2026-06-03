"""学号识别器测试。"""

from __future__ import annotations

import numpy as np
import pytest

from exam_project.recognition.student_id import (
    StudentIdRecognizer,
    StudentIdResult,
    StudentIdVizResult,
)


# ---------------------------------------------------------------------------
# 构造
# ---------------------------------------------------------------------------


def test_default_digit_count_is_10() -> None:
    rec = StudentIdRecognizer()
    assert rec.digit_count == 10
    assert rec.total_rows == 11


def test_invalid_digit_count_raises() -> None:
    with pytest.raises(ValueError, match="digit_count"):
        StudentIdRecognizer(digit_count=0)


def test_custom_digit_count() -> None:
    rec = StudentIdRecognizer(digit_count=8)
    assert rec.digit_count == 8
    assert rec.total_rows == 9


# ---------------------------------------------------------------------------
# recognize 基础行为
# ---------------------------------------------------------------------------


def test_recognize_returns_string_of_correct_length() -> None:
    rec = StudentIdRecognizer()
    # 输入全白图，无法检测到网格
    roi = np.full((200, 300), 255, dtype=np.uint8)
    result = rec.recognize(roi)
    assert isinstance(result, str)
    assert len(result) == 10


def test_recognize_unfilled_returns_question_marks() -> None:
    """无填涂时返回 '?'*digit_count。"""
    rec = StudentIdRecognizer()
    roi = np.full((200, 300), 255, dtype=np.uint8)
    result = rec.recognize(roi)
    assert result == "?" * 10


def test_recognize_ambiguity_warnings_cleared_between_calls() -> None:
    """每次 recognize 调用应当重置 ambiguity_warnings。"""
    rec = StudentIdRecognizer()
    roi = np.full((200, 300), 255, dtype=np.uint8)
    rec.recognize(roi)
    assert rec.ambiguity_warnings == []


# ---------------------------------------------------------------------------
# recognize_with_viz 入口
# ---------------------------------------------------------------------------


def test_recognize_with_viz_returns_three_fields() -> None:
    rec = StudentIdRecognizer()
    roi = np.full((200, 300), 255, dtype=np.uint8)
    result = rec.recognize_with_viz(roi)
    assert isinstance(result, StudentIdVizResult)
    assert isinstance(result.student_id, str)
    assert len(result.student_id) == 10
    assert isinstance(result.viz_image, np.ndarray)
    assert isinstance(result.digit_details, list)


def test_recognize_with_viz_blank_returns_no_details() -> None:
    rec = StudentIdRecognizer()
    roi = np.full((200, 300), 255, dtype=np.uint8)
    result = rec.recognize_with_viz(roi)
    assert result.digit_details == []


# ---------------------------------------------------------------------------
# StudentIdResult / StudentIdVizResult
# ---------------------------------------------------------------------------


def test_student_id_result_is_blank_property() -> None:
    r = StudentIdResult(
        student_id="??????????",
        digits=[None] * 10,
        fill_grid=[[0.0] * 10 for _ in range(10)],
        bounds=(0, 0, 100, 100),
        cell_size=(10.0, 10.0),
    )
    assert r.is_blank is True


def test_student_id_result_is_blank_false_when_some_known() -> None:
    r = StudentIdResult(
        student_id="1????????",
        digits=[1] + [None] * 9,
        fill_grid=[[0.0] * 10 for _ in range(10)],
        bounds=(0, 0, 100, 100),
        cell_size=(10.0, 10.0),
    )
    assert r.is_blank is False


def test_student_id_result_is_frozen() -> None:
    r = StudentIdResult(
        student_id="1234567890",
        digits=list(range(10)),
        fill_grid=[],
        bounds=(0, 0, 0, 0),
        cell_size=(0.0, 0.0),
    )
    with pytest.raises(Exception):
        r.student_id = "0000000000"  # type: ignore[misc]
