"""答题卡版面分析。

从二值图中定位各题型区域（学号/选择题/判断题/简答题）。
答题卡的每个区域有可见矩形边框，通过形态学闭运算合并边框与内部内容
为一个连通区域，再用轮廓检测定位。

设计要点：
- LayoutConfig 显式注入；不再有 import-time 全局 LAYOUT
- LayoutAnalyzer 不在实例上保存中间图像（debug 信息放回 AnalyzeResult）
- 失败回退到固定比例的逻辑封装在 _fallback_region
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from .preprocess import ImagePreprocessor


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LayoutConfig:
    """版面分析配置。

    Attributes:
        page1_fallback: 第1页各区域（按 y 比例 [start, end]）
        page2_fallback: 第2页各区域
        pages: 多页配置。None 表示用 2 页固定结构。
        min_area_ratio: 候选框最小面积占图比例
        max_area_ratio: 候选框最大面积占图比例
        kernel_ratio: 闭运算核宽占图比例
    """

    page1_fallback: dict[str, tuple[float, float]] = field(
        default_factory=lambda: {
            "student_id": (0.06, 0.26),
            "choice": (0.28, 0.80),
        }
    )
    page2_fallback: dict[str, tuple[float, float]] = field(
        default_factory=lambda: {
            "judge": (0.06, 0.46),
            "essay": (0.50, 0.90),
        }
    )
    pages: Optional[list[dict]] = None
    min_area_ratio: float = 0.03
    max_area_ratio: float = 0.92
    kernel_ratio: float = 0.02

    @classmethod
    def from_dict(cls, data: dict) -> "LayoutConfig":
        """从 JSON 字典构造，未提供字段使用默认值。"""
        layout_block = data.get("layout", {}) if isinstance(data, dict) else {}
        return cls(
            page1_fallback=_normalize_fallback(layout_block.get("page1_fallback"), {
                "student_id": (0.06, 0.26),
                "choice": (0.28, 0.80),
            }),
            page2_fallback=_normalize_fallback(layout_block.get("page2_fallback"), {
                "judge": (0.06, 0.46),
                "essay": (0.50, 0.90),
            }),
            pages=data.get("_pages") if isinstance(data, dict) else None,
        )


def _normalize_fallback(
    raw: object,
    defaults: dict[str, tuple[float, float]],
) -> dict[str, tuple[float, float]]:
    if not isinstance(raw, dict):
        return dict(defaults)
    result: dict[str, tuple[float, float]] = {}
    for key, default in defaults.items():
        value = raw.get(key)
        if isinstance(value, (list, tuple)) and len(value) == 2:
            try:
                result[key] = (float(value[0]), float(value[1]))
            except (TypeError, ValueError):
                result[key] = default
        else:
            result[key] = default
    return result


# ---------------------------------------------------------------------------
# 结果
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PageRegions:
    """单页版面区域。

    每个属性是 (x, y, w, h)，未检测到时为 None。
    """

    student_id: Optional[tuple[int, int, int, int]] = None
    choice: Optional[tuple[int, int, int, int]] = None
    judge: Optional[tuple[int, int, int, int]] = None
    essay: Optional[tuple[int, int, int, int]] = None
    image_size: tuple[int, int] = (0, 0)
    boxes: tuple[tuple[int, int, int, int], ...] = ()

    def to_dict(self) -> dict:
        return {
            "student_id": self.student_id,
            "choice": self.choice,
            "judge": self.judge,
            "essay": self.essay,
            "image_size": self.image_size,
            "boxes": list(self.boxes),
        }


# ---------------------------------------------------------------------------
# 分析器
# ---------------------------------------------------------------------------


class LayoutAnalyzer:
    """答题卡版面分析器。

    不在实例上保存状态——单次分析的所有产物（debug 图像等）随结果返回。
    """

    def __init__(self, config: Optional[LayoutConfig] = None) -> None:
        self._config = config or LayoutConfig()

    @property
    def config(self) -> LayoutConfig:
        return self._config

    # ----------------------------------------------------- public api

    def analyze(
        self,
        image: np.ndarray,
        binary: np.ndarray,
        page: int = 1,
    ) -> PageRegions:
        """分析单页答题卡区域。

        Args:
            image: BGR 原图
            binary: 二值化图
            page: 1 = 第1页（学号+选择题），2 = 第2页（判断题+简答题）

        Returns:
            PageRegions，每页四个题型区域的 (x, y, w, h) 或 None
        """
        h, w = image.shape[:2]
        gray_enhanced = self._maybe_enhance(image, page)
        boxes, _, _ = self._detect_regions(binary, gray_enhanced)

        if page == 1:
            return self._page1_regions(boxes, h, w)
        return self._page2_regions(boxes, h, w)

    def analyze_multipage(
        self,
        images: list[np.ndarray],
        binaries: list[np.ndarray],
    ) -> list[PageRegions]:
        """多页答题卡版面分析。

        当 config.pages 存在时按其声明的 section 顺序匹配；否则回退到
        旧的 2 页固定结构（每页 analyze()）。
        """
        if len(images) != len(binaries):
            raise ValueError("images 和 binaries 数量必须一致")
        if not images:
            return []

        if self._config.pages is None:
            return [
                self.analyze(img, binary, page=idx + 1)
                for idx, (img, binary) in enumerate(zip(images, binaries))
            ]

        results: list[PageRegions] = []
        for page_idx, (img, binary) in enumerate(zip(images, binaries)):
            h, w = img.shape[:2]
            gray_enhanced = self._maybe_enhance(img, page=2)
            boxes, _, _ = self._detect_regions(binary, gray_enhanced)
            page_spec = (
                self._config.pages[page_idx]
                if page_idx < len(self._config.pages)
                else []
            )
            results.append(self._regions_from_spec(boxes, page_spec, h, w))
        return results

    # ----------------------------------------------------- internals

    def _page1_regions(
        self,
        boxes: list[tuple[int, int, int, int]],
        h: int,
        w: int,
    ) -> PageRegions:
        if len(boxes) >= 2:
            return PageRegions(
                student_id=boxes[0],
                choice=boxes[1],
                image_size=(w, h),
                boxes=tuple(boxes),
            )
        return PageRegions(
            student_id=self._fallback_region(h, w, self._config.page1_fallback["student_id"]),
            choice=self._fallback_region(h, w, self._config.page1_fallback["choice"]),
            image_size=(w, h),
            boxes=tuple(boxes),
        )

    def _page2_regions(
        self,
        boxes: list[tuple[int, int, int, int]],
        h: int,
        w: int,
    ) -> PageRegions:
        if len(boxes) >= 2:
            return PageRegions(
                judge=boxes[0],
                essay=boxes[1],
                image_size=(w, h),
                boxes=tuple(boxes),
            )
        return PageRegions(
            judge=self._fallback_region(h, w, self._config.page2_fallback["judge"]),
            essay=self._fallback_region(h, w, self._config.page2_fallback["essay"]),
            image_size=(w, h),
            boxes=tuple(boxes),
        )

    def _regions_from_spec(
        self,
        boxes: list[tuple[int, int, int, int]],
        page_spec: object,
        h: int,
        w: int,
    ) -> PageRegions:
        if isinstance(page_spec, dict):
            sections = page_spec.get("sections", [])
            expected = [
                sec.get("type")
                for sec in sections
                if isinstance(sec, dict) and sec.get("type")
            ]
        elif isinstance(page_spec, list):
            expected = list(page_spec)
        else:
            expected = []

        kwargs: dict = {"image_size": (w, h), "boxes": tuple(boxes)}
        for sec_idx, section in enumerate(expected):
            if sec_idx < len(boxes):
                kwargs[section] = boxes[sec_idx]
            else:
                fallback_map = {
                    **self._config.page1_fallback,
                    **self._config.page2_fallback,
                }
                ratio = fallback_map.get(section)
                if ratio is not None:
                    kwargs[section] = self._fallback_region(h, w, ratio)
        return PageRegions(**kwargs)

    def _detect_regions(
        self,
        binary: np.ndarray,
        gray_enhanced: Optional[np.ndarray],
    ) -> tuple[list[tuple[int, int, int, int]], np.ndarray, list]:
        """返回 (boxes, combined, contours)。"""
        h, w = binary.shape
        total_area = h * w
        inv = 255 - binary

        # 自适应核比例：从小到大尝试，最后回退到不做闭运算
        ratios = [0.005, 0.010, self._config.kernel_ratio, 0.0]
        for ratio in ratios:
            closed = self._apply_morphology(inv, h, ratio)
            combined = self._combine_with_edges(closed, gray_enhanced)
            contours, _ = cv2.findContours(
                combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            boxes = self._filter_boxes(contours, total_area)
            if len(boxes) >= 2:
                boxes.sort(key=lambda b: b[2] * b[3], reverse=True)
                boxes = boxes[:2]
                boxes.sort(key=lambda b: b[1])
                return boxes, combined, contours

        # 最终回退：取最大 2 个（哪怕不够 2 个也返回）
        combined = self._combine_with_edges(inv, gray_enhanced)
        contours, _ = cv2.findContours(
            combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        boxes = self._filter_boxes(contours, total_area)
        boxes.sort(key=lambda b: b[2] * b[3], reverse=True)
        boxes = boxes[:2]
        boxes.sort(key=lambda b: b[1])
        return boxes, combined, contours

    def _apply_morphology(self, inv: np.ndarray, h: int, ratio: float) -> np.ndarray:
        if ratio <= 0:
            return inv
        ksize_w = max(int(h * ratio), 3)
        ksize_h = max(ksize_w // 4, 3)
        if ksize_w % 2 == 0:
            ksize_w += 1
        if ksize_h % 2 == 0:
            ksize_h += 1
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (ksize_w, ksize_h))
        return cv2.morphologyEx(inv, cv2.MORPH_CLOSE, kernel)

    def _combine_with_edges(
        self,
        image: np.ndarray,
        gray_enhanced: Optional[np.ndarray],
    ) -> np.ndarray:
        if gray_enhanced is None:
            return image
        sobel_v = ImagePreprocessor.extract_vertical_edges(gray_enhanced)
        sobel_h = ImagePreprocessor.extract_horizontal_edges(gray_enhanced)
        combined = cv2.bitwise_or(image, sobel_v)
        return cv2.bitwise_or(combined, sobel_h)

    def _filter_boxes(
        self,
        contours: tuple,
        total_area: int,
    ) -> list[tuple[int, int, int, int]]:
        min_area = total_area * self._config.min_area_ratio
        max_area = total_area * self._config.max_area_ratio
        boxes: list[tuple[int, int, int, int]] = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < min_area or area > max_area:
                continue
            x, y, bw, bh = cv2.boundingRect(c)
            aspect = bw / max(bh, 1)
            if aspect < 0.3 or aspect > 5.0:
                continue
            boxes.append((x, y, bw, bh))
        return boxes

    @staticmethod
    def _fallback_region(
        h: int,
        w: int,
        ratio_range: tuple[float, float],
    ) -> tuple[int, int, int, int]:
        start, end = ratio_range
        return (0, int(h * start), w, int(h * (end - start)))

    @staticmethod
    def _maybe_enhance(image: np.ndarray, page: int) -> Optional[np.ndarray]:
        """第 2 页和 multipage 模式启用 CLAHE 增强以辅助 Sobel 边线提取。"""
        if page != 2:
            return None
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(gray)
