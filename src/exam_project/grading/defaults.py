"""模型配置默认值。

集中管理 LLM/OCR API 的默认 base URL、模型名、token 上限等。
供 config_validator 补全缺失字段使用。
"""

from __future__ import annotations

from typing import Any


DEFAULT_BASE_URL = "https://api-inference.modelscope.cn"
DEFAULT_LLM_MODEL = "Qwen/Qwen3-235B-A22B"
DEFAULT_OCR_MODEL = "Qwen/Qwen3-VL-235B-A22B-Instruct"
DEFAULT_LLM_MAX_TOKENS = 256
DEFAULT_LLM_TEMPERATURE = 0.3


def model_config_defaults() -> dict[str, Any]:
    """返回一份独立的 defaults 字典副本，避免调用方意外修改常量。"""
    return {
        "base_url": DEFAULT_BASE_URL,
        "llm_model": DEFAULT_LLM_MODEL,
        "ocr_model": DEFAULT_OCR_MODEL,
        "llm_max_tokens": DEFAULT_LLM_MAX_TOKENS,
        "llm_temperature": DEFAULT_LLM_TEMPERATURE,
    }
