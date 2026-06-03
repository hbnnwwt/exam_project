"""错题标注与得分可视化。

在旋转校正后的答题卡图片上：
- 错题/未选/多选位置画红色 X
- 各部分得分（choice/judge/essay）写在区域顶部
- 保存到输出目录

设计要点：
- option_labels 作为参数传入，消除 LAYOUT 全局依赖
- 标注函数返回 marked image，不修改原图
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import cv2
import numpy as np


# 默认选项标签（调用方未传时使用）
DEFAULT_CHOICE_LABELS = ("A", "B", "C", "D")
DEFAULT_JUDGE_LABELS = ("T", "F")


def _imwrite(path: str | Path, image: np.ndarray) -> bool:
    """支持中文路径的图像写入。自动创建父目录。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ext = path.suffix or ".png"
    ok, buf = cv2.imencode(ext, image)
    if not ok:
        return False
    with open(path, "wb") as f:
        f.write(buf.tobytes())
    return True


def _put_score(
    image: np.ndarray,
    text: str,
    region: tuple[int, int, int, int],
    color: tuple[int, int, int] = (0, 0, 255),
    font_scale: float = 1.2,
) -> None:
    """在区域正上方居中写分数（带白底）。"""
    x, y, w, h = region
    thickness = max(1, int(font_scale * 2))
    (tw, th), baseline = cv2.getTextSize(
        text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
    )
    tx = x + (w - tw) // 2
    ty = max(y - 15, th + 10)
    cv2.rectangle(
        image,
        (tx - 6, ty - th - 6),
        (tx + tw + 6, ty + baseline + 6),
        (255, 255, 255),
        -1,
    )
    cv2.putText(
        image, text, (tx, ty),
        cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness, cv2.LINE_AA,
    )


def _valid_region(region) -> bool:
    """检查 region 是否为有效的 (x, y, w, h) 序列。"""
    return (
        isinstance(region, (tuple, list))
        and len(region) == 4
        and all(isinstance(v, (int, float)) for v in region)
    )


def mark_wrong_on_page(
    page: np.ndarray,
    region: tuple[int, int, int, int],
    cell_results: list[dict],
    grading_detail: dict,
    option_labels: tuple[str, ...] = DEFAULT_CHOICE_LABELS,
    color: tuple[int, int, int] = (0, 0, 255),
    thickness: int = 3,
) -> np.ndarray:
    """在错误/多选/未选题的正确选项位置画红色 X。

    Args:
        page: 原始页面图片
        region: 选择题/判断题区域 (x, y, w, h)
        cell_results: 单元格识别结果列表，每个 dict 含 question / zone_bounds / cell_bounds
        grading_detail: 评分结果 {题号: {'correct': ..., 'given': ..., 'score': ...}}
        option_labels: 选项标签列表
        color: ×颜色
        thickness: ×线条粗细
    """
    if not _valid_region(region):
        return page.copy()
    marked = page.copy()
    rx, ry = region[0], region[1]

    for cell in cell_results:
        q_num = cell.get("question")
        if q_num is None or q_num not in grading_detail:
            continue
        detail = grading_detail[q_num]
        given = detail.get("given")
        correct = detail.get("correct")
        score = detail.get("score", 0)

        is_wrong = score == 0
        is_blank = given is None or given == ""
        is_multi = given is not None and len(given) > 1
        if not (is_wrong or is_blank or is_multi):
            continue
        if correct is None:
            continue

        zone_bounds = cell.get("zone_bounds", [])
        for opt in correct:
            if opt not in option_labels:
                continue
            option_idx = option_labels.index(opt)
            if option_idx >= len(zone_bounds):
                continue
            zx0, zx1 = zone_bounds[option_idx]
            y0, y1, x0, _ = cell["cell_bounds"]

            bx1 = rx + x0 + zx0
            by1 = ry + y0
            bx2 = rx + x0 + zx1
            by2 = ry + y1

            zone_w = bx2 - bx1
            zone_h = by2 - by1
            x_len = int(min(zone_w, zone_h) * 0.5)
            cx = (bx1 + bx2) // 2
            cy = (by1 + by2) // 2
            pad = x_len // 2
            # 白色描边
            cv2.line(marked, (cx - pad, cy - pad), (cx + pad, cy + pad),
                    (255, 255, 255), thickness + 1)
            cv2.line(marked, (cx - pad, cy + pad), (cx + pad, cy - pad),
                    (255, 255, 255), thickness + 1)
            # 红色×
            cv2.line(marked, (cx - pad, cy - pad), (cx + pad, cy + pad),
                    color, thickness)
            cv2.line(marked, (cx - pad, cy + pad), (cx + pad, cy - pad),
                    color, thickness)

    return marked


def mark_and_save(
    student_id: Optional[str],
    page1: np.ndarray,
    page2: Optional[np.ndarray],
    regions1: dict,
    regions2: dict,
    choice_cells: list[dict],
    judge_cells: list[dict],
    grading_result: dict,
    choice_max: int,
    judge_max: int,
    essay_max: int,
    output_dir: str | Path = "data/processed",
    choice_labels: tuple[str, ...] = DEFAULT_CHOICE_LABELS,
    judge_labels: tuple[str, ...] = DEFAULT_JUDGE_LABELS,
) -> tuple[str, str, np.ndarray, np.ndarray]:
    """标注两页错题、写上各部分得分并保存。

    Args:
        student_id: 学号（None 或含 ? 时用 unknown）
        page1, page2: 第1/2页原图
        regions1, regions2: 两页区域 dict（含 choice/judge/essay 键）
        choice_cells, judge_cells: 单元格识别结果
        grading_result: 评分汇总
        choice_max/judge_max/essay_max: 各部分满分
        output_dir: 输出目录
        choice_labels, judge_labels: 选项标签

    Returns:
        (p1_path, p2_path, marked_p1, marked_p2)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    sid = (student_id or "unknown").replace("?", "_")

    cs = grading_result.get("choice_total", 0)
    js = grading_result.get("judge_total", 0)
    es = grading_result.get("essay_total", 0)

    marked_p1 = page1.copy()
    if regions1.get("choice") and choice_cells:
        marked_p1 = mark_wrong_on_page(
            marked_p1, regions1["choice"], choice_cells,
            grading_result.get("choice", {}), choice_labels,
        )
        _put_score(marked_p1, f"Choice: {cs}/{choice_max}", regions1["choice"])

    if page2 is not None:
        marked_p2 = page2.copy()
    else:
        marked_p2 = np.zeros_like(page1)
    if page2 is not None and regions2.get("judge") and judge_cells:
        marked_p2 = mark_wrong_on_page(
            marked_p2, regions2["judge"], judge_cells,
            grading_result.get("judge", {}), judge_labels,
        )
        _put_score(marked_p2, f"Judge: {js}/{judge_max}", regions2["judge"])

    if _valid_region(regions2.get("essay")):
        _put_score(marked_p2, f"Essay: {es}/{essay_max}", regions2["essay"])

    p1_path = output_dir / f"{sid}_page1_marked.png"
    p2_path = output_dir / f"{sid}_page2_marked.png"
    # 防止学号重复覆盖
    for suffix in range(100):
        if not p1_path.exists() and not p2_path.exists():
            break
        p1_path = output_dir / f"{sid}_page1_marked_{suffix}.png"
        p2_path = output_dir / f"{sid}_page2_marked_{suffix}.png"
    _imwrite(p1_path, marked_p1)
    _imwrite(p2_path, marked_p2)

    return str(p1_path), str(p2_path), marked_p1, marked_p2
