"""通过 LLM API 对简答题进行语义评分。

调用 ModelScope OpenAI 兼容格式的 API。容忍 OCR 识别偏差，按语义匹配。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

from exam_project.grading.defaults import DEFAULT_BASE_URL, DEFAULT_LLM_MODEL
from exam_project.grading.grading import EssayGraderBase
from exam_project.recognition.types import RecognizeResult, Status


# 默认 prompt 模板
DEFAULT_PROMPT = (
    "你是一个阅卷助手。请根据参考答案评估学生答案。\n\n"
    "注意事项：\n"
    "- 学生答案是通过 OCR 从手写文字识别的，可能存在识别错误（形近字、同音字）\n"
    "- 请根据语义判断，容忍合理的 OCR 识别偏差\n"
    "- 如果答案明显不确定或 OCR 识别质量差，请在反馈中说明\n\n"
    "参考答案：{reference}\n"
    "学生答案：{student_answer}\n"
    "满分：{max_score}分\n\n"
    "请严格按以下格式返回（不要输出其他内容）：\n"
    "得分：X\n"
    "反馈：一句话评语"
)

DEFAULT_PROMPT_PATH = "config/llm_grading_prompt.txt"
DEFAULT_TIMEOUT = 120
DEFAULT_MAX_TOKENS = 256
DEFAULT_TEMPERATURE = 0.3


# 分数解析正则（按优先级顺序）
SCORE_PATTERNS = [
    re.compile(r"得分[：:\s]+(\d+(?:\.\d+)?)"),
    re.compile(r"[Ss]core[：:\s]+(\d+(?:\.\d+)?)"),
    re.compile(r"(\d+(?:\.\d+)?)\s*分"),
    re.compile(r"(\d+(?:\.\d+)?)\s*/\s*\d+"),
]

FEEDBACK_PATTERNS = [
    re.compile(r"反馈[：:\s]+(.+?)(?:\n|$)"),
    re.compile(r"[Ff]eedback[：:\s]+(.+?)(?:\n|$)"),
    re.compile(r"[Cc]omment[：:\s]+(.+?)(?:\n|$)"),
]


@dataclass(frozen=True)
class LLMScore:
    """LLM 评分结果。"""

    score: float
    max_score: float
    feedback: str


@dataclass(frozen=True)
class LLMConfig:
    """LLM API 配置。"""

    api_keys: tuple[str, ...] = ()
    base_urls: tuple[str, ...] = ()
    models: tuple[str, ...] = ()
    max_tokens: int = DEFAULT_MAX_TOKENS
    temperature: float = DEFAULT_TEMPERATURE
    timeout_seconds: int = DEFAULT_TIMEOUT
    prompt_template: str = DEFAULT_PROMPT

    def build_configs(self) -> list[dict]:
        """生成所有 (key, url, model) 配置笛卡尔积。"""
        configs: list[dict] = []
        for key in self.api_keys:
            for url in self.base_urls:
                for model in self.models:
                    configs.append({
                        "api_key": key, "base_url": url, "model": model,
                    })
        return configs


def load_config(config_path: str | Path) -> dict:
    """加载 LLM 配置文件，不存在时返回默认值。"""
    path = Path(config_path)
    if not path.is_file():
        return {
            "api_key": "",
            "base_url": DEFAULT_BASE_URL,
            "llm_model": DEFAULT_LLM_MODEL,
        }
    return json.loads(path.read_text(encoding="utf-8"))


def save_config(config: dict, config_path: str | Path) -> None:
    """保存 LLM 配置（合并写，不覆盖已有键）。"""
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_config(path)
    existing.update(config)
    path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_prompt_template(prompt_path: str | Path) -> str:
    """加载 prompt 模板，缺失时返回默认。"""
    path = Path(prompt_path)
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return DEFAULT_PROMPT


class LLMEssayGrader(EssayGraderBase):
    """通过 LLM API 对简答题评分。"""

    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        api_key: Optional[Union[str, list[str]]] = None,
        base_url: Optional[Union[str, list[str]]] = None,
        model: Optional[Union[str, list[str]]] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        prompt_path: Optional[str | Path] = None,
    ) -> None:
        if config is not None:
            self.config = config
        else:
            # 兼容旧构造签名
            self.config = LLMConfig(
                api_keys=_to_tuple(api_key),
                base_urls=_to_tuple(base_url) or (DEFAULT_BASE_URL,),
                models=_to_tuple(model) or (DEFAULT_LLM_MODEL,),
                max_tokens=max_tokens,
                temperature=temperature,
                prompt_template=(
                    load_prompt_template(prompt_path)
                    if prompt_path else DEFAULT_PROMPT
                ),
            )

    @classmethod
    def from_config(
        cls,
        config_path: str | Path,
        prompt_path: Optional[str | Path] = None,
    ) -> "LLMEssayGrader":
        """从配置文件构造。"""
        cfg = load_config(config_path)
        return cls(
            api_key=cfg.get("api_key", ""),
            base_url=cfg.get("base_url", DEFAULT_BASE_URL),
            model=cfg.get("llm_model", DEFAULT_LLM_MODEL),
            prompt_path=prompt_path,
        )

    def _build_prompt(
        self,
        question: int,
        reference: str,
        student_answer: str,
        max_score: float,
    ) -> str:
        return self.config.prompt_template.format(
            reference=reference, student_answer=student_answer, max_score=max_score,
        )

    def _call_api(self, messages: list[dict], cfg: dict) -> str:
        """调用 ModelScope OpenAI 兼容格式 API。"""
        import requests
        url = f"{cfg['base_url'].rstrip('/')}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json",
        }
        data = {
            "model": cfg["model"],
            "messages": messages,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
        }
        try:
            resp = requests.post(
                url, headers=headers, json=data,
                timeout=self.config.timeout_seconds,
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as exc:
            err_str = str(exc)
            if any(tag in err_str for tag in ("10053", "10054", "Connection aborted")):
                raise RuntimeError(
                    "网络连接被本地软件终止（错误 10053/10054）。"
                    "可能原因：Windows 防火墙/杀毒软件拦截、代理/VPN 冲突、"
                    "或网络不稳定。请检查："
                    "1) 防火墙是否放行 Python；"
                    "2) 是否开启了代理/VPN；"
                    "3) 网络连接是否正常。"
                ) from exc
            raise RuntimeError(
                f"网络连接失败: {exc}。请检查网络连接和 API 地址是否正确。"
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise RuntimeError(
                f"请求超时（{self.config.timeout_seconds}秒）。请检查网络连接或稍后重试。"
            ) from exc

        result = resp.json()
        error_info = result.get("error")
        if error_info:
            err_msg = (
                error_info.get("message", str(error_info))
                if isinstance(error_info, dict)
                else str(error_info)
            )
            raise RuntimeError(
                f"LLM API 错误: {err_msg}，"
                f"原始响应: {json.dumps(result, ensure_ascii=False)[:500]}"
            )

        choices = result.get("choices") or []
        if choices:
            content = choices[0].get("message", {}).get("content", "")
            if content:
                return content
            raise RuntimeError(
                f"LLM 返回空 content，"
                f"原始响应: {json.dumps(result, ensure_ascii=False)[:500]}"
            )
        usage = result.get("usage", {})
        if usage.get("prompt_tokens", 0) == 0 and usage.get("completion_tokens", 0) == 0:
            model_id = cfg.get("model", "未知")
            raise RuntimeError(
                f"LLM 返回无 choices（请求未实际执行）。"
                f"可能原因：模型名称 '{model_id}' 不被支持、"
                f"API Key 无效或服务端内部错误。"
                f"原始响应: {json.dumps(result, ensure_ascii=False)[:500]}"
            )
        raise RuntimeError(
            f"LLM 返回无 choices，"
            f"原始响应: {json.dumps(result, ensure_ascii=False)[:500]}"
        )

    def _parse_response(self, text: str, max_score: float) -> LLMScore:
        """从 LLM 返回文本中提取分数和反馈。"""
        if not text or not text.strip():
            return LLMScore(0.0, max_score, "LLM 返回为空")

        t = text.strip()

        # 1. 尝试解析 JSON
        try:
            data = json.loads(t)
            if isinstance(data, dict):
                score = data.get("score") or data.get("得分")
                feedback = (
                    data.get("feedback") or data.get("反馈")
                    or data.get("comment") or ""
                )
                if score is not None:
                    return LLMScore(
                        min(int(float(score)), max_score),
                        max_score,
                        str(feedback).strip() or "LLM 评分完成",
                    )
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

        # 2. 正则匹配分数
        score_match = None
        for pattern in SCORE_PATTERNS:
            score_match = pattern.search(t)
            if score_match:
                break
        # 3. 兜底：在合理范围内的第一个数字
        if not score_match:
            for num_str in re.findall(r"\b(\d+(?:\.\d+)?)\b", t):
                num = float(num_str)
                if 0 <= num <= max_score:
                    score_match = re.search(re.escape(num_str), t)
                    break

        if not score_match:
            return LLMScore(0.0, max_score, f"LLM 返回无法解析，原始内容：{t[:200]}")

        score = min(int(float(score_match.group(1))), max_score)

        # 反馈
        feedback_match = None
        for pattern in FEEDBACK_PATTERNS:
            feedback_match = pattern.search(t)
            if feedback_match:
                break
        if feedback_match:
            feedback = feedback_match.group(1).strip()
        else:
            lines = [ln.strip() for ln in t.split("\n") if ln.strip()]
            feedback_lines = [
                ln for ln in lines
                if not re.search(r"得分[：:\s]+\d+", ln)
                and not re.search(r"[Ss]core[：:\s]+\d+", ln)
            ]
            feedback = " ".join(feedback_lines) if feedback_lines else "LLM 评分完成"

        return LLMScore(float(score), max_score, feedback)

    def score(
        self,
        question: int,
        reference: str,
        student_answer: Union[str, RecognizeResult],
        max_score: float,
    ) -> tuple[float, float, str]:
        if not isinstance(student_answer, RecognizeResult):
            student_answer = RecognizeResult(
                text=student_answer or "",
                status=Status.BLANK if not (student_answer and str(student_answer).strip()) else Status.OK,
            )
        if student_answer.is_system_failure:
            return (0.0, max_score,
                    f"系统失败: {student_answer.error or student_answer.status}")
        if not (student_answer.text and student_answer.text.strip()):
            return 0.0, max_score, "未作答"

        confidence_prefix = "[低置信度] " if student_answer.status == Status.LOW_CONFIDENCE else ""
        prompt = self._build_prompt(
            question, reference, student_answer.text, max_score,
        )
        messages = [{"role": "user", "content": prompt}]

        configs = self.config.build_configs()
        if not configs:
            return 0.0, max_score, "LLM 未配置：缺少 api_key / base_url / model"

        last_err: Optional[Exception] = None
        for i, cfg in enumerate(configs):
            try:
                text = self._call_api(messages, cfg)
                result = self._parse_response(text, max_score)
                return (
                    result.score, max_score,
                    confidence_prefix + result.feedback,
                )
            except Exception as exc:
                last_err = exc
                is_429 = _is_rate_limited(exc)
                if is_429 and i < len(configs) - 1:
                    import time
                    time.sleep(min(2 * (i + 1), 30))

        return 0.0, max_score, confidence_prefix + (
            f"LLM 调用失败: {last_err}" if last_err else "LLM 调用失败"
        )


# ============================================================================
# helpers
# ============================================================================


def _to_tuple(value) -> tuple:
    """接受 str / list / tuple / None，统一为 tuple。"""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    return tuple(value)


def _is_rate_limited(exc: Exception) -> bool:
    """判断异常是否由 429 限流引起。"""
    if hasattr(exc, "response") and getattr(exc, "response", None) is not None:
        if getattr(exc.response, "status_code", None) == 429:
            return True
    return "429" in str(exc)
