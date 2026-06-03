"""判断题填涂识别器。

继承 BubbleRecognizerBase，对 T/F 两 zone 做密度比较。
包含专用 bubble blob 检测、lighting-invariant 暗化补偿、多选（TF）判定。
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
from .constants import (
    JUDGE_BLOB_AREA_MAX,
    JUDGE_BLOB_AREA_MIN,
    JUDGE_BLOB_ASPECT_MAX,
    JUDGE_BLOB_ASPECT_MIN,
    JUDGE_MIN_FILL,
    JUDGE_MULTI_FILL,
    JUDGE_MULTI_RATIO,
    JUDGE_SIDE_MARGIN_RATIO,
    JUDGE_VALID_RATIO,
    JUDGE_VERT_MARGIN_RATIO,
    MORPH_KERNEL,
)


COLOR_BLANK_DASHED = (0, 0, 255)  # 红色虚线：未填涂/空白

# T/F zone 总宽度占可用宽度的上限
ZONE_TOTAL_RATIO = 0.30
# 投影峰值搜索时的窗口宽度比例
PROJECTION_WINDOW_RATIO = 0.05


@dataclass(frozen=True)
class JudgeCellResult:
    """单题判断题识别结果。"""

    question: int
    answer: Optional[str]  # "T" / "F" / "TF" / None
    cell_bounds: tuple[int, int, int, int]
    cell_viz: np.ndarray
    zone_fills: list[float]
    zone_bounds: list[tuple[int, int]]
    zone_gray_means: list[float]
    gray_darkening: Optional[float]

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "answer": self.answer,
            "cell_bounds": self.cell_bounds,
            "zone_fills": list(self.zone_fills),
            "zone_bounds": list(self.zone_bounds),
            "zone_gray_means": list(self.zone_gray_means),
            "gray_darkening": self.gray_darkening,
        }


@dataclass(frozen=True)
class JudgeBatchResult:
    """批量判断题识别结果。"""

    answers: dict[int, str]
    grid_viz: np.ndarray
    cell_results: list[JudgeCellResult]


class JudgeRecognizer(BubbleRecognizerBase):
    """判断题识别器，扩展基类支持 T/F 双 zone 与多选判定。"""

    def __init__(
        self,
        threshold: float = 0.06,
        margin: int = 5,
        multi_threshold: Optional[float] = 0.10,
        blank_baseline: Optional[dict[int, list[float]]] = None,
        gray_darkening_threshold: float = 8.0,
        zone_bounds_template: Optional[dict[int, list[tuple[float, float]]]] = None,
    ) -> None:
        super().__init__(
            threshold=threshold,
            margin=margin,
            zone_count=2,
            option_labels=["T", "F"],
            multi_threshold=multi_threshold,
        )
        self.blank_baseline = blank_baseline or {}
        self.gray_darkening_threshold = gray_darkening_threshold
        self.zone_bounds_template = zone_bounds_template or {}

    # ----------------------------------------------------- bubble detection

    def _detect_bubbles_in_cell(
        self,
        binary: np.ndarray,
        cell_w: int,
        cell_h: int,
    ) -> dict:
        """检测格子内的方形气泡区域。"""
        contours, _ = cv2.findContours(
            binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        mid_x = cell_w // 2
        side_margin = int(cell_w * JUDGE_SIDE_MARGIN_RATIO)
        top_margin = int(cell_h * JUDGE_VERT_MARGIN_RATIO)
        bottom_margin = int(cell_h * JUDGE_VERT_MARGIN_RATIO)

        t_blob: Optional[tuple[int, int, int, int]] = None
        f_blob: Optional[tuple[int, int, int, int]] = None
        all_blobs: list[tuple[int, int, int, int]] = []

        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            area = cv2.contourArea(cnt)

            if area < JUDGE_BLOB_AREA_MIN or area > JUDGE_BLOB_AREA_MAX:
                continue
            aspect = w / h if h > 0 else 0
            if aspect < JUDGE_BLOB_ASPECT_MIN or aspect > JUDGE_BLOB_ASPECT_MAX:
                continue
            if x < side_margin or (x + w) > (cell_w - side_margin):
                continue
            if y < top_margin or (y + h) > (cell_h - bottom_margin):
                continue

            cx = x + w // 2
            if cx < mid_x:
                if t_blob is None or abs(cx - mid_x) < abs(
                    t_blob[0] + t_blob[2] // 2 - mid_x
                ):
                    t_blob = (x, y, w, h)
            else:
                if f_blob is None or abs(cx - mid_x) < abs(
                    f_blob[0] + f_blob[2] // 2 - mid_x
                ):
                    f_blob = (x, y, w, h)
            all_blobs.append((x, y, w, h))

        if t_blob is None:
            t_blob = (
                mid_x - int(cell_w * 0.15),
                top_margin,
                int(cell_w * 0.30),
                cell_h - top_margin - bottom_margin,
            )
        if f_blob is None:
            f_blob = (
                mid_x + int(cell_w * 0.05),
                top_margin,
                int(cell_w * 0.30),
                cell_h - top_margin - bottom_margin,
            )
        return {"T": t_blob, "F": f_blob, "blobs": all_blobs}

    # ----------------------------------------------------- zone boundaries

    def _detect_zone_boundaries(
        self,
        gray: np.ndarray,
        cell_w: int,
        cell_h: int,
        bubble_data: Optional[dict] = None,
    ) -> tuple[list[tuple[int, int]], int]:
        """基于实际气泡位置或灰度投影划分 T/F zone 边界。

        zone 宽度严格限制为可用宽度的 30%，避免把非气泡区域纳入统计。
        """
        if bubble_data is not None and len(bubble_data["blobs"]) >= 2:
            t_blob = bubble_data["T"]
            f_blob = bubble_data["F"]
            t_cx = t_blob[0] + t_blob[2] // 2
            f_cx = f_blob[0] + f_blob[2] // 2
            num_w = max(int(min(t_blob[0], f_blob[0]) * 0.9), int(cell_w * 0.15))
        else:
            margin_y = int(cell_h * 0.15)
            gray_core = (
                gray[margin_y:cell_h - margin_y, :]
                if cell_h > 2 * margin_y
                else gray
            )
            col_proj = 255.0 - np.mean(gray_core, axis=0)
            window = max(3, int(cell_w * PROJECTION_WINDOW_RATIO))
            if window % 2 == 0:
                window += 1
            kernel = np.ones(window) / window
            smooth = np.convolve(col_proj, kernel, mode="same")
            num_w = int(cell_w * 0.20)
            usable_width = cell_w - num_w
            expected_cx = [
                num_w + int((i + 0.5) * usable_width / self.zone_count)
                for i in range(self.zone_count)
            ]
            search_radius = max(5, int(usable_width / self.zone_count * 0.40))
            bubble_cx: list[int] = []
            for exp_cx in expected_cx:
                x0 = max(num_w, exp_cx - search_radius)
                x1 = min(cell_w, exp_cx + search_radius)
                if x1 <= x0:
                    bubble_cx.append(exp_cx)
                    continue
                bubble_cx.append(x0 + int(np.argmax(smooth[x0:x1])))
            t_cx, f_cx = bubble_cx[0], bubble_cx[1]

        usable_width = cell_w - num_w
        mid = (t_cx + f_cx) // 2
        max_zone_half = int(usable_width * ZONE_TOTAL_RATIO / 2)

        zone_bounds = [
            (max(num_w, mid - max_zone_half), mid),
            (mid, min(cell_w, mid + max_zone_half)),
        ]
        return zone_bounds, num_w

    # ----------------------------------------------------- cell layout

    def _detect_cells_fixed(
        self,
        region_image: np.ndarray,
        rows_n: int,
        cols_n: int,
        cell_mapping: list[Optional[int]],
    ) -> list[tuple[int, int, int, int, Optional[int]]]:
        """均匀切分 + 投影精修 + 自定义题号映射。"""
        h, w = region_image.shape[:2]
        row_bounds, col_bounds = self._refine_cell_boundaries(
            region_image, rows_n, cols_n
        )
        cells: list[tuple[int, int, int, int, Optional[int]]] = []
        for row in range(rows_n):
            y0, y1 = row_bounds[row], row_bounds[row + 1]
            for col in range(cols_n):
                x0, x1 = col_bounds[col], col_bounds[col + 1]
                idx = row * cols_n + col
                q = cell_mapping[idx] if idx < len(cell_mapping) else None
                cells.append((y0, y1, x0, x1, q))
        return cells

    # ----------------------------------------------------- batch recognition

    def recognize_all_with_viz(
        self,
        region_image: np.ndarray,
        question_count: Optional[int] = None,
        question_start: int = 21,
        rows_n: int = 3,
        cols_n: int = 4,
    ) -> JudgeBatchResult:
        """批量识别判断题区域。"""
        if question_count is None:
            question_count = rows_n * cols_n

        gray = (
            region_image
            if region_image.ndim == 2
            else cv2.cvtColor(region_image, cv2.COLOR_BGR2GRAY)
        )
        img_h, img_w = gray.shape

        fill_start = self._detect_fill_start(gray)
        fill_h = img_h - fill_start
        gray_fill = gray[fill_start:, :]

        cell_mapping: list[Optional[int]] = list(
            range(question_start, question_start + question_count)
        )
        total_cells = rows_n * cols_n
        cell_mapping += [None] * (total_cells - len(cell_mapping))
        cells = self._detect_cells_fixed(gray_fill, rows_n, cols_n, cell_mapping)

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
        cell_results: list[JudgeCellResult] = []

        for y0, y1, x0, x1, q in cells:
            if q is None:
                continue
            cell = gray_fill[y0:y1, x0:x1]
            cell_h_pixels = y1 - y0
            cell_w_pixels = x1 - x0

            _, binary = cv2.threshold(
                cell, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            )
            open_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, MORPH_KERNEL)
            binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, open_k)

            bubble_data = self._detect_bubbles_in_cell(
                binary, cell_w_pixels, cell_h_pixels
            )

            if q in self.zone_bounds_template:
                template = self.zone_bounds_template[q]
                if len(template) >= self.zone_count:
                    zone_bounds = [
                        (int(r0 * cell_w_pixels), int(r1 * cell_w_pixels))
                        for r0, r1 in template[: self.zone_count]
                    ]
                    num_w = zone_bounds[0][0]
                else:
                    zone_bounds, num_w = self._detect_zone_boundaries(
                        cell, cell_w_pixels, cell_h_pixels,
                        bubble_data=bubble_data,
                    )
            else:
                zone_bounds, num_w = self._detect_zone_boundaries(
                    cell, cell_w_pixels, cell_h_pixels,
                    bubble_data=bubble_data,
                )

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
            worst_fill = min(zone_fills)
            ratio = worst_fill / best_fill if best_fill > 0 else 0

            effective_min_fill, best_darkening, has_baseline = self._apply_baseline(
                q, zone_gray_means,
            )

            above = (ratio < JUDGE_VALID_RATIO) and (best_fill > effective_min_fill)
            result: Optional[str] = self._judge_result(above, zone_fills, ratio, best_idx)

            if result is not None:
                answers[q] = result

            cell_viz = self._draw_cell_viz(
                cell, num_w, cell_h_pixels, zone_bounds, zone_fills,
                best_idx, above, has_baseline, zone_gray_means, best_darkening,
            )
            cell_results.append(JudgeCellResult(
                question=q,
                answer=result,
                cell_bounds=(fill_start + y0, fill_start + y1, x0, x1),
                cell_viz=cell_viz,
                zone_fills=zone_fills,
                zone_bounds=zone_bounds,
                zone_gray_means=zone_gray_means,
                gray_darkening=best_darkening if has_baseline else None,
            ))
            self._draw_grid_label(
                grid_viz, q, x0, y0, cell_w, cell_h, fill_start, result,
            )

        return JudgeBatchResult(
            answers=answers,
            grid_viz=grid_viz,
            cell_results=cell_results,
        )

    # ----------------------------------------------------- batch internals

    def _apply_baseline(
        self,
        q: int,
        zone_gray_means: list[float],
    ) -> tuple[float, float, bool]:
        """lighting-invariant 暗化补偿。

        Returns:
            (effective_min_fill, best_darkening, has_baseline)
        """
        effective_min_fill = JUDGE_MIN_FILL
        has_baseline = q in self.blank_baseline
        best_darkening = 0.0
        if not has_baseline:
            return effective_min_fill, best_darkening, False
        blank_means = self.blank_baseline[q]
        if len(blank_means) < self.zone_count:
            return effective_min_fill, best_darkening, True
        # zone0 (T) darkening = blank_diff - actual_diff
        # zone1 (F) darkening = actual_diff - blank_diff
        blank_diff = blank_means[0] - blank_means[1]
        actual_diff = zone_gray_means[0] - zone_gray_means[1]
        darkening_per_zone = [
            blank_diff - actual_diff,
            actual_diff - blank_diff,
        ]
        best_darkening = max(darkening_per_zone)
        if best_darkening > self.gray_darkening_threshold:
            effective_min_fill = JUDGE_MIN_FILL * 0.35
        return effective_min_fill, best_darkening, True

    @staticmethod
    def _judge_result(
        above: bool,
        zone_fills: list[float],
        ratio: float,
        best_idx: int,
    ) -> Optional[str]:
        """多选（TF）检测 + 单选 + 空白。"""
        if above and (
            zone_fills[0] > JUDGE_MULTI_FILL
            and zone_fills[1] > JUDGE_MULTI_FILL
            and ratio > JUDGE_MULTI_RATIO
        ):
            return "TF"
        if above:
            return ["T", "F"][best_idx]
        return None

    def _draw_cell_viz(
        self,
        cell: np.ndarray,
        num_w: int,
        cell_h_pixels: int,
        zone_bounds: list[tuple[int, int]],
        zone_fills: list[float],
        best_idx: int,
        above: bool,
        has_baseline: bool,
        zone_gray_means: list[float],
        best_darkening: float,
    ) -> np.ndarray:
        cell_viz = cv2.cvtColor(cell, cv2.COLOR_GRAY2BGR)
        if num_w > 0:
            cv2.rectangle(
                cell_viz, (0, 0), (num_w, cell_h_pixels), (200, 200, 200), 1
            )
        margin_v = int(cell_h_pixels * 0.10)
        for zi, label in enumerate(["T", "F"]):
            zx0, zx1 = zone_bounds[zi]
            fill = zone_fills[zi]
            is_selected = zi == best_idx and above
            by = margin_v
            bh = cell_h_pixels - 2 * margin_v
            bw = zx1 - zx0
            if is_selected:
                cv2.rectangle(
                    cell_viz, (zx0, by), (zx1, by + bh), COLOR_SELECTED, 2
                )
                if has_baseline and zi < len(zone_gray_means):
                    text = f"{label}:{fill:.0%}(D{best_darkening:.0f})"
                else:
                    text = f"{label}:{fill:.0%}"
                fs = max(min(bw, bh) / 40, 0.25)
                ft = max(int(fs * 2), 1)
                cv2.putText(
                    cell_viz, text, (zx0 + 2, by + bh - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, fs, COLOR_SELECTED, ft,
                )
            elif fill > self.threshold * 0.5:
                cv2.rectangle(
                    cell_viz, (zx0, by), (zx1, by + bh), COLOR_HALF, 1
                )
            else:
                cv2.rectangle(
                    cell_viz, (zx0, by), (zx1, by + bh),
                    COLOR_BLANK_DASHED, 1, lineType=cv2.LINE_4,
                )
        return cell_viz

    @staticmethod
    def _draw_grid_label(
        grid_viz: np.ndarray,
        q: int,
        x0: int,
        y0: int,
        cell_w: float,
        cell_h: float,
        fill_start: int,
        result: Optional[str],
    ) -> None:
        fs = max(min(cell_w, cell_h) / 40, 0.3)
        is_multi = result in ("TF", "FT")
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
