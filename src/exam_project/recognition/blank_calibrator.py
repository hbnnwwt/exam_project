"""空白答卷基准校准模块。

通过扫描空白答题卡，计算选择题/判断题每个气泡区域的灰度基准值，
用于后续识别时检测淡铅笔填涂痕迹。

设计要点：
- baseline 路径在每次调用时显式传入（消除 _BLANK_BASELINE_PATH 全局）
- LayoutConfig 复用 layout 模块的 dataclass
- 公共 API：compute_blank_baseline / compute_blank_baseline_multipage / save_baseline / load_baseline
- 提取辅助：get_*_baseline_dict / get_*_zone_bounds
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from .bubble_base import BubbleRecognizerBase
from .layout import LayoutAnalyzer, LayoutConfig
from .preprocess import ImagePreprocessor


# ============================================================================
# 可视化辅助
# ============================================================================


def _roi_to_png(roi_bgr: np.ndarray, max_size: int = 400) -> bytes:
    """将 ROI 转为 PNG bytes。"""
    if roi_bgr.ndim == 2:
        display = cv2.cvtColor(roi_bgr, cv2.COLOR_GRAY2BGR)
    else:
        display = roi_bgr.copy()
    h, w = display.shape[:2]
    scale = max_size / max(h, w)
    if scale < 1:
        display = cv2.resize(display, (int(w * scale), int(h * scale)))
    _, buf = cv2.imencode(".png", display)
    return buf.tobytes()


def _build_section_viz(
    gray: np.ndarray,
    fill_start: int,
    rows_n: int,
    cols_n: int,
    question_start: int,
    question_count: int,
    questions: dict,
    zone_count: int,
) -> dict:
    """为 section 构建可视化图像数据。"""
    h, w = gray.shape

    # 1. ROI + fill_start 线
    roi_viz = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    cv2.line(roi_viz, (0, fill_start), (w, fill_start), (0, 0, 255), 2)

    # 2. 网格线
    grid_viz = roi_viz.copy()
    fill_h = h - fill_start
    cell_h = fill_h / rows_n
    cell_w = w / cols_n
    for row in range(rows_n + 1):
        y = int(fill_start + row * cell_h)
        cv2.line(grid_viz, (0, y), (w, y), (0, 255, 0), 1)
    for col in range(cols_n + 1):
        x = int(col * cell_w)
        cv2.line(grid_viz, (x, fill_start), (x, h), (0, 255, 0), 1)

    # 3. 典型 cell 的 zone 边界（取第一个有效 cell）
    sample_cell_viz = None
    for q_str, data in questions.items():
        bounds = data.get("zone_bounds_rel")
        if bounds:
            q = int(q_str)
            idx = q - question_start
            row = idx // cols_n
            col = idx % cols_n
            y0 = int(fill_start + row * cell_h)
            y1 = int(fill_start + (row + 1) * cell_h)
            x0 = int(col * cell_w)
            x1 = int((col + 1) * cell_w)
            cell = gray[y0:y1, x0:x1]
            if cell.size == 0:
                continue
            cell_color = cv2.cvtColor(cell, cv2.COLOR_GRAY2BGR)
            ch, cw = cell.shape[:2]
            for i, (r0, r1) in enumerate(bounds):
                x_left = int(r0 * cw)
                x_right = int(r1 * cw)
                color = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)][i % 4]
                cv2.rectangle(
                    cell_color, (x_left, 2), (x_right, ch - 2), color, 2
                )
                cv2.putText(
                    cell_color, str(i + 1), (x_left + 2, ch - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1,
                )
            sample_cell_viz = cell_color
            break

    # 4. 统计摘要
    all_means = []
    all_stds = []
    for q_str, data in questions.items():
        for z in data.get("zones", []):
            all_means.append(z["mean"])
            all_stds.append(z["std"])

    stats_summary = {
        "mean_avg": round(float(np.mean(all_means)), 2) if all_means else 0,
        "mean_min": round(float(np.min(all_means)), 2) if all_means else 0,
        "mean_max": round(float(np.max(all_means)), 2) if all_means else 0,
        "std_avg": round(float(np.mean(all_stds)), 2) if all_stds else 0,
        "question_count": len(questions),
        "zone_count": zone_count,
    }

    return {
        "roi_image": _roi_to_png(roi_viz),
        "grid_image": _roi_to_png(grid_viz),
        "sample_cell_image": _roi_to_png(sample_cell_viz) if sample_cell_viz is not None else None,
        "stats_summary": stats_summary,
    }


# 默认布局（与 sheet_layout.json 一致）
DEFAULT_CHOICE_GRID = {"rows": 5, "cols": 5, "question_start": 1, "question_count": 25}
DEFAULT_JUDGE_GRID = {"rows": 2, "cols": 5, "question_start": 26, "question_count": 10}

# 各 section 的选项数
ZONE_COUNT_CHOICE = 4
ZONE_COUNT_JUDGE = 2


def _page_section_types(page_spec) -> list[str]:
    """兼容 _pages 的旧列表格式和新字典格式。"""
    if isinstance(page_spec, dict):
        return [
            sec.get("type")
            for sec in page_spec.get("sections", [])
            if isinstance(sec, dict) and sec.get("type")
        ]
    sections: list[str] = []
    for sec in page_spec or []:
        if isinstance(sec, dict):
            sec_type = sec.get("type")
            if sec_type:
                sections.append(sec_type)
        elif sec:
            sections.append(sec)
    return sections


def _cell_zone_gray_stats(
    cell_gray: np.ndarray,
    zone_bounds: list[tuple[int, int]],
) -> list[dict]:
    """计算一个 cell 内各 zone 的灰度均值和标准差。"""
    stats: list[dict] = []
    for zx0, zx1 in zone_bounds:
        zone = cell_gray[:, zx0:zx1]
        stats.append({
            "mean": float(np.mean(zone)),
            "std": float(np.std(zone)),
        })
    return stats


def _detect_zone_bounds(
    cell_gray: np.ndarray,
    zone_count: int,
    num_w_ratio: float = 0.20,
) -> list[tuple[float, float]]:
    """在 cell 中精确检测气泡位置，返回相对于 cell 宽度的比例边界。"""
    h, w = cell_gray.shape
    proj = 255.0 - np.mean(cell_gray, axis=0)
    window = max(3, int(w * 0.03))
    if window % 2 == 0:
        window += 1
    smooth = np.convolve(proj, np.ones(window) / window, mode="same")

    num_w = int(w * num_w_ratio)
    usable = w - num_w
    expected = [
        num_w + int((i + 0.5) * usable / zone_count)
        for i in range(zone_count)
    ]
    search = max(3, int(usable / zone_count * 0.35))

    peaks: list[int] = []
    for exp in expected:
        x0 = max(num_w, exp - search)
        x1 = min(w, exp + search)
        if x1 <= x0:
            peaks.append(exp)
            continue
        peaks.append(x0 + int(np.argmax(smooth[x0:x1])))

    bounds: list[tuple[float, float]] = []
    for i in range(zone_count):
        left = num_w if i == 0 else int((peaks[i - 1] + peaks[i]) / 2)
        right = w if i == zone_count - 1 else int((peaks[i] + peaks[i + 1]) / 2)
        bounds.append((left / w, right / w))
    return bounds


def _compute_region_baseline(
    gray: np.ndarray,
    fill_start: int,
    rows_n: int,
    cols_n: int,
    question_start: int,
    question_count: int,
    zone_count: int,
    num_w_ratio: float = 0.20,
) -> dict:
    """计算某个区域的灰度基准。"""
    img_h, img_w = gray.shape
    gray_fill = gray[fill_start:, :]
    fill_h = img_h - fill_start
    cell_h = fill_h / rows_n
    cell_w = img_w / cols_n

    questions: dict = {}
    for row in range(rows_n):
        for col in range(cols_n):
            idx = row * cols_n + col
            q = question_start + idx
            if idx >= question_count:
                continue
            y0 = int(row * cell_h)
            y1 = int((row + 1) * cell_h)
            x0 = int(col * cell_w)
            x1 = int((col + 1) * cell_w)
            cell = gray_fill[y0:y1, x0:x1]
            cell_w_pixels = x1 - x0

            zone_bounds_rel = _detect_zone_bounds(cell, zone_count, num_w_ratio)
            zone_bounds = [
                (int(r0 * cell_w_pixels), int(r1 * cell_w_pixels))
                for r0, r1 in zone_bounds_rel
            ]
            stats = _cell_zone_gray_stats(cell, zone_bounds)
            questions[str(q)] = {
                "zones": stats,
                "zone_bounds_rel": zone_bounds_rel,
            }
    return questions


def _compute_section_baseline(
    corrected: np.ndarray,
    region_box: tuple[int, int, int, int],
    section_cfg: dict,
    zone_count: int,
    num_w_ratio: float = 0.20,
) -> dict:
    """计算单个 section（choice/judge）的灰度基准。"""
    base = BubbleRecognizerBase()
    x, y, w, h = region_box
    roi = corrected[y:y + h, x:x + w]
    gray = roi if roi.ndim == 2 else cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    fill_start = base._detect_fill_start(gray)

    questions = _compute_region_baseline(
        gray, fill_start,
        section_cfg.get("rows", 5), section_cfg.get("cols", 4),
        section_cfg.get("question_start", 1),
        section_cfg.get("question_count", 20),
        zone_count=zone_count, num_w_ratio=num_w_ratio,
    )
    return {"questions": questions}


def _default_layout() -> dict:
    """返回默认 layout（与 sheet_layout.json 保持一致）。"""
    return {
        "choice": dict(DEFAULT_CHOICE_GRID),
        "judge": dict(DEFAULT_JUDGE_GRID),
    }


def compute_blank_baseline(
    image_path: str | Path,
    layout: Optional[dict] = None,
    page: int = 2,
    viz: bool = False,
) -> dict | tuple[dict, list[dict]]:
    """从空白答卷计算灰度基准。

    Args:
        viz: 为 True 时返回 (baseline, viz_pages) 元组。
    """
    if layout is None:
        layout = _default_layout()

    preprocessor = ImagePreprocessor()
    analyzer = LayoutAnalyzer(LayoutConfig.from_dict(layout))

    image = preprocessor.load(image_path)
    corrected_result = preprocessor.process(image)
    corrected = corrected_result.corrected
    binary = corrected_result.binary
    regions = analyzer.analyze(corrected, binary, page=page)

    base = BubbleRecognizerBase()
    result: dict = {}
    page_viz: dict = {"page_idx": 0, "sections": {}}

    if page == 1 and regions.choice is not None:
        ch_cfg = layout.get("choice", {})
        x, y, w, h = regions.choice
        roi = corrected[y:y + h, x:x + w]
        gray = roi if roi.ndim == 2 else cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        fill_start = base._detect_fill_start(gray)
        questions = _compute_region_baseline(
            gray, fill_start,
            ch_cfg.get("rows", 5), ch_cfg.get("cols", 4),
            ch_cfg.get("question_start", 1),
            ch_cfg.get("question_count", 20),
            zone_count=ZONE_COUNT_CHOICE, num_w_ratio=0.20,
        )
        result["choice"] = {"questions": questions}
        if viz:
            page_viz["sections"]["choice"] = _build_section_viz(
                gray, fill_start,
                ch_cfg.get("rows", 5), ch_cfg.get("cols", 4),
                ch_cfg.get("question_start", 1),
                ch_cfg.get("question_count", 20),
                questions, ZONE_COUNT_CHOICE,
            )

    if page == 2 and regions.judge is not None:
        ju_cfg = layout.get("judge", {})
        x, y, w, h = regions.judge
        roi = corrected[y:y + h, x:x + w]
        gray = roi if roi.ndim == 2 else cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        fill_start = base._detect_fill_start(gray)
        questions = _compute_region_baseline(
            gray, fill_start,
            ju_cfg.get("rows", 3), ju_cfg.get("cols", 4),
            ju_cfg.get("question_start", 21),
            ju_cfg.get("question_count", 10),
            zone_count=ZONE_COUNT_JUDGE, num_w_ratio=0.20,
        )
        result["judge"] = {"questions": questions}
        if viz:
            page_viz["sections"]["judge"] = _build_section_viz(
                gray, fill_start,
                ju_cfg.get("rows", 3), ju_cfg.get("cols", 4),
                ju_cfg.get("question_start", 21),
                ju_cfg.get("question_count", 10),
                questions, ZONE_COUNT_JUDGE,
            )

    if not result:
        raise ValueError(f"未能在空白答卷中定位识别区域 (page={page})")
    if viz:
        return result, [page_viz]
    return result


def compute_blank_baseline_multipage(
    image_paths: list[str | Path],
    layout: Optional[dict] = None,
    viz: bool = False,
) -> dict | tuple[dict, list[dict]]:
    """多页空白答卷灰度基准校准。

    逐页处理空白答题卡，自动检测各页中的 choice/judge 区域，
    聚合所有页的基准数据，按题号汇总为统一字典。

    Args:
        viz: 为 True 时返回 (baseline, viz_pages) 元组。
    """
    if layout is None:
        layout = _default_layout()

    preprocessor = ImagePreprocessor()
    analyzer = LayoutAnalyzer(LayoutConfig.from_dict(layout))

    binaries: list[np.ndarray] = []
    corrected_images: list[np.ndarray] = []
    for path in image_paths:
        image = preprocessor.load(path)
        result = preprocessor.process(image)
        binaries.append(result.binary)
        corrected_images.append(result.corrected)

    pages_config = layout.get("_pages") if isinstance(layout, dict) else None
    if pages_config:
        regions_list = analyzer.analyze_multipage(corrected_images, binaries)
    else:
        regions_list = [
            analyzer.analyze(c, b, page=idx + 1)
            for idx, (c, b) in enumerate(zip(corrected_images, binaries))
        ]

    result: dict = {"choice": {"questions": {}}, "judge": {"questions": {}}}
    viz_pages: list[dict] = []

    for page_idx, regions in enumerate(regions_list):
        if pages_config and page_idx < len(pages_config):
            expected_sections = _page_section_types(pages_config[page_idx])
        else:
            expected_sections = []
            if page_idx == 0:
                expected_sections = ["choice"]
            elif page_idx == 1:
                expected_sections = ["judge"]

        corrected = corrected_images[page_idx]
        page_viz = {"page_idx": page_idx, "sections": {}}

        for section in expected_sections:
            if section not in ("choice", "judge"):
                continue
            region_box = (
                regions.choice if section == "choice" else regions.judge
            )
            if region_box is None:
                continue

            sec_cfg = layout.get(section, {})
            zone_count = ZONE_COUNT_CHOICE if section == "choice" else ZONE_COUNT_JUDGE
            baseline = _compute_section_baseline(
                corrected, region_box, sec_cfg,
                zone_count=zone_count, num_w_ratio=0.20,
            )
            result[section]["questions"].update(baseline["questions"])

            if viz:
                x, y, w, h = region_box
                roi = corrected[y:y + h, x:x + w]
                gray = roi if roi.ndim == 2 else cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                base = BubbleRecognizerBase()
                fill_start = base._detect_fill_start(gray)
                rows_n = sec_cfg.get("rows", 5)
                cols_n = sec_cfg.get("cols", 4)
                question_start = sec_cfg.get("question_start", 1)
                question_count = sec_cfg.get("question_count", 20)
                sec_viz = _build_section_viz(
                    gray, fill_start, rows_n, cols_n,
                    question_start, question_count,
                    baseline["questions"], zone_count,
                )
                page_viz["sections"][section] = sec_viz

        if viz:
            viz_pages.append(page_viz)

    for section in ("choice", "judge"):
        if not result[section]["questions"]:
            del result[section]

    if not result:
        raise ValueError("未能在多页空白答卷中定位任何 choice/judge 识别区域")
    if viz:
        return result, viz_pages
    return result


# ============================================================================
# 序列化
# ============================================================================


def save_baseline(baseline: dict, path: str | Path) -> None:
    """保存基准数据到 JSON 文件。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_baseline(path: str | Path) -> Optional[dict]:
    """加载基准数据，不存在返回 None。"""
    path = Path(path)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# ============================================================================
