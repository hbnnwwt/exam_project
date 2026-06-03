"""答题卡渲染组件。

每个 Section 对应一个 Component 子类，负责：
- estimate_height: 估算打印占用高度（mm）
- render: 输出 HTML 字符串
- split: 跨页时拆分为两个 Component

设计要点：
- Component 抽象基类定义三件套接口
- 子类各自实现 estimate_height / render / split
- 拆分的判断与实现与原版一致
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional, Tuple

from .schema import SectionConfig


# 排版常量（mm）
SECTION_GAP_MM = 5.0
SECTION_BORDER_MM = 0.6
SECTION_TITLE_MM = 9.5
SECTION_INSTRUCTION_MM = 6.0
GRID_BOTTOM_MM = 2.0
BUBBLE_MM = 5.5
GRID_GAP_MM = 3.0
ANSWER_LINE_MM = 8.0
ANSWER_LINE_GAP_MM = 2.0
ANSWER_ITEM_GAP_MM = 3.0


class Component(ABC):
    """答题卡组件抽象基类。"""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    def estimate_height(self, paper_size: str = "A4") -> float:
        """估算组件在指定纸张上占用的毫米高度。"""

    @abstractmethod
    def render(
        self, page_num: int, y_offset_mm: float, paper_size: str = "A4",
    ) -> str:
        """渲染为 HTML 字符串。"""

    @abstractmethod
    def split(
        self, available_height: float, paper_size: str = "A4",
    ) -> Optional[Tuple["Component", "Component"]]:
        """尝试在 available_height 处拆分为两个组件。

        返回 (first_part, remaining_part) 或 None（不可拆分）。
        """

    # ----------------------------------------------------- 通用工具

    def _cols_for_paper(self, paper_size: str) -> int:
        """根据选项数量自动计算每行可容纳的题数。"""
        options = getattr(self, "options", None)
        if options is None:
            return 4
        n = len(options)
        if n <= 2:
            return 5
        if n <= 4:
            return 4
        if n <= 6:
            return 3
        return 2

    def _section_instruction_height(self) -> float:
        """返回普通题型说明行占用高度。"""
        return 0.0 if getattr(self.config, "instruction", None) == "" else SECTION_INSTRUCTION_MM

    def _before_gap_height(self) -> float:
        return float(getattr(self.config, "before_gap_mm", 0.0) or 0.0)

    def _before_gap_html(self) -> str:
        gap = self._before_gap_height()
        if gap <= 0:
            return ""
        return f'<div class="section-before-gap" style="height: {gap:g}mm"></div>\n'

    def _section_fixed_height(self) -> float:
        """section 除内容网格/列表以外的固定高度。"""
        return (
            self._before_gap_height()
            + SECTION_TITLE_MM
            + self._section_instruction_height()
            + SECTION_BORDER_MM * 2
        )


# ============================================================================
# 共享 HTML 片段
# ============================================================================


def _section_header_html(title: str, q_start: int, q_count: int, section_type: str) -> str:
    """section 标题行。"""
    label = f"第 {q_start} - {q_start + q_count - 1} 题" if q_count > 0 else ""
    return (
        f'<div class="section-title">'
        f'<span class="section-name">{title}</span>'
        f'<span class="section-range">{label}</span>'
        f'<span class="section-type" data-type="{section_type}"></span>'
        f'</div>'
    )


def _grid_html(cells: list[dict], cols: int, paper_size: str) -> str:
    """把 cells 渲染为 N 列的网格。"""
    parts: list[str] = []
    for i, cell in enumerate(cells):
        if i > 0 and i % cols == 0:
            parts.append('<div class="grid-row-break"></div>')
        parts.append(_cell_html(cell))
    return '<div class="bubble-grid">' + ''.join(parts) + '</div>'


def _cell_html(cell: dict) -> str:
    """单个 cell（题号 + 选项气泡）。"""
    q_label = cell.get("q_label", "")
    options = cell.get("options", [])
    bubbles = ''.join(
        f'<span class="bubble" data-option="{o}"></span>' for o in options
    )
    return f'<div class="bubble-cell"><span class="q-label">{q_label}</span>{bubbles}</div>'


# ============================================================================
# 具体组件
# ============================================================================


class ChoiceComponent(Component):
    """选择题组件。"""

    def __init__(self, config: SectionConfig) -> None:
        super().__init__(config)
        self.options = config.options or ["A", "B", "C", "D"]

    def estimate_height(self, paper_size: str = "A4") -> float:
        cols = self._cols_for_paper(paper_size)
        n_rows = (self.config.question_count + cols - 1) // cols
        grid_height = SECTION_BORDER_MM * 2 + BUBBLE_MM * n_rows + GRID_GAP_MM * (n_rows - 1)
        return self._section_fixed_height() + grid_height + GRID_BOTTOM_MM

    def render(
        self, page_num: int, y_offset_mm: float, paper_size: str = "A4",
    ) -> str:
        title = self.config.title or "选择题"
        cols = self._cols_for_paper(paper_size)
        cells: list[dict] = []
        for i in range(self.config.question_count):
            q = self.config.question_start + i
            cells.append({"q_label": str(q), "options": self.options})
        header = _section_header_html(
            title, self.config.question_start, self.config.question_count, "choice",
        )
        grid = _grid_html(cells, cols, paper_size)
        before = self._before_gap_html()
        return (
            f'<div class="section section-choice" data-page="{page_num}" '
            f'data-y="{y_offset_mm:g}">'
            f'{before}{header}{grid}</div>'
        )

    def split(
        self, available_height: float, paper_size: str = "A4",
    ) -> Optional[Tuple["Component", "Component"]]:
        if self.config.question_count <= 1:
            return None
        cols = self._cols_for_paper(paper_size)
        # 估算当前页能放几行
        grid_per_row = SECTION_BORDER_MM * 2 + BUBBLE_MM + GRID_GAP_MM
        rows_avail = int((available_height - self._section_fixed_height() - GRID_BOTTOM_MM) // (BUBBLE_MM + GRID_GAP_MM))
        if rows_avail < 1:
            return None
        first_count = min(self.config.question_count, rows_avail * cols)
        if first_count <= 0 or first_count >= self.config.question_count:
            return None
        first_cfg = SectionConfig(
            type="choice",
            question_start=self.config.question_start,
            question_count=first_count,
            options=self.options,
            score=self.config.score,
            scores=(self.config.scores[:first_count] if self.config.scores else None),
            title=self.config.title,
            instruction=self.config.instruction,
        )
        second_cfg = SectionConfig(
            type="choice",
            question_start=self.config.question_start + first_count,
            question_count=self.config.question_count - first_count,
            options=self.options,
            score=self.config.score,
            scores=(self.config.scores[first_count:] if self.config.scores else None),
            title=self.config.title,
            instruction=self.config.instruction,
        )
        return ChoiceComponent(first_cfg), ChoiceComponent(second_cfg)


class JudgeComponent(ChoiceComponent):
    """判断题组件（结构同 ChoiceComponent，但 options 固定为 T/F）。"""

    def __init__(self, config: SectionConfig) -> None:
        super().__init__(config)
        # 强制覆盖 options（schema 已经校验过）
        self.options = ["T", "F"]


class EssayComponent(Component):
    """简答题组件。"""

    def estimate_height(self, paper_size: str = "A4") -> float:
        n = self.config.lines_per_question or 1
        per_q = ANSWER_LINE_MM * n + ANSWER_LINE_GAP_MM * (n - 1) + ANSWER_ITEM_GAP_MM
        return self._section_fixed_height() + per_q * self.config.question_count + GRID_BOTTOM_MM

    def render(
        self, page_num: int, y_offset_mm: float, paper_size: str = "A4",
    ) -> str:
        title = self.config.title or "简答题"
        header = _section_header_html(
            title, self.config.question_start, self.config.question_count, "essay",
        )
        items: list[str] = []
        for i in range(self.config.question_count):
            q = self.config.question_start + i
            lines = '<div class="answer-line"></div>' * (self.config.lines_per_question or 1)
            items.append(f'<div class="essay-item" data-q="{q}">{lines}</div>')
        before = self._before_gap_html()
        return (
            f'<div class="section section-essay" data-page="{page_num}" '
            f'data-y="{y_offset_mm:g}">'
            f'{before}{header}<div class="essay-items">'
            f'{"".join(items)}</div></div>'
        )

    def split(
        self, available_height: float, paper_size: str = "A4",
    ) -> Optional[Tuple["Component", "Component"]]:
        if self.config.question_count <= 1:
            return None
        per_q = (
            ANSWER_LINE_MM * (self.config.lines_per_question or 1)
            + ANSWER_LINE_GAP_MM * max((self.config.lines_per_question or 1) - 1, 0)
            + ANSWER_ITEM_GAP_MM
        )
        usable = available_height - self._section_fixed_height() - GRID_BOTTOM_MM
        first_count = int(usable // per_q)
        if first_count < 1 or first_count >= self.config.question_count:
            return None
        first_cfg = SectionConfig(
            type="essay",
            question_start=self.config.question_start,
            question_count=first_count,
            score=self.config.score,
            scores=(self.config.scores[:first_count] if self.config.scores else None),
            title=self.config.title,
            lines_per_question=self.config.lines_per_question,
            instruction=self.config.instruction,
        )
        second_cfg = SectionConfig(
            type="essay",
            question_start=self.config.question_start + first_count,
            question_count=self.config.question_count - first_count,
            score=self.config.score,
            scores=(self.config.scores[first_count:] if self.config.scores else None),
            title=self.config.title,
            lines_per_question=self.config.lines_per_question,
            instruction=self.config.instruction,
        )
        return EssayComponent(first_cfg), EssayComponent(second_cfg)


class SolutionComponent(EssayComponent):
    """解答题组件（与简答题结构相同）。"""

    def render(
        self, page_num: int, y_offset_mm: float, paper_size: str = "A4",
    ) -> str:
        title = self.config.title or "解答题"
        header = _section_header_html(
            title, self.config.question_start, self.config.question_count, "solution",
        )
        items: list[str] = []
        for i in range(self.config.question_count):
            q = self.config.question_start + i
            lines = '<div class="answer-line"></div>' * (self.config.lines_per_question or 1)
            items.append(f'<div class="solution-item" data-q="{q}">{lines}</div>')
        before = self._before_gap_html()
        return (
            f'<div class="section section-solution" data-page="{page_num}" '
            f'data-y="{y_offset_mm:g}">'
            f'{before}{header}<div class="solution-items">'
            f'{"".join(items)}</div></div>'
        )


class StudentIdComponent(Component):
    """学号填涂组件。"""

    def estimate_height(self, paper_size: str = "A4") -> float:
        cols = self.config.digit_count or 10
        grid = SECTION_BORDER_MM * 2 + BUBBLE_MM * 2 + GRID_GAP_MM
        return self._section_fixed_height() + grid + GRID_BOTTOM_MM

    def render(
        self, page_num: int, y_offset_mm: float, paper_size: str = "A4",
    ) -> str:
        digit_count = self.config.digit_count or 10
        cells: list[dict] = []
        for d in range(10):
            cells.append({"q_label": str(d), "options": ["."] * digit_count})
        header = _section_header_html(
            "学号", 0, 0, "student_id",
        )
        # 学号行：每列对应一个数字位（0-9），每行是一组（题号 + N 个气泡）
        grid = _grid_html(cells, cols=1, paper_size=paper_size)
        before = self._before_gap_html()
        return (
            f'<div class="section section-student-id" data-page="{page_num}" '
            f'data-digits="{digit_count}" data-y="{y_offset_mm:g}">'
            f'{before}{header}{grid}</div>'
        )

    def split(
        self, available_height: float, paper_size: str = "A4",
    ) -> Optional[Tuple["Component", "Component"]]:
        return None  # 学号不可拆分
