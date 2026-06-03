"""简答题识别器测试。

OCR 引擎调用本身不在单测范围（需装 paddleocr/torch 等重依赖）。
此处覆盖：构造校验、引擎可用性、ApiConfig 解析、错误传播。
"""

from __future__ import annotations

import numpy as np
import pytest

from exam_project.recognition.essay import (
    ApiConfig,
    EssayRecognizer,
    SUPPORTED_ENGINES,
    check_engine_available,
)
from exam_project.recognition.types import Status


# ---------------------------------------------------------------------------
# 构造
# ---------------------------------------------------------------------------


def test_default_engine_paddleocr() -> None:
    rec = EssayRecognizer()
    assert rec.engine == "paddleocr"


def test_invalid_engine_raises() -> None:
    with pytest.raises(ValueError, match="不支持的 OCR 引擎"):
        EssayRecognizer(engine="bogus")


@pytest.mark.parametrize("engine", SUPPORTED_ENGINES)
def test_all_supported_engines_accepted(engine: str) -> None:
    EssayRecognizer(engine=engine)


def test_default_api_config() -> None:
    rec = EssayRecognizer()
    assert rec.api_config.api_keys == ()
    assert rec.api_config.base_url  # 非空


# ---------------------------------------------------------------------------
# ApiConfig
# ---------------------------------------------------------------------------


def test_apiconfig_from_dict_handles_string_key() -> None:
    cfg = ApiConfig.from_dict({"api_key": "k1"})
    assert cfg.api_keys == ("k1",)


def test_apiconfig_from_dict_handles_list_keys() -> None:
    cfg = ApiConfig.from_dict({"api_keys": ["k1", "k2"]})
    assert cfg.api_keys == ("k1", "k2")


def test_apiconfig_from_dict_handles_ocr_api_key() -> None:
    cfg = ApiConfig.from_dict({"ocr_api_key": "ocr-only"})
    assert cfg.api_keys == ("ocr-only",)


def test_apiconfig_from_dict_merges_multiple_fields() -> None:
    """多个 key 字段应当合并去重。"""
    cfg = ApiConfig.from_dict({
        "api_key": "primary",
        "api_keys": ["primary", "backup"],  # 重复
        "ocr_api_key": "ocr",
    })
    # primary 出现两次应当去重
    assert "primary" in cfg.api_keys
    assert "ocr" in cfg.api_keys
    assert len([k for k in cfg.api_keys if k == "primary"]) == 1


def test_apiconfig_from_dict_strips_whitespace() -> None:
    cfg = ApiConfig.from_dict({"api_key": "  k1  "})
    assert cfg.api_keys == ("k1",)


def test_apiconfig_from_dict_filters_empty_strings() -> None:
    cfg = ApiConfig.from_dict({"api_keys": ["", "k1", "  ", "k2"]})
    assert cfg.api_keys == ("k1", "k2")


def test_apiconfig_from_dict_uses_default_prompt() -> None:
    cfg = ApiConfig.from_dict({})
    assert "识别" in cfg.ocr_prompt


def test_apiconfig_from_dict_uses_default_base_url() -> None:
    cfg = ApiConfig.from_dict({})
    assert cfg.base_url.startswith("http")


# ---------------------------------------------------------------------------
# check_engine_available
# ---------------------------------------------------------------------------


def test_check_engine_available_known() -> None:
    """已知引擎返回 bool（不要求 True 或 False，取决于环境）。"""
    for engine in ("paddleocr", "easyocr", "rapidocr", "online"):
        result = check_engine_available(engine)
        assert isinstance(result, bool)


def test_check_engine_available_unknown_returns_false() -> None:
    assert check_engine_available("nonexistent") is False


# ---------------------------------------------------------------------------
# recognize 错误传播
# ---------------------------------------------------------------------------


def test_recognize_unknown_engine_raises() -> None:
    """绕过构造校验直接 recognize 应被 _extract_local 拒绝。"""
    rec = EssayRecognizer(engine="paddleocr")
    rec.engine = "bogus"  # type: ignore[assignment]
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    result = rec.recognize(image)
    # 走 _extract_local 抛 ValueError → 兜底为 exception
    assert result.status == Status.EXCEPTION


def test_recognize_local_engine_missing() -> None:
    """paddleocr 未装时，recognize 应返回 engine_missing。"""
    rec = EssayRecognizer(engine="paddleocr")
    # 强制触发 import 失败
    import builtins
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "paddleocr":
            raise ImportError("simulated missing")
        return original_import(name, *args, **kwargs)

    builtins.__import__ = fake_import
    try:
        image = np.zeros((10, 10, 3), dtype=np.uint8)
        result = rec.recognize(image)
        assert result.status == Status.ENGINE_MISSING
    finally:
        builtins.__import__ = original_import


def test_recognize_online_without_api_key_returns_error() -> None:
    rec = EssayRecognizer(engine="online")
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    result = rec.recognize(image)
    assert result.status == Status.API_ERROR
    assert "API Key" in result.error


def test_recognize_online_cancelled() -> None:
    """cancel_check 返回 True 时应当返回 api_error（已取消）。"""
    rec = EssayRecognizer(
        engine="online",
        api_config={"api_key": "k1"},
        cancel_check=lambda: True,
    )
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    result = rec.recognize(image)
    assert result.status == Status.API_ERROR
    assert "取消" in result.error


# ---------------------------------------------------------------------------
# recognize 返回值形状
# ---------------------------------------------------------------------------


def test_recognize_result_has_required_fields() -> None:
    rec = EssayRecognizer(
        engine="online",
        api_config={"api_key": "k1"},
    )
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    result = rec.recognize(image)
    assert hasattr(result, "text")
    assert hasattr(result, "status")
    assert hasattr(result, "error")
    assert hasattr(result, "confidence")


# ---------------------------------------------------------------------------
# ApiConfig 不可变
# ---------------------------------------------------------------------------


def test_apiconfig_is_frozen() -> None:
    cfg = ApiConfig()
    with pytest.raises(Exception):
        cfg.base_url = "http://changed"  # type: ignore[misc]
