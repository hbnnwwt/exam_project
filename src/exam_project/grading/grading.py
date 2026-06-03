"""评分服务。

将识别结果与标准答案比对，生成评分报告。
消除 LAYOUT 全局依赖：题型分类从传入的 layout 参数推导。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

import openpyxl

from exam_project.recognition.types import RecognizeResult


# 默认分值
DEFAULT_CHOICE_SCORE = 3
DEFAULT_JUDGE_SCORE = 2
DEFAULT_ESSAY_MAX_SCORE = 20


def classify_question(q_num: int, layout: dict) -> str:
    """根据题号 + 布局判断题型。

    Args:
        q_num: 题号
        layout: dict 含 'choice' / 'judge' 子 dict（每题有 question_start / question_count）
    """
    for q_type in ("choice", "judge"):
        cfg = layout.get(q_type, {})
        start = cfg.get("question_start", 0)
        count = cfg.get("question_count", 0)
        if start and count and start <= q_num <= start + count - 1:
            return q_type
    return "essay"


class EssayGraderBase:
    """简答题评分器抽象基类。子类需实现 score()。"""

    def score(
        self,
        question: int,
        reference: str,
        student_answer: Union[str, RecognizeResult],
        max_score: float,
    ) -> tuple[float, float, str]:
        raise NotImplementedError


class DefaultEssayGrader(EssayGraderBase):
    """默认实现：简答题返回 0 分，标注需手动评分。"""

    def score(
        self,
        question: int,
        reference: str,
        student_answer: Union[str, RecognizeResult],
        max_score: float,
    ) -> tuple[float, float, str]:
        if isinstance(student_answer, RecognizeResult):
            if student_answer.is_system_failure:
                return 0.0, max_score, (
                    f"系统失败: {student_answer.error or student_answer.status}"
                )
            if not (student_answer.text and student_answer.text.strip()):
                return 0.0, max_score, "未作答"
        return 0.0, max_score, "需手动评分"


@dataclass(frozen=True)
class GradingConfig:
    """评分配置。"""

    choice_score: int = DEFAULT_CHOICE_SCORE
    judge_score: int = DEFAULT_JUDGE_SCORE
    essay_max_score: int = DEFAULT_ESSAY_MAX_SCORE

    @classmethod
    def from_layout(cls, layout: dict) -> "GradingConfig":
        scoring = layout.get("scoring", {}) if isinstance(layout, dict) else {}
        return cls(
            choice_score=int(scoring.get("choice_score", DEFAULT_CHOICE_SCORE)),
            judge_score=int(scoring.get("judge_score", DEFAULT_JUDGE_SCORE)),
            essay_max_score=int(scoring.get("essay_max_score", DEFAULT_ESSAY_MAX_SCORE)),
        )


@dataclass(frozen=True)
class GradingResult:
    """单次评分完整结果。"""

    choice: dict[int, dict] = field(default_factory=dict)
    judge: dict[int, dict] = field(default_factory=dict)
    essay_detail: dict[int, dict] = field(default_factory=dict)
    essay: dict[int, RecognizeResult] = field(default_factory=dict)
    essay_status: dict[int, str] = field(default_factory=dict)
    choice_total: float = 0.0
    judge_total: float = 0.0
    essay_total: float = 0.0

    @property
    def total(self) -> float:
        return self.choice_total + self.judge_total + self.essay_total


class GradingService:
    """评分服务：识别结果与标准答案比对。"""

    def __init__(
        self,
        answer_key: dict,
        layout: Optional[dict] = None,
        essay_grader: Optional[EssayGraderBase] = None,
        config: Optional[GradingConfig] = None,
    ) -> None:
        self.answer_key = answer_key
        self.layout = layout or {}
        self.essay_grader = essay_grader or DefaultEssayGrader()
        if config is None:
            config = GradingConfig.from_layout(self.layout)
        self.config = config

    # ----------------------------------------------------- max

    @property
    def max_total(self) -> float:
        """动态计算满分。"""
        n_choice = len(self.answer_key.get("choice", {}))
        n_judge = len(self.answer_key.get("judge", {}))
        n_essay = len(self.answer_key.get("essay", {}))
        return (
            n_choice * self.config.choice_score
            + n_judge * self.config.judge_score
            + n_essay * self.config.essay_max_score
        )

    # ----------------------------------------------------- factory

    @classmethod
    def from_xlsx(cls, path: str | Path) -> "GradingService":
        """从 参考答案.xlsx 加载标准答案。"""
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        answer_key: dict = {"choice": {}, "judge": {}, "essay": {}}
        # 暂用默认 layout 推断题型（无法在加载阶段知道 question_start/count）
        # 提供一个合理的默认 layout 假设
        placeholder_layout = {
            "choice": {"question_start": 1, "question_count": 100},  # 上限
            "judge": {"question_start": 21, "question_count": 100},
        }
        for col in range(2, ws.max_column + 1):
            q_num = ws.cell(row=1, column=col).value
            answer = ws.cell(row=2, column=col).value
            if q_num is None or answer is None:
                continue
            try:
                q_num = int(q_num)
            except (ValueError, TypeError):
                continue
            q_type = classify_question(q_num, placeholder_layout)
            answer_key[q_type][q_num] = answer
        return cls(answer_key, layout=placeholder_layout)

    # ----------------------------------------------------- grading

    def grade(self, recognized_answers: dict) -> GradingResult:
        choice_detail, choice_total = self._grade_choice(recognized_answers)
        judge_detail, judge_total = self._grade_judge(recognized_answers)
        essay_detail, essay_status, essay_total, essay_results = (
            self._grade_essay(recognized_answers)
        )
        return GradingResult(
            choice=choice_detail,
            judge=judge_detail,
            essay_detail=essay_detail,
            essay=essay_results,
            essay_status=essay_status,
            choice_total=choice_total,
            judge_total=judge_total,
            essay_total=essay_total,
        )

    def _grade_choice(self, recognized: dict) -> tuple[dict[int, dict], float]:
        detail: dict[int, dict] = {}
        total = 0.0
        for q in sorted(self.answer_key.get("choice", {})):
            correct = self.answer_key["choice"].get(q)
            given = recognized.get("choice", {}).get(q)
            score = self.config.choice_score if given is not None and given == correct else 0.0
            detail[q] = {"correct": correct, "given": given, "score": score}
            total += score
        return detail, total

    def _grade_judge(self, recognized: dict) -> tuple[dict[int, dict], float]:
        detail: dict[int, dict] = {}
        total = 0.0
        for q in sorted(self.answer_key.get("judge", {})):
            correct = self.answer_key["judge"].get(q)
            given = recognized.get("judge", {}).get(q)
            score = self.config.judge_score if given is not None and given == correct else 0.0
            detail[q] = {"correct": correct, "given": given, "score": score}
            total += score
        return detail, total

    def _grade_essay(
        self,
        recognized: dict,
    ) -> tuple[dict[int, dict], dict[int, str], float, dict[int, RecognizeResult]]:
        detail: dict[int, dict] = {}
        status: dict[int, str] = {}
        total = 0.0
        results: dict[int, RecognizeResult] = {}
        blank = RecognizeResult(text="", status="blank")
        for q, ref_text in self.answer_key.get("essay", {}).items():
            student = recognized.get("essay", {}).get(q, blank)
            # 向后兼容：旧调用方可能传字符串
            if not isinstance(student, RecognizeResult):
                student = RecognizeResult(
                    text=student or "",
                    status="blank" if not (student and str(student).strip()) else "ok",
                )
            s, mx, fb = self.essay_grader.score(q, ref_text, student, self.config.essay_max_score)
            detail[q] = {
                "score": s, "max_score": mx, "feedback": fb,
                "status": student.status, "error": student.error,
            }
            status[q] = student.status
            results[q] = student
            total += s
        return detail, status, total, results

    # ----------------------------------------------------- reporting

    def generate_report(self, result: GradingResult) -> str:
        """生成可读评分报告。"""
        lines = [f"总分: {result.total}/{self.max_total}", ""]

        n_choice = len(self.answer_key.get("choice", {}))
        n_judge = len(self.answer_key.get("judge", {}))
        choice_correct = sum(1 for d in result.choice.values() if d["score"] > 0)
        lines.append(
            f"选择题: {choice_correct}/{n_choice} "
            f"({choice_correct * self.config.choice_score}分)"
        )
        for q in sorted(result.choice):
            d = result.choice[q]
            mark = "✅" if d["score"] > 0 else "❌"
            lines.append(
                f"  第{q}题: {d['given'] or '未答'} (正确:{d['correct']}) {mark}"
            )

        judge_correct = sum(1 for d in result.judge.values() if d["score"] > 0)
        lines.append(
            f"判断题: {judge_correct}/{n_judge} "
            f"({judge_correct * self.config.judge_score}分)"
        )
        for q in sorted(result.judge):
            d = result.judge[q]
            mark = "✅" if d["score"] > 0 else "❌"
            lines.append(
                f"  第{q}题: {d['given'] or '未答'} (正确:{d['correct']}) {mark}"
            )

        if result.essay_detail:
            n_essay = len(self.answer_key.get("essay", {}))
            lines.append(
                f"简答题: {result.essay_total}/{n_essay * self.config.essay_max_score}分"
            )
            for q in sorted(result.essay_detail):
                d = result.essay_detail[q]
                lines.append(f"  第{q}题: {d['score']}/{d['max_score']}分 — {d['feedback']}")
        return "\n".join(lines)

    # ----------------------------------------------------- xlsx export

    def save_result_xlsx(
        self,
        template_path: str | Path,
        output_path: str | Path,
        student_results: list[tuple[Optional[str], dict]],
    ) -> None:
        """按结果.xlsx 模板格式输出。"""
        wb = openpyxl.load_workbook(template_path)
        ws = wb.active
        next_row = ws.max_row + 1

        for student_id, rec in student_results:
            ws.cell(row=next_row, column=1, value=student_id)
            choice_scores: list[float] = []
            judge_scores: list[float] = []
            for col in range(2, ws.max_column + 1):
                q_num = ws.cell(row=1, column=col).value
                if q_num is None:
                    continue
                try:
                    q_num = int(q_num)
                except (ValueError, TypeError):
                    continue
                q_type = classify_question(q_num, self.layout)
                if q_type == "choice":
                    ans = rec.get("choice", {}).get(q_num)
                    ws.cell(row=next_row, column=col, value=ans)
                    correct = self.answer_key["choice"].get(q_num)
                    score = self.config.choice_score if ans and ans == correct else 0
                    choice_scores.append(score)
                elif q_type == "judge":
                    ans = rec.get("judge", {}).get(q_num)
                    ws.cell(row=next_row, column=col, value=ans)
                    correct_j = self.answer_key["judge"].get(q_num)
                    score = self.config.judge_score if ans and ans == correct_j else 0
                    judge_scores.append(score)
            next_row += 1

            ws.cell(row=next_row, column=1, value=f"{student_id}_score")
            col_idx = 2
            for s in choice_scores:
                ws.cell(row=next_row, column=col_idx, value=s)
                col_idx += 1
            for s in judge_scores:
                ws.cell(row=next_row, column=col_idx, value=s)
                col_idx += 1
            if choice_scores:
                c0 = openpyxl.utils.get_column_letter(2)
                c1 = openpyxl.utils.get_column_letter(2 + len(choice_scores) - 1)
                ws.cell(
                    row=next_row, column=33,
                    value=f"=SUM({c0}{next_row}:{c1}{next_row})",
                )
            else:
                ws.cell(row=next_row, column=33, value=0)
            if judge_scores:
                j0 = openpyxl.utils.get_column_letter(2 + len(choice_scores))
                j1 = openpyxl.utils.get_column_letter(
                    2 + len(choice_scores) + len(judge_scores) - 1
                )
                ws.cell(
                    row=next_row, column=34,
                    value=f"=SUM({j0}{next_row}:{j1}{next_row})",
                )
            else:
                ws.cell(row=next_row, column=34, value=0)
            next_row += 1

        wb.save(output_path)
