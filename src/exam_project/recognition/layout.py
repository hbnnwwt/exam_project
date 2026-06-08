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

from exam_project.answer_sheet.layout_engine import PAGE_SIZES, page_content_height

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
    page_fallbacks: dict[int, dict[str, tuple[float, float]]] = field(
        default_factory=dict
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
            page_fallbacks=_normalize_page_fallbacks(layout_block),
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
        normalized = _normalize_ratio_pair(raw.get(key))
        result[key] = normalized if normalized is not None else default
    return result


def _normalize_page_fallbacks(
    layout_block: object,
) -> dict[int, dict[str, tuple[float, float]]]:
    if not isinstance(layout_block, dict):
        return {}

    result: dict[int, dict[str, tuple[float, float]]] = {}
    for key, raw in layout_block.items():
        page_number = _page_number_from_fallback_key(key)
        if page_number is None or not isinstance(raw, dict):
            continue

        page_fallback: dict[str, tuple[float, float]] = {}
        for section, value in raw.items():
            normalized = _normalize_ratio_pair(value)
            if normalized is not None:
                page_fallback[str(section)] = normalized
        if page_fallback:
            result[page_number] = page_fallback
    return result


def _page_number_from_fallback_key(key: object) -> Optional[int]:
    if not isinstance(key, str):
        return None
    if not key.startswith("page") or not key.endswith("_fallback"):
        return None
    raw_number = key[4:-9]
    if not raw_number.isdigit():
        return None
    page_number = int(raw_number)
    return page_number if page_number > 0 else None


def _normalize_ratio_pair(value: object) -> Optional[tuple[float, float]]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        return (float(value[0]), float(value[1]))
    except (TypeError, ValueError):
        return None


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
        fallback_regions = self.fallback_regions_from_spec(page_spec, h, w, boxes)
        unused_boxes = list(boxes)

        for section in expected:
            region = fallback_regions.get(section)
            matched = None
            if region is not None and unused_boxes:
                matched = self._best_overlapping_box(region, unused_boxes)
            elif unused_boxes:
                matched = unused_boxes[0]

            if matched is not None:
                kwargs[section] = matched
                unused_boxes.remove(matched)
            elif region is not None:
                kwargs[section] = region
        return PageRegions(**kwargs)

    def fallback_regions_from_spec(
        self,
        page_spec: object,
        h: int,
        w: int,
        boxes: list[tuple[int, int, int, int]] | tuple[tuple[int, int, int, int], ...] = (),
    ) -> dict[str, tuple[int, int, int, int]]:
        expected = self._section_types_from_spec(page_spec)
        page_number = self._page_number_from_spec(page_spec)
        fallback_map = {
            **self._config.page1_fallback,
            **self._config.page2_fallback,
        }
        page_fallback = self._config.page_fallbacks.get(page_number, {})
        ratios: dict[str, tuple[float, float]] = {}
        for section in expected:
            ratio = page_fallback.get(section)
            if ratio is None:
                ratio = fallback_map.get(section)
            if ratio is not None:
                ratios[section] = ratio
        if not ratios:
            return {}

        rough_regions = {
            section: self._fallback_region(h, w, ratio)
            for section, ratio in ratios.items()
        }
        matched: list[tuple[tuple[int, int, int, int], tuple[float, float]]] = []
        for box in boxes:
            section = self._best_overlapping_section(box, rough_regions)
            if section is not None:
                matched.append((box, ratios[section]))

        content_top, content_height = self._content_axis(
            h, page_number, matched
        )
        return {
            section: self._content_fallback_region(
                w, h, content_top, content_height, ratio
            )
            for section, ratio in ratios.items()
        }

    @staticmethod
    def _section_types_from_spec(page_spec: object) -> list[str]:
        if isinstance(page_spec, dict):
            sections = page_spec.get("sections", [])
            return [
                sec.get("type")
                for sec in sections
                if isinstance(sec, dict) and sec.get("type")
            ]
        if isinstance(page_spec, list):
            return list(page_spec)
        return []

    @staticmethod
    def _page_number_from_spec(page_spec: object) -> int:
        if isinstance(page_spec, dict):
            try:
                return int(page_spec.get("page_number", 1))
            except (TypeError, ValueError):
                return 1
        return 1

    @staticmethod
    def _content_axis(
        image_height: int,
        page_number: int,
        matched: list[tuple[tuple[int, int, int, int], tuple[float, float]]],
        paper_size: str = "A4",
    ) -> tuple[int, int]:
        estimates: list[tuple[float, float]] = []
        for box, ratio in matched:
            start, end = ratio
            span = end - start
            if span <= 0:
                continue
            _, y, _, box_h = box
            content_h = box_h / span
            content_top = y - start * content_h
            if content_h > 0:
                estimates.append((content_top, content_h))

        if estimates:
            top = sum(item[0] for item in estimates) / len(estimates)
            height = sum(item[1] for item in estimates) / len(estimates)
            top = max(0.0, min(float(image_height - 1), top))
            height = max(1.0, min(float(image_height - top), height))
            return int(top), int(height)

        page_mm = PAGE_SIZES.get(paper_size, PAGE_SIZES["A4"])["height"]
        content_mm = page_content_height(paper_size, page_number)
        content_h = image_height * content_mm / page_mm
        content_top = (image_height - content_h) / 2
        return int(content_top), int(content_h)

    @staticmethod
    def _content_fallback_region(
        w: int,
        image_height: int,
        content_top: int,
        content_height: int,
        ratio_range: tuple[float, float],
    ) -> tuple[int, int, int, int]:
        start, end = ratio_range
        y1 = int(content_top + content_height * start)
        y2 = int(content_top + content_height * end)
        top_padding = max(2, int(content_height * 0.006))
        bottom_padding = max(2, int(content_height * 0.003))
        y = max(0, y1 - top_padding)
        bottom = min(image_height, y2 + bottom_padding)
        return (0, y, w, max(1, bottom - y))

    @staticmethod
    def _best_overlapping_section(
        box: tuple[int, int, int, int],
        regions: dict[str, tuple[int, int, int, int]],
    ) -> Optional[str]:
        best_section = None
        best_ratio = 0.0
        for section, region in regions.items():
            overlap = LayoutAnalyzer._intersection_area(region, box)
            ratio = overlap / max(box[2] * box[3], 1)
            if ratio > best_ratio:
                best_section = section
                best_ratio = ratio
        if best_ratio < 0.20:
            return None
        return best_section

    @staticmethod
    def _best_overlapping_box(
        region: tuple[int, int, int, int],
        boxes: list[tuple[int, int, int, int]],
    ) -> Optional[tuple[int, int, int, int]]:
        best_box = None
        best_ratio = 0.0
        for box in boxes:
            overlap = LayoutAnalyzer._intersection_area(region, box)
            ratio = overlap / max(box[2] * box[3], 1)
            if ratio > best_ratio:
                best_box = box
                best_ratio = ratio
        if best_ratio < 0.20:
            return None
        return best_box

    @staticmethod
    def _intersection_area(
        a: tuple[int, int, int, int],
        b: tuple[int, int, int, int],
    ) -> int:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        x0 = max(ax, bx)
        y0 = max(ay, by)
        x1 = min(ax + aw, bx + bw)
        y1 = min(ay + ah, by + bh)
        if x1 <= x0 or y1 <= y0:
            return 0
        return (x1 - x0) * (y1 - y0)

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
            if aspect < 0.3 or aspect > 8.0:
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
