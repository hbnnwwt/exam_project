"""选择题填涂识别器。

继承 BubbleRecognizerBase，新增批量识别接口 recognize_all_with_viz。
每题支持单选/多选/未涂；提供空白基准校准与暗化辅助判别。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from .bubble_base import (
    BubbleRecognizerBase,
    COLOR_HALF,
    COLOR_LINE,
    COLOR_SELECTED,
)
from .constants import MORPH_KERNEL


# 题目序号列占整行的比例
NUMBER_COLUMN_RATIO = 0.20
# 多选时的相对阈值（占最佳填涂率的比例）
MULTI_REL_RATIO_DEFAULT = 0.75
# 污渍检测：所有 zone 的最小 fill 与最佳 fill 的比例上限
STAIN_RATIO_DEFAULT = 0.70
# 气泡大小占格宽度的范围
BUBBLE_MIN_W_RATIO = 0.08
BUBBLE_MAX_W_RATIO = 0.30
BUBBLE_MIN_H_RATIO = 0.40


@dataclass(frozen=True)
class CellResult:
    """单题识别结果。"""

    question: int
    answer: Optional[str]
    multi_options: list[int]
    cell_bounds: tuple[int, int, int, int]  # (y0, y1, x0, x1) 绝对坐标
    cell_viz: np.ndarray
    zone_fills: list[float]
    zone_bounds: list[tuple[int, int]]
    zone_gray_means: list[float]
    gray_darkening: Optional[float]

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "answer": self.answer,
            "multi_options": list(self.multi_options),
            "cell_bounds": self.cell_bounds,
            "zone_fills": list(self.zone_fills),
            "zone_bounds": list(self.zone_bounds),
            "zone_gray_means": list(self.zone_gray_means),
            "gray_darkening": self.gray_darkening,
        }


@dataclass(frozen=True)
class ChoiceBatchResult:
    """批量选择题识别结果。"""

    answers: dict[int, str]
    grid_viz: np.ndarray
    cell_results: list[CellResult]


class ChoiceRecognizer(BubbleRecognizerBase):
    """选择题识别器，扩展基类支持多题批量识别与暗化补偿。"""

    def __init__(
        self,
        threshold: float = 0.06,
        option_count: int = 4,
        margin: int = 5,
        multi_threshold: Optional[float] = 0.75,
        blank_baseline: Optional[dict[int, list[float]]] = None,
        gray_darkening_threshold: float = 8.0,
        zone_bounds_template: Optional[dict[int, list[tuple[float, float]]]] = None,
    ) -> None:
        super().__init__(
            threshold=threshold,
            margin=margin,
            zone_count=option_count,
            option_labels=[chr(ord("A") + i) for i in range(option_count)],
            multi_threshold=multi_threshold,
        )
        self.blank_baseline = blank_baseline or {}
        self.gray_darkening_threshold = gray_darkening_threshold
        self.zone_bounds_template = zone_bounds_template or {}

    @property
    def option_count(self) -> int:
        return self.zone_count

    # ----------------------------------------------------- zone detection

    def _detect_zone_boundaries_projection(
        self,
        gray: np.ndarray,
        cell_w: int,
        cell_h: int,
    ) -> tuple[list[tuple[int, int]], int]:
        """基于灰度垂直投影的峰值检测定位气泡位置。"""
        margin_y = int(cell_h * 0.15)
        if cell_h > 2 * margin_y:
            gray_core = gray[margin_y:cell_h - margin_y, :]
        else:
            gray_core = gray

        col_proj = 255.0 - np.mean(gray_core, axis=0)
        window = max(3, int(cell_w * 0.03))
        if window % 2 == 0:
            window += 1
        kernel = np.ones(window) / window
        smooth = np.convolve(col_proj, kernel, mode="same")

        num_w = int(cell_w * NUMBER_COLUMN_RATIO)
        usable_width = cell_w - num_w
        expected_cx = [
            num_w + int((i + 0.5) * usable_width / self.zone_count)
            for i in range(self.zone_count)
        ]

        search_radius = max(3, int(usable_width / self.zone_count * 0.35))
        bubble_cx: list[int] = []
        for exp_cx in expected_cx:
            x0 = max(num_w, exp_cx - search_radius)
            x1 = min(cell_w, exp_cx + search_radius)
            if x1 <= x0:
                bubble_cx.append(exp_cx)
                continue
            bubble_cx.append(x0 + int(np.argmax(smooth[x0:x1])))

        zone_bounds: list[tuple[int, int]] = []
        for z in range(self.zone_count):
            if z == 0:
                left = num_w
            else:
                left = int((bubble_cx[z - 1] + bubble_cx[z]) / 2)
            if z == self.zone_count - 1:
                right = cell_w
            else:
                right = int((bubble_cx[z] + bubble_cx[z + 1]) / 2)
            zone_bounds.append((left, right))
        return zone_bounds, num_w

    def _detect_zone_boundaries(
        self,
        gray: np.ndarray,
        binary: np.ndarray,
        cell_w: int,
        cell_h: int,
    ) -> tuple[list[tuple[int, int]], int]:
        """先尝试连通域检测，气泡不足时回退到投影峰值。"""
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
            binary, connectivity=8
        )
        min_bw = cell_w * BUBBLE_MIN_W_RATIO
        max_bw = cell_w * BUBBLE_MAX_W_RATIO
        min_bh = cell_h * BUBBLE_MIN_H_RATIO
        bubble_cx: list[float] = []
        for i in range(1, num_labels):
            bx, by, bw, bh, _ = stats[i]
            if min_bw <= bw <= max_bw and bh >= min_bh:
                bubble_cx.append(centroids[i][0])

        if len(bubble_cx) >= self.zone_count:
            bubble_cx.sort()
            if len(bubble_cx) > self.zone_count:
                bubble_cx = self._select_best_bubbles(bubble_cx, self.zone_count)
            spacing = (bubble_cx[-1] - bubble_cx[0]) / (len(bubble_cx) - 1)
            num_w = max(int(bubble_cx[0] - spacing * 0.5), 0)
            half_s = spacing * 0.5
            zone_bounds = []
            for z in range(self.zone_count):
                zx0 = max(int(bubble_cx[z] - half_s), num_w)
                zx1 = min(int(bubble_cx[z] + half_s), cell_w)
                zone_bounds.append((zx0, zx1))
            return zone_bounds, num_w

        return self._detect_zone_boundaries_projection(gray, cell_w, cell_h)

    @staticmethod
    def _select_best_bubbles(
        sorted_cx: list[float],
        count: int,
    ) -> list[float]:
        """从已排序气泡中心中选出最均匀的 count 个。"""
        n = len(sorted_cx)
        if n <= count:
            return sorted_cx
        best_score = float("inf")
        best_start = 0
        for start in range(n - count + 1):
            subset = sorted_cx[start:start + count]
            spacings = [subset[i + 1] - subset[i] for i in range(count - 1)]
            avg = sum(spacings) / len(spacings)
            score = sum(abs(s - avg) for s in spacings)
            if score < best_score:
                best_score = score
                best_start = start
        return sorted_cx[best_start:best_start + count]

    # ----------------------------------------------------- batch recognition

    def recognize_all_with_viz(
        self,
        region_image: np.ndarray,
        question_count: int,
        question_start: int = 1,
        options: Optional[list[str]] = None,
        fixed_grid: Optional[tuple[int, int]] = None,
    ) -> ChoiceBatchResult:
        """批量识别选择题区域。

        Args:
            region_image: 整个选择题区域图像（BGR 或灰度）
            question_count: 题目数量
            question_start: 起始题号
            options: 选项标签列表，默认 A/B/C/...
            fixed_grid: (rows, cols)，默认 (5, 4)

        Returns:
            ChoiceBatchResult 含 answers, grid_viz, cell_results
        """
        if options is None:
            options = self.option_labels
        if fixed_grid is None:
            fixed_grid = (5, 4)

        gray = (
            region_image
            if region_image.ndim == 2
            else cv2.cvtColor(region_image, cv2.COLOR_BGR2GRAY)
        )
        img_h, img_w = gray.shape

        fill_start = self._detect_fill_start(gray)
        fill_h = img_h - fill_start
        gray_fill = gray[fill_start:, :]

        rows_n, cols_n = fixed_grid
        cells = self._detect_rows_fixed(gray_fill, rows_n, cols_n)

        # 网格切分可视化
        grid_viz = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        if fill_start > 0:
            cv2.rectangle(
                grid_viz, (0, 0), (img_w - 1, fill_start), (200, 200, 200), 1
            )
        cell_h = fill_h / rows_n
        cell_w = img_w / cols_n
        for row in range(rows_n + 1):
            y = fill_start + int(row * cell_h)
            cv2.line(grid_viz, (0, y), (img_w, y), COLOR_LINE, 1)
        for col in range(cols_n + 1):
            x = int(col * cell_w)
            cv2.line(grid_viz, (x, fill_start), (x, img_h), COLOR_LINE, 1)

        answers: dict[int, str] = {}
        cell_results: list[CellResult] = []

        for idx, (y0, y1, x0, x1) in enumerate(cells):
            q = question_start + idx
            cell = gray_fill[y0:y1, x0:x1]
            cell_h_pixels = y1 - y0
            cell_w_pixels = x1 - x0

            _, binary = cv2.threshold(
                cell, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            )
            open_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, MORPH_KERNEL)
            binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, open_k)

            zone_bounds, num_w = self._zone_bounds_for(q, cell, binary, cell_w_pixels, cell_h_pixels)
            zone_fills: list[float] = []
            zone_gray_means: list[float] = []
            for z in range(self.zone_count):
                zx0, zx1 = zone_bounds[z]
                zone_pixels = binary[:, zx0:zx1]
                total = zone_pixels.size
                black = np.count_nonzero(zone_pixels)
                zone_fills.append(black / total if total > 0 else 0.0)
                zone_gray_means.append(float(np.mean(cell[:, zx0:zx1])))

            best_idx = max(range(self.zone_count), key=lambda z: zone_fills[z])
            best_fill = zone_fills[best_idx]

            # 空白基准校准
            (
                effective_threshold,
                darkening_confident,
                darkening_best_idx,
                best_darkening,
            ) = self._apply_baseline(q, zone_fills, zone_gray_means)

            # 暗化优先
            if darkening_confident and darkening_best_idx is not None:
                fill_ranks = sorted(
                    range(self.zone_count),
                    key=lambda z: zone_fills[z],
                    reverse=True,
                )
                if darkening_best_idx in fill_ranks[:2]:
                    best_idx = darkening_best_idx
                    best_fill = zone_fills[best_idx]

            above = best_fill >= effective_threshold
            worst = min(zone_fills)
            stain_threshold = STAIN_RATIO_DEFAULT
            has_baseline = q in self.blank_baseline
            if has_baseline and best_darkening > self.gray_darkening_threshold:
                stain_threshold = 0.85
            if worst > best_fill * stain_threshold:
                above = False

            multi_options = self._detect_multi(
                above, zone_fills, best_fill, darkening_confident
            )

            if len(multi_options) >= 2:
                result: Optional[str] = "".join(options[z] for z in multi_options)
            elif above:
                result = options[best_idx]
            else:
                result = None

            if result is not None:
                answers[q] = result

            cell_viz = self._draw_cell_viz(
                cell, num_w, cell_h_pixels, zone_bounds, zone_fills,
                options, best_idx, above, multi_options,
            )

            cell_results.append(CellResult(
                question=q,
                answer=result,
                multi_options=multi_options if len(multi_options) >= 2 else [],
                cell_bounds=(fill_start + y0, fill_start + y1, x0, x1),
                cell_viz=cell_viz,
                zone_fills=zone_fills,
                zone_bounds=zone_bounds,
                zone_gray_means=zone_gray_means,
                gray_darkening=best_darkening if has_baseline else None,
            ))

            self._draw_grid_label(
                grid_viz, q, x0, y0, cell_w, cell_h, fill_start, result, multi_options,
            )

        return ChoiceBatchResult(
            answers=answers,
            grid_viz=grid_viz,
            cell_results=cell_results,
        )

    # ----------------------------------------------------- batch internals

    def _zone_bounds_for(
        self,
        question: int,
        cell: np.ndarray,
        binary: np.ndarray,
        cell_w_pixels: int,
        cell_h_pixels: int,
    ) -> tuple[list[tuple[int, int]], int]:
        """优先用空白卷模板，缺失时回退到自动检测。"""
        if question in self.zone_bounds_template:
            template = self.zone_bounds_template[question]
            if len(template) >= self.zone_count:
                zone_bounds = [
                    (int(r0 * cell_w_pixels), int(r1 * cell_w_pixels))
                    for r0, r1 in template[: self.zone_count]
                ]
                num_w = zone_bounds[0][0]
                return zone_bounds, num_w
        return self._detect_zone_boundaries(
            cell, binary, cell_w_pixels, cell_h_pixels
        )

    def _apply_baseline(
        self,
        question: int,
        zone_fills: list[float],
        zone_gray_means: list[float],
    ) -> tuple[float, bool, Optional[int], float]:
        """应用空白基准：返回 effective_threshold, darkening_confident, best_idx, best_darkening。"""
        if question not in self.blank_baseline:
            return self.threshold, False, None, 0.0
        blank_means = self.blank_baseline[question]
        if len(blank_means) < self.zone_count:
            return self.threshold, False, None, 0.0

        mean_shift = (
            sum(blank_means) / len(blank_means)
            - sum(zone_gray_means) / len(zone_gray_means)
        )
        darkening_per_zone = [
            (blank_means[z] - zone_gray_means[z]) - mean_shift
            for z in range(self.zone_count)
        ]
        best_darkening = max(darkening_per_zone)
        if best_darkening <= self.gray_darkening_threshold:
            return self.threshold, False, None, best_darkening

        effective_threshold = self.threshold * 0.35
        darkening_best_idx = max(
            range(self.zone_count),
            key=lambda z: darkening_per_zone[z],
        )
        confident = zone_fills[darkening_best_idx] > 0.02
        return effective_threshold, confident, darkening_best_idx, best_darkening

    def _detect_multi(
        self,
        above: bool,
        zone_fills: list[float],
        best_fill: float,
        darkening_confident: bool,
    ) -> list[int]:
        if not above or self.multi_threshold is None:
            return []
        multi_rel = 0.95 if darkening_confident else self.multi_threshold
        threshold_rel = best_fill * multi_rel
        candidates = [
            z for z in range(self.zone_count) if zone_fills[z] >= threshold_rel
        ]
        if len(candidates) < 2:
            return []
        multi_fills = [zone_fills[z] for z in candidates]
        multi_worst = min(multi_fills)
        unselected = [
            zone_fills[z]
            for z in range(self.zone_count)
            if z not in candidates
        ]
        if unselected:
            if multi_worst <= max(unselected) * 1.2:
                return []
        return candidates

    def _draw_cell_viz(
        self,
        cell: np.ndarray,
        num_w: int,
        cell_h_pixels: int,
        zone_bounds: list[tuple[int, int]],
        zone_fills: list[float],
        options: list[str],
        best_idx: int,
        above: bool,
        multi_options: list[int],
    ) -> np.ndarray:
        cell_viz = cv2.cvtColor(cell, cv2.COLOR_GRAY2BGR)
        if num_w > 0:
            cv2.rectangle(
                cell_viz, (0, 0), (num_w, cell_h_pixels), (200, 200, 200), 1
            )
        for z in range(self.zone_count):
            zx0, zx1 = zone_bounds[z]
            fill = zone_fills[z]
            is_multi = len(multi_options) >= 2 and z in multi_options
            is_single = len(multi_options) < 2 and z == best_idx and above
            if is_multi or is_single:
                cv2.rectangle(
                    cell_viz, (zx0, 0), (zx1, cell_h_pixels), COLOR_SELECTED, 2
                )
                text = f"{options[z]}:{fill:.0%}"
                fs = max((zx1 - zx0) / 60, 0.25)
                ft = max(int(fs * 2), 1)
                cv2.putText(
                    cell_viz, text, (zx0 + 2, cell_h_pixels - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, fs, COLOR_SELECTED, ft,
                )
            elif fill > self.threshold * 0.5:
                cv2.rectangle(
                    cell_viz, (zx0, 0), (zx1, cell_h_pixels), COLOR_HALF, 1
                )
        for z in range(1, self.zone_count):
            x = zone_bounds[z][0]
            cv2.line(
                cell_viz, (x, 0), (x, cell_h_pixels), COLOR_LINE, 1
            )
        return cell_viz

    def _draw_grid_label(
        self,
        grid_viz: np.ndarray,
        q: int,
        x0: int,
        y0: int,
        cell_w: float,
        cell_h: float,
        fill_start: int,
        result: Optional[str],
        multi_options: list[int],
    ) -> None:
        fs = max(min(cell_w, cell_h) / 40, 0.3)
        is_multi = len(multi_options) >= 2
        is_blank = result is None
        if is_blank or is_multi:
            color = (0, 0, 255)
            label = f"{q}:{result if result else '-'}"
            cv2.putText(
                grid_viz, label,
                (x0 + 2, fill_start + y0 + int(cell_h * 0.15)),
                cv2.FONT_HERSHEY_SIMPLEX, fs, color, 1,
            )
            cx = x0 + int(cell_w * 0.8)
            cy = fill_start + y0 + int(cell_h * 0.6)
            t = max(int(fs * 2), 2)
            cv2.line(grid_viz, (cx - 5, cy - 5), (cx + 5, cy + 5), color, t)
            cv2.line(grid_viz, (cx - 5, cy + 5), (cx + 5, cy - 5), color, t)
        else:
            cv2.putText(
                grid_viz, f"{q}:{result}",
                (x0 + 2, fill_start + y0 + int(cell_h * 0.15)),
                cv2.FONT_HERSHEY_SIMPLEX, fs, (0, 200, 0), 1,
            )

    # ----------------------------------------------------- cell layout

    def _detect_rows_fixed(
        self,
        region_image: np.ndarray,
        expected_rows: int,
        expected_cols: int,
    ) -> list[tuple[int, int, int, int]]:
        """均匀切分 + 投影精修。"""
        h, w = region_image.shape[:2]
        row_bounds, col_bounds = self._refine_cell_boundaries(
            region_image, expected_rows, expected_cols
        )
        cells: list[tuple[int, int, int, int]] = []
        for row in range(expected_rows):
            y0, y1 = row_bounds[row], row_bounds[row + 1]
            for col in range(expected_cols):
                x0, x1 = col_bounds[col], col_bounds[col + 1]
                cells.append((y0, y1, x0, x1))
        return cells
