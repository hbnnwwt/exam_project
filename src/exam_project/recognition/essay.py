"""简答题文字识别器。

支持多引擎：paddleocr / easyocr / rapidocr / online(LLM vision)。
所有失败通过 RecognizeResult.status 表达，不向上抛异常。
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import importlib.util
from typing import Optional

import cv2
import numpy as np

from .constants import DEFAULT_BASE_URL, DEFAULT_OCR_MODEL
from .types import RecognizeResult, Status


SUPPORTED_ENGINES = ("paddleocr", "easyocr", "rapidocr", "online")


@dataclass(frozen=True)
class ApiConfig:
    """在线 OCR/LLM API 配置。"""

    api_keys: tuple[str, ...] = ()
    base_url: str = DEFAULT_BASE_URL
    ocr_model: str = DEFAULT_OCR_MODEL
    ocr_prompt: str = "请逐行识别图片中的所有文字内容，只输出文字，不要添加解释。"
    ocr_max_tokens: int = 1024
    timeout_seconds: int = 120

    @classmethod
    def from_dict(cls, data: dict) -> "ApiConfig":
        """从 dict 构造，统一 api_key/api_keys/ocr_api_key 三种字段。

        多个字段同时提供时，keys 保持首次出现顺序并去重。
        """
        seen: set[str] = set()
        keys: list[str] = []
        for field_name in ("api_key", "api_keys", "ocr_api_key"):
            value = data.get(field_name)
            if isinstance(value, str) and value.strip():
                k = value.strip()
                if k not in seen:
                    seen.add(k)
                    keys.append(k)
            elif isinstance(value, (list, tuple)):
                for k in value:
                    if k and str(k).strip():
                        stripped = str(k).strip()
                        if stripped not in seen:
                            seen.add(stripped)
                            keys.append(stripped)
        return cls(
            api_keys=tuple(keys),
            base_url=str(data.get("base_url", DEFAULT_BASE_URL)),
            ocr_model=str(data.get("ocr_model", data.get("model", DEFAULT_OCR_MODEL))),
            ocr_prompt=str(data.get(
                "ocr_prompt",
                "请逐行识别图片中的所有文字内容，只输出文字，不要添加解释。",
            )),
            ocr_max_tokens=int(data.get("ocr_max_tokens", 1024)),
            timeout_seconds=int(data.get("timeout_seconds", 120)),
        )


def check_engine_available(engine: str) -> bool:
    """检查 OCR 引擎是否已安装（不触发 import）。"""
    if engine == "paddleocr":
        return importlib.util.find_spec("paddleocr") is not None
    if engine == "easyocr":
        return importlib.util.find_spec("easyocr") is not None
    if engine == "rapidocr":
        return importlib.util.find_spec("rapidocr_onnxruntime") is not None
    if engine == "online":
        return importlib.util.find_spec("requests") is not None
    return False


class EssayRecognizer:
    """简答题文字识别器。

    每次 recognize() 调用都返回 RecognizeResult；失败不抛异常，
    由 status 字段告诉调用方原因。
    """

    def __init__(
        self,
        engine: str = "paddleocr",
        lang: str = "ch",
        api_config: Optional[ApiConfig | dict] = None,
        cancel_check: Optional[callable] = None,
        max_image_side: int = 2048,
    ) -> None:
        if engine not in SUPPORTED_ENGINES:
            raise ValueError(f"不支持的 OCR 引擎: {engine}")
        self.engine = engine
        self.lang = lang
        if isinstance(api_config, dict):
            self.api_config = ApiConfig.from_dict(api_config)
        elif api_config is None:
            self.api_config = ApiConfig()
        else:
            self.api_config = api_config
        self.cancel_check = cancel_check
        self.max_image_side = max_image_side
        self._engine_instance: object | None = None

    # ----------------------------------------------------- public

    def recognize(self, image: np.ndarray) -> RecognizeResult:
        try:
            if self.engine == "online":
                text = self._extract_online(image)
            else:
                text = self._extract_local(image)
        except _CancelledError:
            return RecognizeResult(text="", status=Status.API_ERROR, error="OCR 已取消")
        except (ImportError, ModuleNotFoundError, OSError) as exc:
            return RecognizeResult(
                text="", status=Status.ENGINE_MISSING,
                error=f"OCR 引擎未安装或 DLL 加载失败: {exc}",
            )
        except _TimeoutError as exc:
            return RecognizeResult(text="", status=Status.TIMEOUT, error=str(exc))
        except _ApiError as exc:
            return RecognizeResult(text="", status=Status.API_ERROR, error=str(exc))
        except Exception as exc:  # 兜底：未分类错误
            return RecognizeResult(
                text="", status=Status.EXCEPTION, error=f"未预期错误: {exc}",
            )

        if not text or not text.strip():
            return RecognizeResult(text=text or "", status=Status.BLANK)
        return RecognizeResult(text=text, status=Status.OK)

    # ----------------------------------------------------- engine dispatch

    def _extract_local(self, image: np.ndarray) -> str:
        if self.engine == "paddleocr":
            return self._extract_paddleocr(image)
        if self.engine == "easyocr":
            return self._extract_easyocr(image)
        if self.engine == "rapidocr":
            return self._extract_rapidocr(image)
        raise ValueError(f"未知的本地 OCR 引擎: {self.engine}")

    # ----------------------------------------------------- paddleocr

    def _extract_paddleocr(self, image: np.ndarray) -> str:
        paddleocr = importlib.import_module("paddleocr")
        version = int(paddleocr.__version__.split(".")[0])
        ocr = self._get_engine_instance(paddleocr, version)
        if version >= 3:
            return self._extract_paddleocr_v3(ocr, image)
        return self._extract_paddleocr_v2(ocr, image)

    def _build_paddleocr(self, paddleocr_module, version: int):
        if version >= 3:
            return paddleocr_module.PaddleOCR(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                lang=self.lang,
            )
        return paddleocr_module.PaddleOCR(
            use_angle_cls=True, lang=self.lang, show_log=False,
        )

    @staticmethod
    def _extract_paddleocr_v3(ocr, image: np.ndarray) -> str:
        results = ocr.predict(image)
        lines: list[tuple[float, str]] = []
        for res in results:
            data = res.json
            rec_texts = data.get("rec_texts", [])
            rec_polys = data.get("rec_polys", [])
            for i, text in enumerate(rec_texts):
                if i < len(rec_polys):
                    y_center = sum(p[1] for p in rec_polys[i]) / 4
                else:
                    y_center = float(i)
                lines.append((y_center, text))
        lines.sort(key=lambda t: t[0])
        return "".join(t for _, t in lines)

    @staticmethod
    def _extract_paddleocr_v2(ocr, image: np.ndarray) -> str:
        results = ocr.ocr(image, cls=True)
        if not results or not results[0]:
            return ""
        lines: list[tuple[float, str]] = []
        for line in results[0]:
            box = line[0]
            text = line[1][0]
            y_center = sum(p[1] for p in box) / 4
            lines.append((y_center, text))
        lines.sort(key=lambda t: t[0])
        return "".join(t for _, t in lines)

    # ----------------------------------------------------- easyocr

    def _extract_easyocr(self, image: np.ndarray) -> str:
        easyocr = importlib.import_module("easyocr")
        if self._engine_instance is None:
            self._engine_instance = easyocr.Reader(
                [self.lang.replace("ch", "ch_sim")]
            )
        reader = self._engine_instance
        results = reader.readtext(image)
        if not results:
            return ""
        lines: list[tuple[float, str]] = []
        for box, text, _ in results:
            y_center = sum(p[1] for p in box) / 4
            lines.append((y_center, text))
        lines.sort(key=lambda t: t[0])
        return "".join(t for _, t in lines)

    # ----------------------------------------------------- rapidocr

    def _extract_rapidocr(self, image: np.ndarray) -> str:
        if self._engine_instance is None:
            from rapidocr_onnxruntime import RapidOCR
            self._engine_instance = RapidOCR()
        result, _ = self._engine_instance(image)
        if not result:
            return ""
        lines: list[tuple[float, str]] = []
        for item in result:
            box = item[0]
            text = item[1]
            y_center = sum(p[1] for p in box) / 4
            lines.append((y_center, text))
        lines.sort(key=lambda t: t[0])
        return "".join(t for _, t in lines)

    # ----------------------------------------------------- online

    def _extract_online(self, image: np.ndarray) -> str:
        if not self.api_config.api_keys:
            raise _ApiError("在线 OCR 需要 API Key")

        if self.cancel_check and self.cancel_check():
            raise _CancelledError("OCR 已取消")

        # 缩放过大的图
        h, w = image.shape[:2]
        if max(h, w) > self.max_image_side:
            scale = self.max_image_side / max(h, w)
            image = cv2.resize(image, (int(w * scale), int(h * scale)))

        _, buf = cv2.imencode(".png", image)
        b64 = base64.b64encode(buf.tobytes()).decode("utf-8")
        data_url = f"data:image/png;base64,{b64}"

        url = f"{self.api_config.base_url.rstrip('/')}/v1/chat/completions"
        payload = {
            "model": self.api_config.ocr_model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": self.api_config.ocr_prompt},
                ],
            }],
            "max_tokens": self.api_config.ocr_max_tokens,
        }

        last_error: Optional[Exception] = None
        for i, api_key in enumerate(self.api_config.api_keys):
            try:
                text = self._call_online_once(url, payload, api_key)
                if text is not None:
                    return text
            except _RateLimitedError as exc:
                last_error = exc
                if i < len(self.api_config.api_keys) - 1:
                    import time
                    time.sleep(min(2 * (i + 1), 30))
                    continue
                raise
            except (Exception, _ApiError, _TimeoutError) as exc:
                last_error = exc
                continue

        if last_error is not None:
            raise last_error
        raise _ApiError("OCR 调用全部失败")

    def _call_online_once(
        self,
        url: str,
        payload: dict,
        api_key: str,
    ) -> Optional[str]:
        import requests
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(
                url, json=payload, headers=headers,
                timeout=self.api_config.timeout_seconds,
            )
        except requests.exceptions.ConnectionError as exc:
            raise _ApiError(self._format_connection_error(exc)) from exc
        except requests.exceptions.Timeout as exc:
            raise _TimeoutError(
                f"请求超时（{self.api_config.timeout_seconds}秒）。"
                "请检查网络连接或稍后重试。"
            ) from exc

        if not resp.ok:
            if resp.status_code == 429:
                raise _RateLimitedError("OCR API 限流（429），切换备用 Key…")
            raise _ApiError(f"OCR API {resp.status_code}: {resp.text[:500]}")

        data = resp.json()
        error_info = data.get("error")
        if error_info:
            err_msg = (
                error_info.get("message", str(error_info))
                if isinstance(error_info, dict)
                else str(error_info)
            )
            raise _ApiError(f"OCR API 错误: {err_msg}")

        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
            return content.strip()
        raise _ApiError("OCR 返回无 choices")

    @staticmethod
    def _format_connection_error(exc: Exception) -> str:
        msg = str(exc)
        if any(tag in msg for tag in ("10053", "10054", "Connection aborted")):
            return (
                "网络连接被本地软件终止（错误 10053/10054）。"
                "可能原因：Windows 防火墙/杀毒软件拦截、代理/VPN 冲突、"
                "或网络不稳定。请检查："
                "1) 防火墙是否放行 Python；"
                "2) 是否开启了代理/VPN；"
                "3) 网络连接是否正常。"
            )
        return f"网络连接失败: {exc}。请检查网络连接和 API 地址是否正确。"

    # ----------------------------------------------------- engine cache

    def _get_engine_instance(self, paddleocr_module, version: int):
        if self._engine_instance is None:
            self._engine_instance = self._build_paddleocr(paddleocr_module, version)
        return self._engine_instance


# ============================================================================
# 内部异常（不暴露给调用方）
# ============================================================================


class _CancelledError(Exception):
    """用户主动取消 OCR。"""


class _TimeoutError(Exception):
    """OCR 请求超时。"""


class _ApiError(Exception):
    """OCR API 错误（4xx/5xx/网络问题/参数错误）。"""


class _RateLimitedError(_ApiError):
    """429 限流，可尝试切换 Key。"""
