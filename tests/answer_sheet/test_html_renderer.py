"""html_renderer 测试。"""

from __future__ import annotations

from exam_project.answer_sheet.html_renderer import render_html
from exam_project.answer_sheet.layout_engine import paginate
from exam_project.answer_sheet.schema import (
    AnswerSheetConfig,
    MetaConfig,
    PageConfig,
    SectionConfig,
    StudentIdConfig,
)


def _config() -> AnswerSheetConfig:
    return AnswerSheetConfig(
        meta=MetaConfig(title="测试答题卡"),
        student_id=StudentIdConfig(digit_count=10),
        pages=[PageConfig(sections=[
            SectionConfig(
                type="choice", question_start=1, question_count=20,
                options=["A", "B", "C", "D"], score=3,
            ),
        ])],
    )


def test_render_html_returns_string() -> None:
    cfg = _config()
    pages = paginate(cfg)
    html = render_html(cfg, pages)
    assert isinstance(html, str)
    assert len(html) > 0


def test_render_html_has_doctype() -> None:
    cfg = _config()
    html = render_html(cfg, paginate(cfg))
    assert html.startswith("<!DOCTYPE html>")


def test_render_html_contains_title() -> None:
    cfg = _config()
    html = render_html(cfg, paginate(cfg))
    assert "测试答题卡" in html


def test_render_html_contains_css() -> None:
    cfg = _config()
    html = render_html(cfg, paginate(cfg))
    assert "<style>" in html
    assert "bubble-cell" in html


def test_render_html_contains_pages() -> None:
    cfg = _config()
    html = render_html(cfg, paginate(cfg))
    assert html.count('class="page"') >= 1
    assert "page-title" in html


def test_render_html_with_empty_pages() -> None:
    from exam_project.answer_sheet.html_renderer import render_html
    cfg = _config()
    html = render_html(cfg, [])
    # 即使没有 page，也要输出合法的 HTML 框架
    assert html.startswith("<!DOCTYPE html>")
    assert "测试答题卡" in html