# 提取辅助
# ============================================================================


def _get_baseline_means(baseline: Optional[dict], section: str) -> Optional[dict]:
    """提取某 section (choice/judge) 的 zone 均值字典。"""
    if baseline is None:
        return None
    sec = baseline.get(section, {})
    questions = sec.get("questions", {})
    result: dict = {}
    for q_str, data in questions.items():
        q = int(q_str)
        means = [z["mean"] for z in data.get("zones", [])]
        result[q] = means
    return result


def get_judge_baseline_dict(baseline: Optional[dict]) -> Optional[dict]:
    return _get_baseline_means(baseline, "judge")


def get_choice_baseline_dict(baseline: Optional[dict]) -> Optional[dict]:
    return _get_baseline_means(baseline, "choice")


def _get_baseline_zone_bounds(baseline: Optional[dict], section: str) -> Optional[dict]:
    """提取某 section 的 zone 边界相对比例。"""
    if baseline is None:
        return None
    sec = baseline.get(section, {})
    questions = sec.get("questions", {})
    result: dict = {}
    for q_str, data in questions.items():
        q = int(q_str)
        bounds = data.get("zone_bounds_rel")
        if bounds:
            result[q] = bounds
    return result


def get_judge_zone_bounds(baseline: Optional[dict]) -> Optional[dict]:
    return _get_baseline_zone_bounds(baseline, "judge")


def get_choice_zone_bounds(baseline: Optional[dict]) -> Optional[dict]:
    return _get_baseline_zone_bounds(baseline, "choice")
