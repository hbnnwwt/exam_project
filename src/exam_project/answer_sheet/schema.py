"""答题卡生成器的配置模型与校验。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any, Optional


# ============================================================================
# 配置 dataclass
# ============================================================================


@dataclass
class MetaConfig:
    """答题卡元信息配置。"""

    title: str = "标准化考试答题卡"
    paper_size: str = "A4"
    numbering_mode: str = "continuous"  # "continuous" | "per_section"

    def __post_init__(self) -> None:
        if self.paper_size not in {"A4", "B5"}:
            raise ValueError(f"paper_size 必须是 A4 或 B5，当前为: {self.paper_size}")
        if self.numbering_mode not in {"continuous", "per_section"}:
            raise ValueError(
                f"numbering_mode 必须是 continuous 或 per_section，"
                f"当前为: {self.numbering_mode}"
            )


@dataclass
class StudentIdConfig:
    """学号填涂区域配置。"""

    digit_count: int = 10

    def __post_init__(self) -> None:
        if not (6 <= self.digit_count <= 14):
            raise ValueError(
                f"digit_count 必须在 6 到 14 之间，当前为: {self.digit_count}"
            )


@dataclass
class SectionConfig:
    """答题卡上的一个题型区块配置。"""

    type: str
    question_start: int
    question_count: int
    before_gap_mm: float = 0.0
    title: Optional[str] = None
    options: Optional[list[str]] = None
    score: Optional[float] = None
    scores: Optional[list[float]] = None
    lines_per_question: Optional[int] = None
    digit_count: Optional[int] = None
    instruction: Optional[str] = None

    VALID_TYPES = frozenset({"choice", "judge", "essay", "solution", "student_id"})

    def __post_init__(self) -> None:
        try:
            self.before_gap_mm = float(self.before_gap_mm)
        except (TypeError, ValueError) as exc:
            raise ValueError("before_gap_mm 必须是数字") from exc
        if not (0.0 <= self.before_gap_mm <= 30.0):
            raise ValueError(
                f"before_gap_mm 必须在 0 到 30 之间，当前为: {self.before_gap_mm}"
            )

        if self.type not in self.VALID_TYPES:
            raise ValueError(
                f"type 必须是 choice、judge、essay、solution 或 student_id，"
                f"当前为: {self.type}"
            )

        if self.type == "student_id":
            if self.digit_count is None:
                raise ValueError("type=student_id 时必须提供 digit_count")
            if not (6 <= self.digit_count <= 14):
                raise ValueError(
                    f"digit_count 必须在 6 到 14 之间，当前为: {self.digit_count}"
                )
        else:
            if self.question_start < 1:
                raise ValueError(f"question_start 必须 >= 1，当前为: {self.question_start}")
            if self.question_count < 1:
                raise ValueError(f"question_count 必须 >= 1，当前为: {self.question_count}")

        if self.type != "student_id":
            if (self.score is not None and self.scores is not None) or (
                self.score is None and self.scores is None
            ):
                raise ValueError("score 和 scores 必须且只能设置其中一个")

        if self.scores is not None and len(self.scores) != self.question_count:
            raise ValueError(
                f"scores 的长度 ({len(self.scores)}) "
                f"必须等于 question_count ({self.question_count})"
            )

        if self.type in {"choice", "judge"}:
            if self.options is None or len(self.options) < 2:
                raise ValueError(
                    f"{self.type} 类型的 options 必须至少包含 2 个选项"
                )

        if self.type == "judge":
            if self.options != ["T", "F"]:
                raise ValueError(
                    f"judge 类型的 options 必须是 ['T', 'F']，当前为: {self.options}"
                )

        if self.type in {"essay", "solution"}:
            if self.lines_per_question is None or self.lines_per_question < 1:
                raise ValueError(
                    f"{self.type} 类型的 lines_per_question 必须 >= 1，"
                    f"当前为: {self.lines_per_question}"
                )

    def get_score_for_question(self, q_idx: int) -> float:
        """获取第 q_idx 题（从 1 开始）的分数。"""
        if not (1 <= q_idx <= self.question_count):
            raise IndexError(f"题号 {q_idx} 超出范围 [1, {self.question_count}]")
        if self.scores is not None:
            return self.scores[q_idx - 1]
        if self.score is not None:
            return self.score
        raise RuntimeError("score 和 scores 均未设置，不应到达此处")


@dataclass
class PageConfig:
    """答题卡单页配置。"""

    sections: list[SectionConfig] = field(default_factory=list)
    title: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.sections:
            raise ValueError("每页至少包含一个 section")


@dataclass
class AnswerSheetConfig:
    """整张答题卡完整配置。"""

    meta: MetaConfig
    student_id: StudentIdConfig
    pages: list[PageConfig]

    def __post_init__(self) -> None:
        if not self.pages:
            raise ValueError("pages 不能为空")

    def validate(self) -> Optional[str]:
        """验证全局业务规则，返回错误信息或 None。"""
        ranges: list[tuple] = []
        for page_idx, page in enumerate(self.pages):
            for section in page.sections:
                if section.type == "student_id":
                    continue
                start = section.question_start
                end = section.question_start + section.question_count - 1
                ranges.append((start, end, page_idx))

        if self.meta.numbering_mode == "continuous":
            ranges.sort(key=lambda x: x[0])
            for i in range(len(ranges) - 1):
                a_start, a_end, a_page = ranges[i]
                b_start, b_end, b_page = ranges[i + 1]
                if a_end >= b_start:
                    return (
                        f"题目编号范围重叠: 第 {a_page + 1} 页的 [{a_start}, {a_end}] "
                        f"与第 {b_page + 1} 页的 [{b_start}, {b_end}]"
                    )

        all_numbers: list[int] = []
        for start, end, _ in ranges:
            all_numbers.extend(range(start, end + 1))

        if not all_numbers:
            return "没有任何题目"
        return None

    @classmethod
    def from_dict(cls, data: dict) -> "AnswerSheetConfig":
        """从嵌套字典构造配置。"""
        meta = MetaConfig(**data.get("meta", {}))
        student_id = StudentIdConfig(**data.get("student_id", {}))

        pages: list[PageConfig] = []
        for page_dict in data.get("pages", []):
            sections: list[SectionConfig] = []
            for sec_dict in page_dict.get("sections", []):
                sections.append(SectionConfig(**sec_dict))
            pages.append(PageConfig(
                sections=sections,
                title=page_dict.get("title"),
            ))

        return cls(meta=meta, student_id=student_id, pages=pages)

    def to_dict(self) -> dict:
        """序列化为字典。"""

        def _clean(value: Any) -> Any:
            if is_dataclass(value):
                return _clean(asdict(value))
            if isinstance(value, list):
                return [_clean(v) for v in value]
            if isinstance(value, dict):
                return {k: _clean(v) for k, v in value.items() if v is not None}
            return value

        return _clean(self)

    @classmethod
    def load(cls, path: str | Path) -> "AnswerSheetConfig":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
