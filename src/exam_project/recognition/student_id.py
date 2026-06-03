"""学号气泡填涂识别器。

采用单遍轮廓检测 + 第三大轮廓作为填涂网格区域的策略。
对网格按 N 列 × (N+1) 行（header + N 个数字行）等分，
逐格计算黑色像素填充率决定每位学号。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np


# 填涂网格最小宽高比（占 ROI 比例）
GRID_MIN_RATIO = 0.30
# 填涂网格面积占比下限
GRID_MIN_AREA_RATIO = 0.10
# 宽高比合法范围
GRID_ASPECT_MIN = 0.5
GRID_ASPECT_MAX = 5.0
# 空白气泡检测：所有数字最佳 fill 的最大值低于此值且范围小于 0.08 → 空白
BLANK_MAX_FILL = 0.30
BLANK_FILL_RANGE = 0.08
# 最佳/次佳 fill 差距小于此值时记入 ambiguity
AMBIGUITY_GAP = 0.05


@dataclass(frozen=True)
class StudentIdResult:
    """单次学号识别结果。"""

    student_id: str  # 长度为 digit_count，"?" 表无法识别
    digits: list[Optional[int]]
    fill_grid: list[list[float]]  # [col][row] = fill ratio
    bounds: tuple[int, int, int, int]  # (x, y, w, h)
    cell_size: tuple[float, float]
    ambiguity_warnings: list[str] = field(default_factory=list)

    @property
    def is_blank(self) -> bool:
        return all(d is None for d in self.digits)


@dataclass(frozen=True)
class StudentIdVizResult:
    """recognize_with_viz 的完整返回。"""

    student_id: str
    viz_image: np.ndarray
    digit_details: list[dict]


class StudentIdRecognizer:
    """学号气泡填涂识别器。"""

    def __init__(
        self,
        digit_count: int = 10,
        threshold: float = 0.2,
        margin: int = 0,
        canny_low: int = 50,
        canny_high: int = 150,
    ) -> None:
        if digit_count < 1:
            raise ValueError("digit_count 必须 >= 1")
        self.digit_count = digit_count
        self.total_rows = digit_count + 1  # 含 header 行
        self.threshold = threshold
        self.margin = margin
        self.canny_low = canny_low
        self.canny_high = canny_high
        self.ambiguity_warnings: list[str] = []

    # ----------------------------------------------------- utilities

    def _trim_margin(self, roi: np.ndarray) -> np.ndarray:
        m = self.margin
        if m <= 0:
            return roi
        h, w = roi.shape[:2]
        if h <= 2 * m or w <= 2 * m:
            return roi
        return roi[m:-m, m:-m]

    # ----------------------------------------------------- grid detection

    def _detect_grid(self, gray_roi: np.ndarray) -> tuple[Optional[tuple[int, int, int, int]], np.ndarray, np.ndarray, int, list]:
        """单遍轮廓检测：去掉最大轮廓后取第三大作为填涂网格区域。

        Returns:
            (grid_bounds, canny, dilated, contour_count, contours)
        """
        h, w = gray_roi.shape
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))

        edges = cv2.Canny(gray_roi, self.canny_low, self.canny_high)
        dilated = cv2.dilate(edges, kernel, iterations=1)
        contours, _ = cv2.findContours(
            dilated, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
        )

        grid_bounds: Optional[tuple[int, int, int, int]] = None
        if contours:
            sorted_contours = sorted(contours, key=cv2.contourArea, reverse=True)
            # 跳过最大（外框），取第三大（剩余中的第二个）
            inner = sorted_contours[1:] if len(sorted_contours) > 1 else []
            third = inner[1] if len(inner) > 1 else None
            if third is not None:
                x, y, bw, bh = cv2.boundingRect(third)
                if bw >= w * GRID_MIN_RATIO and bh >= h * GRID_MIN_RATIO:
                    aspect = bw / bh if bh > 0 else 0
                    area_ratio = cv2.contourArea(third) / (w * h) if w * h > 0 else 0
                    if GRID_ASPECT_MIN <= aspect <= GRID_ASPECT_MAX and area_ratio > GRID_MIN_AREA_RATIO:
                        grid_bounds = (x, y, bw, bh)

        return grid_bounds, edges, dilated, len(contours), contours

    # ----------------------------------------------------- bubble analysis

    def _analyze_bubbles(
        self,
        roi: np.ndarray,
    ) -> Optional[dict]:
        """逐格计算填充率，返回 grid 数据或 None 表示未检测到网格。"""
        gray = roi if roi.ndim == 2 else cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        grid_bounds, _, _, _, _ = self._detect_grid(gray)
        if grid_bounds is None:
            return None
        x, y, bw, bh = grid_bounds
        cell_w = bw / self.digit_count
        cell_h = bh / self.total_rows

        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        fill_grid: list[list[float]] = [[0.0] * self.digit_count for _ in range(self.digit_count)]
        for col in range(self.digit_count):
            for row in range(self.digit_count):
                cx0 = int(x + col * cell_w)
                cy0 = int(y + (row + 1) * cell_h)  # 跳过 header
                cx1 = int(x + (col + 1) * cell_w)
                cy1 = int(y + (row + 2) * cell_h)
                cell_pixels = binary[cy0:cy1, cx0:cx1]
                total = cell_pixels.size
                black = int(np.count_nonzero(cell_pixels))
                fill_grid[col][row] = black / total if total > 0 else 0.0

        digits: list[Optional[int]] = []
        best_rows: list[int] = []
        best_fills: list[float] = []
        for col in range(self.digit_count):
            fills = fill_grid[col]
            best_row = max(range(self.digit_count), key=lambda r: fills[r])
            best_fill = fills[best_row]
            best_rows.append(best_row)
            best_fills.append(best_fill)
            digits.append(best_row if best_fill >= self.threshold else None)

        return {
            "bounds": grid_bounds,
            "cell_size": (cell_w, cell_h),
            "fill_grid": fill_grid,
            "digits": digits,
            "best_rows": best_rows,
            "best_fills": best_fills,
        }

    # ----------------------------------------------------- public api

    def recognize(self, roi: np.ndarray) -> str:
        """识别学号，返回长度 = digit_count 的字符串。无法识别位为 '?'。"""
        self.ambiguity_warnings = []
        data = self._analyze_bubbles(self._trim_margin(roi))
        if data is None:
            return "?" * self.digit_count

        # 空白检测
        if data["best_fills"]:
            max_fill = max(data["best_fills"])
            min_fill = min(data["best_fills"])
            fill_range = max_fill - min_fill
            if max_fill < BLANK_MAX_FILL and fill_range < BLANK_FILL_RANGE:
                return "?" * self.digit_count

        # 歧义检测
        for col in range(self.digit_count):
            fills = data["fill_grid"][col]
            sorted_fills = sorted(fills, reverse=True)
            best = sorted_fills[0]
            runner = sorted_fills[1] if len(sorted_fills) > 1 else 0
            if best >= self.threshold and (best - runner) < AMBIGUITY_GAP:
                self.ambiguity_warnings.append(
                    f"第{col + 1}位: 最佳{best:.2%}与次佳{runner:.2%}差距过小"
                )
        return "".join("?" if d is None else str(d) for d in data["digits"])

    def recognize_with_viz(self, roi: np.ndarray) -> StudentIdVizResult:
        """识别学号并返回可视化结果。"""
        self.ambiguity_warnings = []
        trimmed = self._trim_margin(roi)
        data = self._analyze_bubbles(trimmed)
        if data is None:
            return StudentIdVizResult(
                student_id="?" * self.digit_count,
                viz_image=trimmed.copy(),
                digit_details=[],
            )

        if data["best_fills"]:
            max_fill = max(data["best_fills"])
            min_fill = min(data["best_fills"])
            fill_range = max_fill - min_fill
            if max_fill < BLANK_MAX_FILL and fill_range < BLANK_FILL_RANGE:
                return StudentIdVizResult(
                    student_id="?" * self.digit_count,
                    viz_image=trimmed.copy(),
                    digit_details=[],
                )

        grid_y0, grid_y1, grid_x0, grid_x1 = data["bounds"]
        cell_w, cell_h = data["cell_size"]

        gray = trimmed if trimmed.ndim == 2 else cv2.cvtColor(trimmed, cv2.COLOR_BGR2GRAY)
        viz = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        font_scale = max(min(cell_w, cell_h) / 60, 0.25)
        font_thick = max(int(font_scale * 2), 1)

        for col in range(self.digit_count):
            for row in range(self.digit_count):
                cx0 = int(grid_x0 + col * cell_w)
                cy0 = int(grid_y0 + (row + 1) * cell_h)
                cx1 = int(grid_x0 + (col + 1) * cell_w)
                cy1 = int(grid_y0 + (row + 2) * cell_h)
                fill = data["fill_grid"][col][row]
                is_selected = row == data["best_rows"][col] and fill >= self.threshold
                if is_selected:
                    cv2.rectangle(viz, (cx0, cy0), (cx1, cy1), (0, 200, 0), 2)
                    cv2.putText(
                        viz, str(row), (cx0 + 3, cy1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 200, 0), font_thick,
                    )
                elif fill > self.threshold * 0.5:
                    cv2.rectangle(viz, (cx0, cy0), (cx1, cy1), (0, 160, 255), 1)

        digit_details: list[dict] = []
        for col in range(self.digit_count):
            fills = data["fill_grid"][col]
            sorted_fills = sorted(enumerate(fills), key=lambda x: -x[1])
            digit_details.append({
                "digit": data["digits"][col],
                "best_row": data["best_rows"][col],
                "best_fill": data["best_fills"][col],
                "runner_up_row": sorted_fills[1][0] if len(sorted_fills) > 1 else -1,
                "runner_up_fill": sorted_fills[1][1] if len(sorted_fills) > 1 else 0.0,
            })

        student_id = "".join("?" if d is None else str(d) for d in data["digits"])
        return StudentIdVizResult(
            student_id=student_id,
            viz_image=viz,
            digit_details=digit_details,
        )
