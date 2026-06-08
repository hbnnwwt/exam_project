"""答题卡渲染组件。"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any, Optional, Tuple

from .schema import SectionConfig, StudentIdConfig

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
    def render(self, page_num: int, y_offset_mm: float, paper_size: str = "A4") -> str:
        """渲染为 HTML 字符串。"""

    @abstractmethod
    def split(
        self, available_height: float, paper_size: str = "A4"
    ) -> Optional[Tuple["Component", "Component"]]:
        """尝试在 available_height 处拆分为两个组件。

        返回 (first_part, remaining_part) 或 None（不可拆分）。
        """

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
        """返回普通题型说明行占用高度。

        SectionConfig.instruction 的语义是：None 使用默认说明，"" 隐藏说明，
        非空字符串显示自定义说明。因此只有空字符串不占高度。
        """
        return 0.0 if getattr(self.config, "instruction", None) == "" else SECTION_INSTRUCTION_MM

    def _before_gap_height(self) -> float:
        return float(getattr(self.config, "before_gap_mm", 0.0) or 0.0)

    def _bottom_gap_height(self) -> float:
        """返回组件底部 margin（SECTION_GAP_MM），对应 CSS margin-bottom。"""
        return SECTION_GAP_MM

    def _before_gap_html(self) -> str:
        gap = self._before_gap_height()
        if gap <= 0:
            return ""
        return f'<div class="section-before-gap" style="height: {gap:g}mm"></div>\n'

    def _section_fixed_height(self) -> float:
        """普通 section 除内容网格/列表以外的打印流高度。"""
        return (
            self._before_gap_height()
            + SECTION_TITLE_MM
            + self._section_instruction_height()
            + SECTION_BORDER_MM
            + SECTION_GAP_MM
        )

    def _bubble_grid_height(self, rows: int) -> float:
        if rows <= 0:
            return 0.0
        return rows * BUBBLE_MM + max(0, rows - 1) * GRID_GAP_MM + GRID_BOTTOM_MM

    def _max_bubble_rows_for_height(self, available_height: float) -> int:
        usable = available_height - self._section_fixed_height() - GRID_BOTTOM_MM
        if usable < BUBBLE_MM:
            return 0
        return int((usable + GRID_GAP_MM) // (BUBBLE_MM + GRID_GAP_MM))

    def _answer_item_height(self, lines_per_question: int) -> float:
        if lines_per_question <= 0:
            return 0.0
        return (
            lines_per_question * ANSWER_LINE_MM
            + max(0, lines_per_question - 1) * ANSWER_LINE_GAP_MM
        )

    def _answer_list_height(self, question_count: int, lines_per_question: int) -> float:
        if question_count <= 0:
            return 0.0
        return (
            question_count * self._answer_item_height(lines_per_question)
            + max(0, question_count - 1) * ANSWER_ITEM_GAP_MM
            + GRID_BOTTOM_MM
        )

    def _max_answer_questions_for_height(
        self, available_height: float, lines_per_question: int
    ) -> int:
        item_height = self._answer_item_height(lines_per_question)
        usable = available_height - self._section_fixed_height() - GRID_BOTTOM_MM
        if usable < item_height:
            return 0
        return int((usable + ANSWER_ITEM_GAP_MM) // (item_height + ANSWER_ITEM_GAP_MM))


class StudentIdComponent(Component):
    """学号填涂区域组件。

    优先接受 SectionConfig(type="student_id", digit_count=...)；
    向后兼容：仍可接受 StudentIdConfig（仅含 digit_count）。
    """

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        # 兼容两种来源：SectionConfig.digit_count 或 StudentIdConfig.digit_count
        if hasattr(config, "digit_count") and isinstance(getattr(config, "digit_count"), int):
            self.digit_count = config.digit_count
        else:
            raise ValueError(
                "StudentIdComponent 需要 digit_count 字段（来自 SectionConfig 或 StudentIdConfig）"
            )

    def estimate_height(self, paper_size: str = "A4") -> float:
        # Matches print CSS: section box ~100.5mm plus the following section gap.
        return self._before_gap_height() + 105.5

    def render(self, page_num: int, y_offset_mm: float = 0.0, paper_size: str = "A4") -> str:
        cells: list[str] = []
        # 第1行：手写学号格
        for _ in range(self.digit_count):
            cells.append('<div class="sid-cell sid-write-cell"></div>')
        # 数字行 0-9：每格内含带数字的 OMR 圆形框
        for d in range(10):
            for _ in range(self.digit_count):
                cells.append(f'<div class="sid-cell"><span class="sid-omr">{d}</span></div>')

        html = f'''{self._before_gap_html()}<section class="student-id-section">
  <div class="sid-title">准考证号</div>
  <div class="sid-instruction">请用 2B 铅笔将对应数字涂黑</div>
  <div class="sid-grid" style="grid-template-columns: repeat({self.digit_count}, 1fr);">
    {'\n    '.join(cells)}
  </div>
</section>'''
        return html

    def split(
        self, available_height: float, paper_size: str = "A4"
    ) -> Optional[Tuple["Component", "Component"]]:
        return None


class ChoiceComponent(Component):
    """选择题区域组件。"""

    def __init__(self, config: SectionConfig) -> None:
        super().__init__(config)
        self.question_start = config.question_start
        self.question_count = config.question_count
        self.options = config.options or []
        self.score = config.score
        self.scores = config.scores

    def estimate_height(self, paper_size: str = "A4") -> float:
        cols = self._cols_for_paper(paper_size)
        rows = math.ceil(self.question_count / cols)
        return self._section_fixed_height() + self._bubble_grid_height(rows)

    def render(self, page_num: int, y_offset_mm: float, paper_size: str = "A4") -> str:
        cols = self._cols_for_paper(paper_size)
        questions_html: list[str] = []
        for i in range(self.question_count):
            q_num = self.question_start + i
            options_html = "".join(f'<span class="opt">{opt}</span>' for opt in self.options)
            questions_html.append(
                f'<div class="q-item">'
                f'<span class="q-num">{q_num:02d}.</span>{options_html}'
                f'</div>'
            )

        score_label = ""
        if self.scores is not None:
            if len(set(self.scores)) == 1:
                score_label = f"，每题 {self.scores[0]} 分"
            else:
                score_label = "，逐题赋分"
        elif self.score is not None:
            score_label = f"，每题 {self.score} 分"
        title = self.config.title or f"选择题（第 {self.question_start}~{self.question_start + self.question_count - 1} 题{score_label}）"

        # 新增：instruction 渲染
        from .html_renderer import resolve_instruction
        instruction_html = ""
        resolved = resolve_instruction("choice", self.config.instruction)
        if resolved:
            instruction_html = f'\n  <div class="sec-instruction">{resolved}</div>'

        # 关键：去掉 absolute 定位，不再用 y_offset
        html = f'''{self._before_gap_html()}<section class="choice-section">
  <div class="sec-title">{title}</div>{instruction_html}
  <div class="choice-grid" style="grid-template-columns: repeat({cols}, 1fr)">
    {'\n    '.join(questions_html)}
  </div>
</section>
'''
        return html

    def split(
        self, available_height: float, paper_size: str = "A4"
    ) -> Optional[Tuple["Component", "Component"]]:
        needed = self.estimate_height(paper_size)
        if needed <= available_height:
            return None

        cols = self._cols_for_paper(paper_size)
        max_rows = self._max_bubble_rows_for_height(available_height)
        max_questions = max_rows * cols

        if max_questions < 1:
            return None
        if max_questions >= self.question_count:
            return None

        first_count = max_questions
        second_count = self.question_count - first_count

        first_scores = None
        second_scores = None
        if self.scores is not None:
            first_scores = self.scores[:first_count]
            second_scores = self.scores[first_count:]

        first_cfg = SectionConfig(
            type="choice",
            question_start=self.question_start,
            question_count=first_count,
            title=self.config.title,
            options=list(self.options),
            score=self.score,
            scores=first_scores,
            instruction=self.config.instruction,
            before_gap_mm=0.0,
        )
        second_cfg = SectionConfig(
            type="choice",
            question_start=self.question_start + first_count,
            question_count=second_count,
            title=self.config.title,
            options=list(self.options),
            score=self.score,
            scores=second_scores,
            instruction=self.config.instruction,
            before_gap_mm=self.config.before_gap_mm,
        )
        return (ChoiceComponent(first_cfg), ChoiceComponent(second_cfg))


class JudgeComponent(Component):
    """判断题区域组件。"""

    def __init__(self, config: SectionConfig) -> None:
        super().__init__(config)
        self.question_start = config.question_start
        self.question_count = config.question_count
        self.options = config.options or ["T", "F"]
        self.score = config.score
        self.scores = config.scores

    def estimate_height(self, paper_size: str = "A4") -> float:
        cols = self._cols_for_paper(paper_size)
        rows = math.ceil(self.question_count / cols)
        return self._section_fixed_height() + self._bubble_grid_height(rows)

    def render(self, page_num: int, y_offset_mm: float, paper_size: str = "A4") -> str:
        cols = self._cols_for_paper(paper_size)
        questions_html: list[str] = []
        for i in range(self.question_count):
            q_num = self.question_start + i
            options_html = "".join(f'<span class="opt">{opt}</span>' for opt in self.options)
            questions_html.append(
                f'<div class="q-item">'
                f'<span class="q-num">{q_num:02d}.</span>{options_html}'
                f'</div>'
            )

        score_label = ""
        if self.scores is not None:
            if len(set(self.scores)) == 1:
                score_label = f"，每题 {self.scores[0]} 分"
            else:
                score_label = "，逐题赋分"
        elif self.score is not None:
            score_label = f"，每题 {self.score} 分"
        title = self.config.title or f"判断题（第 {self.question_start}~{self.question_start + self.question_count - 1} 题{score_label}）"

        # instruction 渲染
        from .html_renderer import resolve_instruction
        instruction_html = ""
        resolved = resolve_instruction("judge", self.config.instruction)
        if resolved:
            instruction_html = f'\n  <div class="sec-instruction">{resolved}</div>'

        # 去掉 absolute 定位
        html = f'''{self._before_gap_html()}<section class="judge-section">
  <div class="sec-title">{title}</div>{instruction_html}
  <div class="judge-grid" style="grid-template-columns: repeat({cols}, 1fr)">
    {'\n    '.join(questions_html)}
  </div>
</section>
'''
        return html

    def split(
        self, available_height: float, paper_size: str = "A4"
    ) -> Optional[Tuple["Component", "Component"]]:
        needed = self.estimate_height(paper_size)
        if needed <= available_height:
            return None

        cols = self._cols_for_paper(paper_size)
        max_rows = self._max_bubble_rows_for_height(available_height)
        max_questions = max_rows * cols

        if max_questions < 1:
            return None
        if max_questions >= self.question_count:
            return None

        first_count = max_questions
        second_count = self.question_count - first_count

        first_scores = None
        second_scores = None
        if self.scores is not None:
            first_scores = self.scores[:first_count]
            second_scores = self.scores[first_count:]

        first_cfg = SectionConfig(
            type="judge",
            question_start=self.question_start,
            question_count=first_count,
            title=self.config.title,
            options=list(self.options),
            score=self.score,
            scores=first_scores,
            instruction=self.config.instruction,
            before_gap_mm=0.0,
        )
        second_cfg = SectionConfig(
            type="judge",
            question_start=self.question_start + first_count,
            question_count=second_count,
            title=self.config.title,
            options=list(self.options),
            score=self.score,
            scores=second_scores,
            instruction=self.config.instruction,
            before_gap_mm=self.config.before_gap_mm,
        )
        return (JudgeComponent(first_cfg), JudgeComponent(second_cfg))


class EssayComponent(Component):
    """简答题/填空题区域组件。"""

    def __init__(self, config: SectionConfig) -> None:
        super().__init__(config)
        self.question_start = config.question_start
        self.question_count = config.question_count
        self.lines_per_question = config.lines_per_question or 1
        self.score = config.score
        self.scores = config.scores

    def estimate_height(self, paper_size: str = "A4") -> float:
        return self._section_fixed_height() + self._answer_list_height(
            self.question_count, self.lines_per_question
        )

    def render(self, page_num: int, y_offset_mm: float, paper_size: str = "A4") -> str:
        questions_html: list[str] = []
        for i in range(self.question_count):
            q_num = self.question_start + i
            lines_html = "\n    ".join('<div class="essay-line"></div>' for _ in range(self.lines_per_question))
            questions_html.append(
                f'<div class="essay-item">\n'
                f'  <div class="essay-label">{q_num:02d}.</div>\n'
                f'  <div class="essay-lines">\n    {lines_html}\n  </div>\n'
                f'</div>'
            )

        score_label = ""
        if self.scores is not None:
            if len(set(self.scores)) == 1:
                score_label = f"，每题 {self.scores[0]} 分"
            else:
                score_label = "，逐题赋分"
        elif self.score is not None:
            score_label = f"，每题 {self.score} 分"
        title = self.config.title or f"简答题（第 {self.question_start}~{self.question_start + self.question_count - 1} 题{score_label}）"

        # instruction 渲染
        from .html_renderer import resolve_instruction
        instruction_html = ""
        resolved = resolve_instruction("essay", self.config.instruction)
        if resolved:
            instruction_html = f'\n  <div class="sec-instruction">{resolved}</div>'

        # 去掉 absolute 定位
        html = f'''{self._before_gap_html()}<section class="essay-section">
  <div class="sec-title">{title}</div>{instruction_html}
  <div class="essay-list">
    {'\n    '.join(questions_html)}
  </div>
</section>
'''
        return html

    def split(
        self, available_height: float, paper_size: str = "A4"
    ) -> Optional[Tuple["Component", "Component"]]:
        needed = self.estimate_height(paper_size)
        if needed <= available_height:
            return None

        max_questions = self._max_answer_questions_for_height(
            available_height, self.lines_per_question
        )
        if max_questions < 1:
            return None
        if max_questions >= self.question_count:
            return None

        first_count = max_questions
        second_count = self.question_count - first_count

        first_scores = None
        second_scores = None
        if self.scores is not None:
            first_scores = self.scores[:first_count]
            second_scores = self.scores[first_count:]

        first_cfg = SectionConfig(
            type="essay",
            question_start=self.question_start,
            question_count=first_count,
            title=self.config.title,
            lines_per_question=self.lines_per_question,
            score=self.score,
            scores=first_scores,
            instruction=self.config.instruction,
            before_gap_mm=0.0,
        )
        second_cfg = SectionConfig(
            type="essay",
            question_start=self.question_start + first_count,
            question_count=second_count,
            title=self.config.title,
            lines_per_question=self.lines_per_question,
            score=self.score,
            scores=second_scores,
            instruction=self.config.instruction,
            before_gap_mm=self.config.before_gap_mm,
        )
        return (EssayComponent(first_cfg), EssayComponent(second_cfg))


class SolutionComponent(Component):
    """解答题区域组件：保留书写空间，但不绘制横线。"""

    def __init__(self, config: SectionConfig) -> None:
        super().__init__(config)
        self.question_start = config.question_start
        self.question_count = config.question_count
        self.lines_per_question = config.lines_per_question or 1
        self.score = config.score
        self.scores = config.scores

    def _blank_item_height(self) -> float:
        if self.lines_per_question <= 0:
            return 0.0
        return self.lines_per_question * ANSWER_LINE_MM

    def _blank_list_height(self) -> float:
        if self.question_count <= 0:
            return 0.0
        return (
            self.question_count * self._blank_item_height()
            + max(0, self.question_count - 1) * ANSWER_ITEM_GAP_MM
            + GRID_BOTTOM_MM
        )

    def _max_blank_questions_for_height(self, available_height: float) -> int:
        item_height = self._blank_item_height()
        usable = available_height - self._section_fixed_height() - GRID_BOTTOM_MM
        if usable < item_height:
            return 0
        return int((usable + ANSWER_ITEM_GAP_MM) // (item_height + ANSWER_ITEM_GAP_MM))

    def estimate_height(self, paper_size: str = "A4") -> float:
        return self._section_fixed_height() + self._blank_list_height()

    def render(self, page_num: int, y_offset_mm: float, paper_size: str = "A4") -> str:
        questions_html: list[str] = []
        for i in range(self.question_count):
            q_num = self.question_start + i
            height_mm = self._blank_item_height()
            questions_html.append(
                f'<div class="solution-item">\n'
                f'  <div class="solution-label">{q_num:02d}.</div>\n'
                f'  <div class="solution-box" style="min-height: {height_mm}mm"></div>\n'
                f'</div>'
            )

        score_label = ""
        if self.scores is not None:
            if len(set(self.scores)) == 1:
                score_label = f"，每题 {self.scores[0]} 分"
            else:
                score_label = "，逐题赋分"
        elif self.score is not None:
            score_label = f"，每题 {self.score} 分"
        title = self.config.title or (
            f"解答题（第 {self.question_start}~"
            f"{self.question_start + self.question_count - 1} 题{score_label}）"
        )

        from .html_renderer import resolve_instruction
        instruction_html = ""
        resolved = resolve_instruction("solution", self.config.instruction)
        if resolved:
            instruction_html = f'\n  <div class="sec-instruction">{resolved}</div>'

        html = f'''{self._before_gap_html()}<section class="solution-section">
  <div class="sec-title">{title}</div>{instruction_html}
  <div class="solution-list">
    {'\n    '.join(questions_html)}
  </div>
</section>
'''
        return html

    def split(
        self, available_height: float, paper_size: str = "A4"
    ) -> Optional[Tuple["Component", "Component"]]:
        needed = self.estimate_height(paper_size)
        if needed <= available_height:
            return None

        max_questions = self._max_blank_questions_for_height(available_height)
        if max_questions < 1:
            return None
        if max_questions >= self.question_count:
            return None

        first_count = max_questions
        second_count = self.question_count - first_count

        first_scores = None
        second_scores = None
        if self.scores is not None:
            first_scores = self.scores[:first_count]
            second_scores = self.scores[first_count:]

        first_cfg = SectionConfig(
            type="solution",
            question_start=self.question_start,
            question_count=first_count,
            title=self.config.title,
            lines_per_question=self.lines_per_question,
            score=self.score,
            scores=first_scores,
            instruction=self.config.instruction,
            before_gap_mm=0.0,
        )
        second_cfg = SectionConfig(
            type="solution",
            question_start=self.question_start + first_count,
            question_count=second_count,
            title=self.config.title,
            lines_per_question=self.lines_per_question,
            score=self.score,
            scores=second_scores,
            instruction=self.config.instruction,
            before_gap_mm=self.config.before_gap_mm,
        )
        return (SolutionComponent(first_cfg), SolutionComponent(second_cfg))
