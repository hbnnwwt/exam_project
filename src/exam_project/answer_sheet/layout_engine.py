"""答题卡分页布局引擎。"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import List, Optional

from .components import (
    ChoiceComponent,
    Component,
    EssayComponent,
    JudgeComponent,
    SolutionComponent,
    StudentIdComponent,
)
from .schema import AnswerSheetConfig, SectionConfig


# 纸张尺寸（mm）
PAGE_SIZES = {
    "A4": {"width": 210, "height": 297, "usable_width": 190, "usable_height": 277},
    "B5": {"width": 176, "height": 250, "usable_width": 156, "usable_height": 230},
}

PAGE_CONTENT_HEIGHT = {"A4": 215, "B5": 175}
PAGE_CONTENT_HEIGHT_WITHOUT_NOTICE = {"A4": 230, "B5": 188}
HEADER_ESTIMATE = {"A4": 62, "B5": 55}


class LayoutError(Exception):
    """布局错误：某个 section 在单页内无法容纳且不可拆分。"""


def page_content_height(paper_size: str, page_number: int) -> float:
    """返回指定页的可用内容高度（mm）。第 1 页含 notice，后续页不含。"""
    if page_number <= 1:
        return PAGE_CONTENT_HEIGHT[paper_size]
    return PAGE_CONTENT_HEIGHT_WITHOUT_NOTICE[paper_size]


@dataclass
class Page:
    """分页结果中的一页。"""

    page_number: int
    components: list[Component] = field(default_factory=list)

    def add_component(self, comp: Component) -> None:
        self.components.append(comp)

    def total_content_height(self, paper_size: str) -> float:
        return sum(comp.estimate_height(paper_size) for comp in self.components)


def _create_component(section: SectionConfig) -> Component:
    """根据 SectionConfig 创建对应的 Component 子类实例。"""
    if section.type == "choice":
        return ChoiceComponent(section)
    if section.type == "judge":
        return JudgeComponent(section)
    if section.type == "essay":
        return EssayComponent(section)
    if section.type == "solution":
        return SolutionComponent(section)
    if section.type == "student_id":
        return StudentIdComponent(section)
    raise ValueError(f"未知的 section 类型: {section.type}")


def paginate(cfg: AnswerSheetConfig) -> list[Page]:
    """将 AnswerSheetConfig 分页为 List[Page]。

    算法：
    1. 根据纸张尺寸获取每页可用净高度
    2. 收集 cfg.pages 中所有 section，保留用户声明的顺序
    3. 逐个尝试放入当前页；若放不下则尝试 split；
       若 split 失败则开新页；若单页净高仍不够则抛 LayoutError
    4. y_offset 不由引擎计算，由 CSS 在渲染时确定
    """
    paper_size = cfg.meta.paper_size
    if paper_size not in PAGE_SIZES:
        raise ValueError(f"不支持的纸张尺寸: {paper_size}")

    pages: list[Page] = []
    current_page = Page(page_number=1)
    current_used = 0.0

    all_sections: list[SectionConfig] = []
    for page_cfg in cfg.pages:
        all_sections.extend(page_cfg.sections)

    for section in all_sections:
        comp = _create_component(section)
        comp_height = comp.estimate_height(paper_size)

        while True:
            page_net_height = page_content_height(paper_size, current_page.page_number)
            if comp_height <= page_net_height - current_used:
                current_page.add_component(comp)
                current_used += comp_height
                break

            split_result = comp.split(page_net_height - current_used, paper_size)
            if split_result is None:
                if current_used > 0:
                    remaining = page_net_height - current_used
                    pages.append(current_page)
                    current_page = Page(page_number=len(pages) + 1)
                    current_used = 0.0
                    # 题前间距跨页连续计算：减去上一页已提供的空间
                    gap = comp._before_gap_height()
                    if gap > 0 and remaining > 0:
                        new_gap = max(0.0, gap - remaining)
                        section = replace(section, before_gap_mm=new_gap)
                        comp = _create_component(section)
                        comp_height = comp.estimate_height(paper_size)
                    continue
                raise LayoutError(
                    f"Section {section.type} (题号 {section.question_start}~"
                    f"{section.question_start + section.question_count - 1}) "
                    f"高度 {comp_height:.1f}mm 超过单页净高度 {page_net_height:.1f}mm，"
                    f"且不可拆分。"
                )

            first_part, second_part = split_result
            first_height = first_part.estimate_height(paper_size)
            current_page.add_component(first_part)
            current_used += first_height

            remaining = page_net_height - current_used
            pages.append(current_page)
            current_page = Page(page_number=len(pages) + 1)
            current_used = 0.0
            # 题前间距跨页连续计算：减去上一页已提供的空间
            gap = second_part._before_gap_height()
            if gap > 0 and remaining > 0:
                new_gap = max(0.0, gap - remaining)
                second_section = replace(second_part.config, before_gap_mm=new_gap)
                second_part = _create_component(second_section)
            comp = second_part
            comp_height = comp.estimate_height(paper_size)

    if current_page.components:
        pages.append(current_page)

    for idx, page in enumerate(pages, start=1):
        page.page_number = idx

    return pages
