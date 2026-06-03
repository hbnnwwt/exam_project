"""识别层统一数据结构。

`RecognizeResult` 把"识别是否成功"和"识别内容"分离：
- status 表示处理路径的结果分类
- text 表示识别到的内容（失败时通常为空串）
- error 在失败时携带可读错误信息
- confidence 可选，用于低置信度标注

status 取值约定：
- "ok"             — 识别成功且有内容
- "blank"          — 识别成功但学生没写（空 ROI / OCR 返回空）
- "engine_missing" — 本地 OCR 引擎未安装（ImportError / OSError）
- "api_error"      — 在线 OCR/LLM 接口调用失败（4xx/5xx、网络中断、限流等）
- "timeout"        — 接口调用超时
- "low_confidence" — 识别成功但置信度低（仅在明确能算出来时设置）
- "exception"      — 其他未分类异常

下游评分器和 UI 根据 status 决定如何处理：
- ok/blank/low_confidence → 走正常 LLM 评分
- engine_missing/api_error/timeout/exception → 不浪费 LLM 调用，直接报告"系统失败"
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# 用普通字符串而不是 typing.Literal，避免 dataclass 字段类型兼容性坑
RecognizeStatus = str


class Status:
    """识别状态常量。集中在此避免散落的 magic string。"""

    OK = "ok"
    BLANK = "blank"
    ENGINE_MISSING = "engine_missing"
    API_ERROR = "api_error"
    TIMEOUT = "timeout"
    LOW_CONFIDENCE = "low_confidence"
    EXCEPTION = "exception"

    SYSTEM_FAILURES = frozenset({ENGINE_MISSING, API_ERROR, TIMEOUT, EXCEPTION})


@dataclass
class RecognizeResult:
    """单次识别调用的结构化结果。"""

    text: str = ""
    status: RecognizeStatus = Status.BLANK
    error: Optional[str] = None
    confidence: Optional[float] = None

    @property
    def is_system_failure(self) -> bool:
        """是否系统侧失败（与学生未作答区分）。"""
        return self.status in Status.SYSTEM_FAILURES

    @property
    def is_blank(self) -> bool:
        """是否学生未作答（OCR 成功但内容为空）。

        系统失败（engine_missing/api_error/timeout/exception）不算空白——
        那是我们这边的故障，不是学生没写。
        """
        if self.is_system_failure:
            return False
        return self.status == Status.BLANK or not (self.text and self.text.strip())

    def to_legacy_text(self) -> str:
        """兼容旧接口：仅返回 text 字段（下游若只看字符串）。"""
        return self.text
