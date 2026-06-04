"""试卷分析模块。

从 grading_results.json 加载批量批改结果，生成：
- 班级报告：平均分、中位数、标准差、分数段分布
- 题目统计：每题正确率、平均得分率、区分度
- 学生排名：总分排序

不依赖 Pydantic，使用纯 dict 传递数据。
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


# 默认分数段（百分制）
DEFAULT_SCORE_RANGES = [
    (90, 100, "90-100 (优秀)"),
    (80, 89, "80-89 (良好)"),
    (70, 79, "70-79 (中等)"),
    (60, 69, "60-69 (及格)"),
    (0, 59, "0-59 (不及格)"),
]


@dataclass
class QuestionStats:
    """单题统计"""

    question_id: str = ""
    total_students: int = 0
    correct_count: int = 0
    correct_rate: float = 0.0
    avg_score: float = 0.0
    avg_score_rate: float = 0.0
    max_score: float = 0.0
    blank_count: int = 0
    discrimination_index: Optional[float] = None
    difficulty_level: float = 0.0
    is_anomalous: bool = False
    anomaly_reason: str = ""


@dataclass
class ScoreDistribution:
    """分数段分布"""

    range_label: str = ""
    min_score: float = 0.0
    max_score: float = 0.0
    count: int = 0
    percentage: float = 0.0


@dataclass
class ClassReport:
    """班级报告"""

    total_students: int = 0
    average_score: float = 0.0
    median_score: float = 0.0
    std_score: float = 0.0
    max_score: float = 0.0
    min_score: float = 0.0
    full_mark: float = 0.0
    score_distribution: list[ScoreDistribution] = field(default_factory=list)
    question_stats: list[QuestionStats] = field(default_factory=list)
    student_ranking: list[dict[str, Any]] = field(default_factory=list)
    anomalous_questions: list[QuestionStats] = field(default_factory=list)


class ExamAnalyzer:
    """试卷分析器"""

    GROUP_RATIO = 0.27  # 高分组/低分组比例（取前27%和后27%）
    LOW_CORRECT_RATE_THRESHOLD = 0.2
    HIGH_BLANK_RATE_THRESHOLD = 0.3

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.students = data.get("students", [])
        self.answer_key = data.get("answer_key", {})
        self.config = data.get("config", {})

    @classmethod
    def from_json(cls, path: str | Path) -> "ExamAnalyzer":
        """从 JSON 文件加载。"""
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    def generate_report(self) -> ClassReport:
        """生成完整班级报告。"""
        if not self.students:
            return ClassReport()

        scores = [s["total_score"] for s in self.students]
        full_mark = self.students[0].get("max_score", 100.0) if self.students else 100.0

        average_score = statistics.mean(scores)
        median_score = statistics.median(scores)
        std_score = statistics.stdev(scores) if len(scores) > 1 else 0.0

        score_distribution = self._compute_score_distribution(scores, full_mark)
        question_stats = self._compute_question_stats()
        student_ranking = self._compute_student_ranking()
        anomalous = [q for q in question_stats if q.is_anomalous]

        return ClassReport(
            total_students=len(self.students),
            average_score=round(average_score, 2),
            median_score=round(median_score, 2),
            std_score=round(std_score, 2),
            max_score=max(scores),
            min_score=min(scores),
            full_mark=full_mark,
            score_distribution=score_distribution,
            question_stats=question_stats,
            student_ranking=student_ranking,
            anomalous_questions=anomalous,
        )

    def _compute_score_distribution(
        self, scores: list[float], max_score: float
    ) -> list[ScoreDistribution]:
        """计算分数段分布。"""
        total = len(scores)
        distributions = []
        for low, high, label in DEFAULT_SCORE_RANGES:
            count = sum(1 for s in scores if low <= s <= high)
            distributions.append(
                ScoreDistribution(
                    range_label=label,
                    min_score=low,
                    max_score=high,
                    count=count,
                    percentage=round(count / total if total > 0 else 0.0, 2),
                )
            )
        return distributions

    def _compute_question_stats(self) -> list[QuestionStats]:
        """计算每题统计。"""
        # 收集所有题号（从 answer_key 和 student detail 中）
        all_qids: set[str] = set()
        for s in self.students:
            for key in ("choice_detail", "judge_detail", "essay_detail"):
                all_qids.update(str(k) for k in s.get(key, {}).keys())

        # 按题型分组获取满分
        def max_score_for(qid: str) -> float:
            if qid in self.answer_key.get("choice", {}):
                return self.config.get("choice_score", 3)
            if qid in self.answer_key.get("judge", {}):
                return self.config.get("judge_score", 2)
            if qid in self.answer_key.get("essay", {}):
                return self.config.get("essay_max_score", 20)
            return 0.0

        # 准备高分组和低分组（按总分排序）
        sorted_students = sorted(self.students, key=lambda s: s["total_score"], reverse=True)
        n = max(1, int(len(sorted_students) * self.GROUP_RATIO))
        high_group = sorted_students[:n]
        low_group = sorted_students[-n:]

        stats = []
        for qid in sorted(all_qids, key=lambda x: int(x) if x.isdigit() else x):
            scores = []
            correct = 0
            blank = 0
            max_s = max_score_for(qid)

            for s in self.students:
                score = None
                for key in ("choice_detail", "judge_detail", "essay_detail"):
                    detail = s.get(key, {})
                    if qid in detail:
                        score = detail[qid].get("score", 0)
                        given = detail[qid].get("given", "")
                        if score == max_s and max_s > 0:
                            correct += 1
                        if given is None or given == "":
                            blank += 1
                        break
                if score is not None:
                    scores.append(score)

            total = len(scores)
            avg = statistics.mean(scores) if scores else 0.0
            rate = avg / max_s if max_s > 0 else 0.0
            correct_rate = correct / total if total > 0 else 0.0
            blank_rate = blank / total if total > 0 else 0.0

            discrimination = self._compute_discrimination(qid, high_group, low_group, max_s)

            is_anomalous = False
            reasons = []
            if correct_rate < self.LOW_CORRECT_RATE_THRESHOLD:
                is_anomalous = True
                reasons.append(f"正确率极低({correct_rate:.1%})")
            if blank_rate > self.HIGH_BLANK_RATE_THRESHOLD:
                is_anomalous = True
                reasons.append(f"空白率过高({blank_rate:.1%})")

            stats.append(
                QuestionStats(
                    question_id=qid,
                    total_students=total,
                    correct_count=correct,
                    correct_rate=round(correct_rate, 2),
                    avg_score=round(avg, 2),
                    avg_score_rate=round(rate, 2),
                    max_score=max_s,
                    blank_count=blank,
                    discrimination_index=round(discrimination, 3) if discrimination is not None else None,
                    difficulty_level=round(rate, 2),
                    is_anomalous=is_anomalous,
                    anomaly_reason="; ".join(reasons),
                )
            )
        return stats

    def _compute_discrimination(
        self, qid: str, high_group: list[dict], low_group: list[dict], max_score: float
    ) -> Optional[float]:
        """计算区分度：高分组得分率 - 低分组得分率。"""
        if max_score == 0 or not high_group or not low_group:
            return None

        def group_rate(group: list[dict]) -> float:
            scores = []
            for s in group:
                for key in ("choice_detail", "judge_detail", "essay_detail"):
                    detail = s.get(key, {})
                    if qid in detail:
                        scores.append(detail[qid].get("score", 0))
                        break
            return statistics.mean(scores) / max_score if scores else 0.0

        return group_rate(high_group) - group_rate(low_group)

    def _compute_student_ranking(self) -> list[dict[str, Any]]:
        """学生总分排名。"""
        ranked = sorted(
            self.students, key=lambda s: s["total_score"], reverse=True
        )
        return [
            {
                "rank": i + 1,
                "student_id": s.get("student_id", f"unknown_{i}"),
                "total_score": s["total_score"],
                "max_score": s.get("max_score", 0),
                "score_rate": round(s["total_score"] / s.get("max_score", 1), 2)
                if s.get("max_score", 0) > 0
                else 0.0,
            }
            for i, s in enumerate(ranked)
        ]
