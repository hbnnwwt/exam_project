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
from .layout import LayoutAnalyzer
from .preprocess import ImagePreprocessor


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
) -> dict:
    """从空白答卷计算灰度基准。"""
    if layout is None:
        layout = _default_layout()

    preprocessor = ImagePreprocessor()
    analyzer = LayoutAnalyzer()

    image = preprocessor.load(image_path)
    preprocessor.process(image)  # 验证图像能处理；下面用 corrected
    corrected_result = preprocessor.process(image)
    corrected = corrected_result.corrected
    binary = corrected_result.binary
    regions = analyzer.analyze(corrected, binary, page=page)

    base = BubbleRecognizerBase()
    result: dict = {}

    if page == 1 and regions.choice is not None:
        ch_cfg = layout.get("choice", {})
        x, y, w, h = regions.choice
        roi = corrected[y:y + h, x:x + w]
        gray = roi if roi.ndim == 2 else cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        fill_start = base._detect_fill_start(gray)
        result["choice"] = {
            "questions": _compute_region_baseline(
                gray, fill_start,
                ch_cfg.get("rows", 5), ch_cfg.get("cols", 4),
                ch_cfg.get("question_start", 1),
                ch_cfg.get("question_count", 20),
                zone_count=ZONE_COUNT_CHOICE, num_w_ratio=0.20,
            )
        }

    if page == 2 and regions.judge is not None:
        ju_cfg = layout.get("judge", {})
        x, y, w, h = regions.judge
        roi = corrected[y:y + h, x:x + w]
        gray = roi if roi.ndim == 2 else cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        fill_start = base._detect_fill_start(gray)
        result["judge"] = {
            "questions": _compute_region_baseline(
                gray, fill_start,
                ju_cfg.get("rows", 3), ju_cfg.get("cols", 4),
                ju_cfg.get("question_start", 21),
                ju_cfg.get("question_count", 10),
                zone_count=ZONE_COUNT_JUDGE, num_w_ratio=0.20,
            )
        }

    if not result:
        raise ValueError(f"未能在空白答卷中定位识别区域 (page={page})")
    return result


def compute_blank_baseline_multipage(
    image_paths: list[str | Path],
    layout: Optional[dict] = None,
) -> dict:
    """多页空白答卷灰度基准校准。

    逐页处理空白答题卡，自动检测各页中的 choice/judge 区域，
    聚合所有页的基准数据，按题号汇总为统一字典。
    """
    if layout is None:
        layout = _default_layout()

    preprocessor = ImagePreprocessor()
    analyzer = LayoutAnalyzer()

    images: list[np.ndarray] = []
    binaries: list[np.ndarray] = []
    corrected_images: list[np.ndarray] = []
    for path in image_paths:
        image = preprocessor.load(path)
        result = preprocessor.process(image)
        images.append(image)
        binaries.append(result.binary)
        corrected_images.append(result.corrected)

    pages_config = layout.get("_pages") if isinstance(layout, dict) else None
    if pages_config:
        regions_list = analyzer.analyze_multipage(images, binaries)
    else:
        regions_list = [
            analyzer.analyze(c, b, page=idx + 1)
            for idx, (c, b) in enumerate(zip(corrected_images, binaries))
        ]

    result: dict = {"choice": {"questions": {}}, "judge": {"questions": {}}}

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

    for section in ("choice", "judge"):
        if not result[section]["questions"]:
            del result[section]

    if not result:
        raise ValueError("未能在多页空白答卷中定位任何 choice/judge 识别区域")
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
