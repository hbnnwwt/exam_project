"""将 AnswerSheetConfig 导出为 backward-compatible 的 sheet_layout.json 格式。

旧识别器期望的 sheet_layout.json 结构：
- student_id: { digit_count }
- choice: { rows, cols, question_start, question_count, options }
- judge: 同上
- layout: { pageN_fallback: { section: [y_start, y_end] } }
- scoring: { choice_score, judge_score, essay_max_score }
- _pages: 新版多页 LayoutAnalyzer 输入
"""

from __future__ import annotations

import math
from typing import Any, Optional

from .components import (
    ChoiceComponent,
    Component,
    EssayComponent,
    JudgeComponent,
    SolutionComponent,
    StudentIdComponent,
)
from .layout_engine import paginate, page_content_height
from .schema import AnswerSheetConfig, SectionConfig


# 历史兼容：每行 5 题（A4 / B5 都用此值）
COLS_PER_ROW = 5


def _merge_sections(
    sections: list[SectionConfig], paper_size: str
) -> Optional[dict[str, Any]]:
    """将多个同类型 section 合并为 old-format 的单一字典。"""
    if not sections:
        return None
    total_count = sum(s.question_count for s in sections)
    question_start = min(s.question_start for s in sections)
    cols = COLS_PER_ROW
    rows = math.ceil(total_count / cols)
    options = sections[0].options
    return {
        "rows": rows,
        "cols": cols,
        "question_start": question_start,
        "question_count": total_count,
        "options": options,
    }


def _build_old_format(
    cfg: AnswerSheetConfig,
) -> tuple[Optional[dict], Optional[dict], Optional[dict]]:
    """构建 old-format 的 student_id, choice, judge 字典。"""
    student_id: Optional[dict] = None
    choice_sections: list[SectionConfig] = []
    judge_sections: list[SectionConfig] = []

    for page_cfg in cfg.pages:
        for sec in page_cfg.sections:
            if sec.type == "student_id" and student_id is None:
                student_id = {"digit_count": sec.digit_count}
            elif sec.type == "choice":
                choice_sections.append(sec)
            elif sec.type == "judge":
                judge_sections.append(sec)

    choice = _merge_sections(choice_sections, cfg.meta.paper_size)
    judge = _merge_sections(judge_sections, cfg.meta.paper_size)
    return student_id, choice, judge


def _build_fallback_layout(
    cfg: AnswerSheetConfig,
) -> dict[str, dict[str, list[float]]]:
    """为每页计算 fallback 的相对 y 范围。"""
    paper_size = cfg.meta.paper_size
    pages = paginate(cfg)
    layout: dict[str, dict[str, list[float]]] = {}

    for page in pages:
        page_net_height = page_content_height(paper_size, page.page_number)
        page_key = f"page{page.page_number}_fallback"
        page_fallback: dict[str, list[float]] = {}
        cumulative_y = 0.0
        for comp in page.components:
            height = comp.estimate_height(paper_size)
            before_gap = (
                comp._before_gap_height() if isinstance(comp, Component) else 0.0
            )
            bottom_gap = (
                comp._bottom_gap_height() if isinstance(comp, Component) else 0.0
            )
            rel_start = round((cumulative_y + before_gap) / page_net_height, 4)
            # rel_end 不应包含底部 margin，因为检测器定位的是 section border-box，
            # 而 CSS margin-bottom 不属于 border-box，也不会被轮廓检测合并。
            rel_end = round(
                (cumulative_y + max(height - bottom_gap, before_gap)) / page_net_height, 4
            )
            cumulative_y += height
            rel_start = max(0.0, min(1.0, rel_start))
            rel_end = max(0.0, min(1.0, rel_end))

            key = _section_key(comp)
            if key is None:
                continue

            if key in page_fallback:
                existing = page_fallback[key]
                page_fallback[key] = [
                    min(existing[0], rel_start),
                    max(existing[1], rel_end),
                ]
            else:
                page_fallback[key] = [rel_start, rel_end]

        if page_fallback:
            layout[page_key] = page_fallback
    return layout


def _section_key(comp: Component) -> Optional[str]:
    """把 Component 映射为 fallback 字典的 key。"""
    if isinstance(comp, StudentIdComponent):
        return "student_id"
    if isinstance(comp, ChoiceComponent):
        return "choice"
    if isinstance(comp, JudgeComponent):
        return "judge"
    if isinstance(comp, EssayComponent):
        return "essay"
    if isinstance(comp, SolutionComponent):
        return "solution"
    return None


def _build_pages_field(cfg: AnswerSheetConfig) -> list[dict[str, Any]]:
    """构建 _pages 字段（描述 paginate 后的实际分页结果）。"""
    pages_field: list[dict[str, Any]] = []
    pages = paginate(cfg)
    for page in pages:
        sections: list[dict[str, Any]] = []
        for comp in page.components:
            if isinstance(comp, StudentIdComponent):
                sections.append({
                    "type": "student_id",
                    "digit_count": comp.config.digit_count,
                })
                continue
            sec = getattr(comp, "config", None)
            if not isinstance(sec, SectionConfig):
                continue
            sec_dict: dict[str, Any] = {
                "type": sec.type,
                "question_start": sec.question_start,
                "question_count": sec.question_count,
            }
            if sec.title is not None:
                sec_dict["title"] = sec.title
            if sec.options is not None:
                sec_dict["options"] = sec.options
            if sec.lines_per_question is not None:
                sec_dict["lines_per_question"] = sec.lines_per_question
            if sec.before_gap_mm:
                sec_dict["before_gap_mm"] = sec.before_gap_mm
            sections.append(sec_dict)
        pages_field.append({
            "page_number": page.page_number,
            "sections": sections,
        })
    return pages_field


def _build_scoring(cfg: AnswerSheetConfig) -> dict[str, float]:
    """从 section 配置中提取 scoring 字段。"""
    choice_score: Optional[float] = None
    judge_score: Optional[float] = None
    essay_max_score = 0.0

    for page_cfg in cfg.pages:
        for sec in page_cfg.sections:
            if sec.type == "choice" and choice_score is None:
                choice_score = (
                    sec.score if sec.score is not None
                    else (sec.scores[0] if sec.scores else None)
                )
            elif sec.type == "judge" and judge_score is None:
                judge_score = (
                    sec.score if sec.score is not None
                    else (sec.scores[0] if sec.scores else None)
                )
            elif sec.type == "essay":
                if sec.scores is not None:
                    essay_max_score += sum(sec.scores)
                elif sec.score is not None:
                    essay_max_score += sec.score * sec.question_count

    return {
        "choice_score": choice_score if choice_score is not None else 3.0,
        "judge_score": judge_score if judge_score is not None else 2.0,
        "essay_max_score": essay_max_score if essay_max_score > 0 else 20.0,
    }


def export_sheet_layout(cfg: AnswerSheetConfig) -> dict:
    """将 AnswerSheetConfig 导出为 sheet_layout.json 兼容格式。"""
    student_id, choice, judge = _build_old_format(cfg)
    fallback_layout = _build_fallback_layout(cfg)
    pages_field = _build_pages_field(cfg)
    scoring = _build_scoring(cfg)

    result: dict[str, Any] = {
        "layout": fallback_layout,
        "scoring": scoring,
        "_pages": pages_field,
    }
    if student_id is not None:
        result["student_id"] = student_id
    if choice is not None:
        result["choice"] = choice
    if judge is not None:
        result["judge"] = judge
    return result
