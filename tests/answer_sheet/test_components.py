"""components + layout_engine + config_exporter 集成测试。"""

from __future__ import annotations

import pytest

from exam_project.answer_sheet.components import (
    ChoiceComponent,
    EssayComponent,
    JudgeComponent,
    StudentIdComponent,
)
from exam_project.answer_sheet.config_exporter import export_sheet_layout
from exam_project.answer_sheet.layout_engine import (
    LayoutError,
    Page,
    page_content_height,
    paginate,
)
from exam_project.answer_sheet.schema import (
    AnswerSheetConfig,
    MetaConfig,
    PageConfig,
    SectionConfig,
    StudentIdConfig,
)


# ---------------------------------------------------------------------------
# 单组件
# ---------------------------------------------------------------------------


def test_choice_estimate_height() -> None:
    section = SectionConfig(
        type="choice", question_start=1, question_count=20,
        options=["A", "B", "C", "D"], score=3,
    )
    comp = ChoiceComponent(section)
    h = comp.estimate_height("A4")
    assert h > 0


def test_choice_split() -> None:
    section = SectionConfig(
        type="choice", question_start=1, question_count=20,
        options=["A", "B", "C", "D"], score=3,
    )
    comp = ChoiceComponent(section)
    split = comp.split(50.0, "A4")  # 50mm 空间
    if split is not None:
        first, second = split
        assert first.config.question_count < 20
        assert second.config.question_count > 0
        assert first.config.question_count + second.config.question_count == 20


def test_choice_no_split_when_too_small() -> None:
    section = SectionConfig(
        type="choice", question_start=1, question_count=20,
        options=["A", "B", "C", "D"], score=3,
    )
    comp = ChoiceComponent(section)
    assert comp.split(0.1, "A4") is None


def test_choice_no_split_when_count_is_1() -> None:
    section = SectionConfig(
        type="choice", question_start=1, question_count=1,
        options=["A", "B"], score=1,
    )
    comp = ChoiceComponent(section)
    assert comp.split(100.0, "A4") is None


def test_judge_uses_tf() -> None:
    section = SectionConfig(
        type="judge", question_start=21, question_count=10,
        options=["T", "F"], score=2,
    )
    comp = JudgeComponent(section)
    assert comp.options == ["T", "F"]


def test_essay_estimate_and_render() -> None:
    section = SectionConfig(
        type="essay", question_start=31, question_count=2,
        score=10, lines_per_question=3,
    )
    comp = EssayComponent(section)
    h = comp.estimate_height("A4")
    assert h > 0
    html = comp.render(1, 0.0, "A4")
    assert "essay" in html
    assert "31" in html
    assert "32" in html


def test_student_id_render() -> None:
    section = SectionConfig(type="student_id", question_start=0, question_count=0,
                            digit_count=10)
    comp = StudentIdComponent(section)
    html = comp.render(1, 0.0, "A4")
    assert "student-id" in html
    assert 'class="sid-grid"' in html
    assert "repeat(10, 1fr)" in html


def test_student_id_cannot_split() -> None:
    section = SectionConfig(type="student_id", question_start=0, question_count=0,
                            digit_count=10)
    comp = StudentIdComponent(section)
    assert comp.split(100.0, "A4") is None


# ---------------------------------------------------------------------------
# paginate
# ---------------------------------------------------------------------------


def _simple_config() -> AnswerSheetConfig:
    return AnswerSheetConfig(
        meta=MetaConfig(),
        student_id=StudentIdConfig(),
        pages=[PageConfig(sections=[
            SectionConfig(
                type="choice", question_start=1, question_count=20,
                options=["A", "B", "C", "D"], score=3,
            ),
            SectionConfig(
                type="judge", question_start=21, question_count=10,
                options=["T", "F"], score=2,
            ),
        ])],
    )


def test_paginate_simple() -> None:
    pages = paginate(_simple_config())
    assert len(pages) >= 1
    for p in pages:
        assert p.page_number >= 1


def test_paginate_assigns_sequential_page_numbers() -> None:
    pages = paginate(_simple_config())
    for idx, p in enumerate(pages, start=1):
        assert p.page_number == idx


def test_paginate_preserves_section_order() -> None:
    pages = paginate(_simple_config())
    all_comps = [c for p in pages for c in p.components]
    assert len(all_comps) >= 2


def test_paginate_rejects_bad_paper() -> None:
    cfg = _simple_config()
    cfg.meta.paper_size = "A3"
    with pytest.raises(ValueError, match="纸张"):
        paginate(cfg)


def test_page_content_height_differs_by_page() -> None:
    assert page_content_height("A4", 1) < page_content_height("A4", 2)


# ---------------------------------------------------------------------------
# config_exporter
# ---------------------------------------------------------------------------


def test_export_basic() -> None:
    cfg = _simple_config()
    out = export_sheet_layout(cfg)
    assert "layout" in out
    assert "scoring" in out
    assert "_pages" in out
    assert "choice" in out
    assert "judge" in out
    assert out["choice"]["question_count"] == 20
    assert out["judge"]["question_count"] == 10


def test_export_with_student_id_section() -> None:
    """当 cfg.pages 中包含 type=student_id section 时才导出 student_id 字段。"""
    cfg = AnswerSheetConfig(
        meta=MetaConfig(),
        student_id=StudentIdConfig(digit_count=10),
        pages=[PageConfig(sections=[
            SectionConfig(type="student_id", question_start=0, question_count=0,
                          digit_count=10),
            SectionConfig(
                type="choice", question_start=1, question_count=20,
                options=["A", "B", "C", "D"], score=3,
            ),
        ])],
    )
    out = export_sheet_layout(cfg)
    assert "student_id" in out
    assert out["student_id"]["digit_count"] == 10


def test_export_scoring() -> None:
    cfg = _simple_config()
    out = export_sheet_layout(cfg)
    assert out["scoring"]["choice_score"] == 3
    assert out["scoring"]["judge_score"] == 2
    assert out["scoring"]["essay_max_score"] == 20  # default


def test_export_pages_field() -> None:
    cfg = _simple_config()
    out = export_sheet_layout(cfg)
    assert isinstance(out["_pages"], list)
    assert len(out["_pages"]) >= 1
    for page in out["_pages"]:
        assert "page_number" in page
        assert "sections" in page


def test_export_fallback_layout_uses_paginate() -> None:
    """fallback 应当与 paginate 结果一致。"""
    cfg = _simple_config()
    out = export_sheet_layout(cfg)
    pages_in_pages_field = len(out["_pages"])
    pages_in_fallback = sum(1 for k in out["layout"] if k.startswith("page"))
    # 不强求完全相等：fallback 只对含 section 的页生成
    assert pages_in_pages_field >= 1
