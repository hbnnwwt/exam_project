"""识别层数据类型测试。"""

from __future__ import annotations

import pytest

from exam_project.recognition.types import RecognizeResult, Status


def test_default_result_is_blank() -> None:
    result = RecognizeResult()
    assert result.text == ""
    assert result.status == Status.BLANK
    assert result.is_blank is True
    assert result.is_system_failure is False


def test_ok_with_text_is_not_blank() -> None:
    result = RecognizeResult(text="A", status=Status.OK)
    assert result.is_blank is False
    assert result.is_system_failure is False


def test_ok_with_whitespace_only_is_blank() -> None:
    result = RecognizeResult(text="   ", status=Status.OK)
    assert result.is_blank is True


def test_engine_missing_is_system_failure() -> None:
    for status in (
        Status.ENGINE_MISSING,
        Status.API_ERROR,
        Status.TIMEOUT,
        Status.EXCEPTION,
    ):
        result = RecognizeResult(text="", status=status)
        assert result.is_system_failure is True, status
        assert result.is_blank is False, status


def test_low_confidence_is_not_system_failure() -> None:
    result = RecognizeResult(text="A", status=Status.LOW_CONFIDENCE, confidence=0.5)
    assert result.is_system_failure is False
    assert result.is_blank is False


def test_to_legacy_text_returns_text() -> None:
    result = RecognizeResult(text="hello", status=Status.OK)
    assert result.to_legacy_text() == "hello"


def test_confidence_optional() -> None:
    assert RecognizeResult().confidence is None
    assert RecognizeResult(confidence=None).confidence is None
    assert RecognizeResult(confidence=0.9).confidence == pytest.approx(0.9)


def test_error_carries_message() -> None:
    result = RecognizeResult(text="", status=Status.API_ERROR, error="HTTP 503")
    assert result.error == "HTTP 503"


def test_status_constants_are_strings() -> None:
    """Status 常量必须是普通 str（与下游 dataclass 字段类型兼容）。"""
    for value in (
        Status.OK,
        Status.BLANK,
        Status.ENGINE_MISSING,
        Status.API_ERROR,
        Status.TIMEOUT,
        Status.LOW_CONFIDENCE,
        Status.EXCEPTION,
    ):
        assert isinstance(value, str)


def test_system_failures_is_frozenset() -> None:
    """SYSTEM_FAILURES 应是不可变集合，避免下游意外修改。"""
    assert isinstance(Status.SYSTEM_FAILURES, frozenset)
    assert Status.ENGINE_MISSING in Status.SYSTEM_FAILURES
    assert Status.OK not in Status.SYSTEM_FAILURES
