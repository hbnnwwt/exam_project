"""选择题/判断题识别器的共享基类。

抽取 ChoiceRecognizer 和 JudgeRecognizer 共同需要的方法：
- _trim_margin: 裁剪图像四周边距
- _analyze_zones: 按列统计填涂密度
- _detect_fill_start: 通过水平投影检测填涂起始行
- _refine_cell_boundaries: 精修行列边界
- recognize / recognize_with_viz: 主识别入口
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from .constants import FILL_BAND_THRESHOLD, MORPH_KERNEL


# 可视化颜色（BGR）
COLOR_SELECTED = (0, 200, 0)
COLOR_HALF = (0, 160, 255)
COLOR_LINE = (180, 180, 180)
COLOR_MULTI = (0, 255, 255)  # 多选警告


@dataclass(frozen=True)
class ZoneAnalysis:
    """_analyze_zones 的结构化结果。"""

    zone_fills: tuple[float, ...]
    best_idx: int
    above_threshold: bool
    is_multi: bool

    def as_dict(self) -> dict:
        return {
            "zone_fills": list(self.zone_fills),
            "best_idx": self.best_idx,
            "above_threshold": self.above_threshold,
            "is_multi": self.is_multi,
        }


class BubbleRecognizerBase:
    """气泡填涂识别器基类。子类负责解析 layout 中的具体配置。"""

    def __init__(
        self,
        threshold: float = 0.06,
        margin: int = 5,
        zone_count: int = 4,
        option_labels: Optional[list[str]] = None,
        multi_threshold: Optional[float] = None,
    ) -> None:
        if zone_count < 1:
            raise ValueError("zone_count 必须 >= 1")
        if margin < 0:
            raise ValueError("margin 必须 >= 0")
        self.threshold = threshold
        self.margin = margin
        self.zone_count = zone_count
        self.option_labels = option_labels or [
            chr(ord("A") + i) for i in range(zone_count)
        ]
        self.multi_threshold = multi_threshold

    # ----------------------------------------------------- utilities

    def _trim_margin(self, image: np.ndarray) -> np.ndarray:
        m = self.margin
        if m <= 0:
            return image
        h, w = image.shape[:2]
        if h <= 2 * m or w <= 2 * m:
            return image
        return image[m:-m, m:-m]

    def _to_gray(self, image: np.ndarray) -> np.ndarray:
        return image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # ----------------------------------------------------- zone analysis

    def _analyze_zones(self, image: np.ndarray) -> ZoneAnalysis:
        """按列统计填涂密度，输出 ZoneAnalysis。"""
        gray = self._to_gray(image)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, MORPH_KERNEL)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

        _, img_w = binary.shape
        zone_w = img_w / self.zone_count
        zone_fills: list[float] = []
        for z in range(self.zone_count):
            zx0 = int(z * zone_w)
            zx1 = int((z + 1) * zone_w)
            zone_pixels = binary[:, zx0:zx1]
            total = zone_pixels.size
            black = np.count_nonzero(zone_pixels)
            zone_fills.append(black / total if total > 0 else 0.0)

        best_idx = max(range(self.zone_count), key=lambda z: zone_fills[z])
        above = zone_fills[best_idx] >= self.threshold
        is_multi = False
        if self.multi_threshold is not None and above:
            confident = sum(1 for f in zone_fills if f >= self.multi_threshold)
            is_multi = confident >= 2
        return ZoneAnalysis(
            zone_fills=tuple(zone_fills),
            best_idx=best_idx,
            above_threshold=above,
            is_multi=is_multi,
        )

    # ----------------------------------------------------- fill band

    def _detect_fill_start(self, gray: np.ndarray) -> int:
        """通过水平投影频带检测填涂区域起始行。"""
        h, w = gray.shape
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, MORPH_KERNEL)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

        proj = np.sum(binary, axis=1).astype(np.float64) / (255.0 * w)
        bands: list[tuple[int, int]] = []
        in_band = False
        band_start = 0
        for row in range(h):
            if proj[row] >= FILL_BAND_THRESHOLD:
                if not in_band:
                    band_start = row
                    in_band = True
            else:
                if in_band:
                    bands.append((band_start, row))
                    in_band = False
        if in_band:
            bands.append((band_start, h))

        if not bands:
            return 0

        min_h = h * 0.03
        while bands and (bands[0][1] - bands[0][0]) < min_h:
            bands = bands[1:]
        while bands and (bands[-1][1] - bands[-1][0]) < min_h:
            bands = bands[:-1]

        if not bands:
            return 0

        max_band_h = max(e - s for s, e in bands)
        for s, e in bands:
            if (e - s) >= max_band_h * 0.8:
                return s
        return 0

    # ----------------------------------------------------- boundary refinement

    def _refine_cell_boundaries(
        self,
        gray_fill: np.ndarray,
        expected_rows: int,
        expected_cols: int,
    ) -> tuple[list[int], list[int]]:
        """基于高阈值间隙检测精修行列边界。"""
        h, w = gray_fill.shape[:2]

        # Step 1: 裁剪四周空白
        row_means = np.mean(gray_fill, axis=1)
        col_means = np.mean(gray_fill, axis=0)
        row_thresh = np.max(row_means) - 5.0
        col_thresh = np.max(col_means) - 5.0
        content_rows = np.where(row_means < row_thresh)[0]
        content_cols = np.where(col_means < col_thresh)[0]
        if len(content_rows) > 10 and len(content_cols) > 10:
            trim_y0, trim_y1 = int(content_rows[0]), int(content_rows[-1]) + 1
            trim_x0, trim_x1 = int(content_cols[0]), int(content_cols[-1]) + 1
        else:
            trim_y0, trim_y1 = 0, h
            trim_x0, trim_x1 = 0, w
        content_h = trim_y1 - trim_y0
        content_w = trim_x1 - trim_x0

        # Step 2: 行边界
        _, bin_high = cv2.threshold(gray_fill, 230, 255, cv2.THRESH_BINARY_INV)
        row_gap_centers = [
            (s + e) / 2.0
            for s, e in self._find_gaps(bin_high, axis=0, min_gap=2, w=w, h=h)
        ]
        expected_row_h = content_h / expected_rows
        search_r = max(8, int(expected_row_h * 0.40))

        row_bounds = [trim_y0]
        for i in range(1, expected_rows):
            exp_y = trim_y0 + int(i * expected_row_h)
            best = exp_y
            best_dist = float("inf")
            for gc in row_gap_centers:
                if abs(gc - exp_y) <= search_r:
                    d = abs(gc - exp_y)
                    if d < best_dist:
                        best_dist = d
                        best = int(round(gc))
            best = max(best, row_bounds[-1] + 5)
            row_bounds.append(best)
        row_bounds.append(trim_y1)

        # Step 3: 列边界（搜索半径更保守，避免气泡干扰）
        col_gap_centers = [
            (s + e) / 2.0
            for s, e in self._find_gaps(bin_high, axis=1, min_gap=2, w=w, h=h)
        ]
        expected_col_w = content_w / expected_cols
        search_r_col = min(10, max(4, int(expected_col_w * 0.25)))

        col_bounds = [trim_x0]
        for i in range(1, expected_cols):
            exp_x = trim_x0 + int(i * expected_col_w)
            best = exp_x
            best_dist = float("inf")
            for gc in col_gap_centers:
                if abs(gc - exp_x) <= search_r_col:
                    d = abs(gc - exp_x)
                    if d < best_dist:
                        best_dist = d
                        best = int(round(gc))
            best = max(best, col_bounds[-1] + 3)
            col_bounds.append(best)
        col_bounds.append(trim_x1)

        return row_bounds, col_bounds

    @staticmethod
    def _find_gaps(
        binary_inv: np.ndarray,
        axis: int,
        min_gap: int,
        w: int,
        h: int,
    ) -> list[tuple[int, int]]:
        """binary_inv 中 0=白(间隙), 255=黑(内容)。找连续 0 的段。"""
        if axis == 0:
            black_ratio = np.sum(binary_inv > 0, axis=1) / w
        else:
            black_ratio = np.sum(binary_inv > 0, axis=0) / h
        is_gap = black_ratio < 0.05
        gaps: list[tuple[int, int]] = []
        in_gap = False
        start = 0
        for i in range(len(is_gap)):
            if is_gap[i]:
                if not in_gap:
                    start = i
                    in_gap = True
            else:
                if in_gap:
                    if i - start >= min_gap:
                        gaps.append((start, i))
                    in_gap = False
        if in_gap and (len(is_gap) - start) >= min_gap:
            gaps.append((start, len(is_gap)))
        return gaps

    # ----------------------------------------------------- public api

    def recognize(
        self,
        image: np.ndarray,
        options: Optional[list[str]] = None,
    ) -> Optional[str]:
        """识别填涂区域，返回选中的选项。多选或未达阈值返回 None。"""
        image = self._trim_margin(image)
        if options is None:
            options = self.option_labels
        data = self._analyze_zones(image)
        if not data.above_threshold or data.is_multi:
            return None
        return options[data.best_idx]

    def recognize_with_viz(
        self,
        image: np.ndarray,
        options: Optional[list[str]] = None,
    ) -> tuple[Optional[str], np.ndarray, list[float]]:
        """识别填涂区域并返回 (result, viz_image, zone_fills)。"""
        image = self._trim_margin(image)
        if options is None:
            options = self.option_labels

        data = self._analyze_zones(image)
        if data.is_multi:
            result: Optional[str] = None
        elif data.above_threshold:
            result = options[data.best_idx]
        else:
            result = None

        gray = self._to_gray(image)
        viz = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        img_h, img_w = gray.shape
        zone_w = img_w / self.zone_count
        font_scale = max(zone_w / 60, 0.3)
        font_thick = max(int(font_scale * 2), 1)

        for z in range(self.zone_count):
            zx0 = int(z * zone_w)
            zx1 = int((z + 1) * zone_w)
            fill = data.zone_fills[z]
            is_selected = (
                z == data.best_idx and data.above_threshold and not data.is_multi
            )

            if data.is_multi and fill >= (self.multi_threshold or 0):
                cv2.rectangle(viz, (zx0, 0), (zx1, img_h), COLOR_MULTI, 2)
                text = f"{options[z]}:{fill:.0%}"
                cv2.putText(
                    viz, text, (zx0 + 3, img_h - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale, COLOR_MULTI, font_thick,
                )
            elif is_selected:
                cv2.rectangle(viz, (zx0, 0), (zx1, img_h), COLOR_SELECTED, 2)
                text = f"{options[z]}:{fill:.0%}"
                cv2.putText(
                    viz, text, (zx0 + 3, img_h - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale, COLOR_SELECTED, font_thick,
                )
            elif fill > self.threshold * 0.5:
                cv2.rectangle(viz, (zx0, 0), (zx1, img_h), COLOR_HALF, 1)

        for z in range(1, self.zone_count):
            x = int(z * zone_w)
            cv2.line(viz, (x, 0), (x, img_h), COLOR_LINE, 1)

        return result, viz, list(data.zone_fills)
