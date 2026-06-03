"""answer_sheet.schema 测试。"""

from __future__ import annotations

import json
import pytest

from exam_project.answer_sheet.schema import (
    AnswerSheetConfig,
    MetaConfig,
    PageConfig,
    SectionConfig,
    StudentIdConfig,
)


# ---------------------------------------------------------------------------
# MetaConfig
# ---------------------------------------------------------------------------


def test_meta_defaults() -> None:
    m = MetaConfig()
    assert m.title == "标准化考试答题卡"
    assert m.paper_size == "A4"
    assert m.numbering_mode == "continuous"


def test_meta_rejects_bad_paper_size() -> None:
    with pytest.raises(ValueError, match="paper_size"):
        MetaConfig(paper_size="A3")


def test_meta_rejects_bad_numbering() -> None:
    with pytest.raises(ValueError, match="numbering_mode"):
        MetaConfig(numbering_mode="random")


# ---------------------------------------------------------------------------
# StudentIdConfig
# ---------------------------------------------------------------------------


def test_student_id_default() -> None:
    s = StudentIdConfig()
    assert s.digit_count == 10


@pytest.mark.parametrize("n", [5, 15])
def test_student_id_out_of_range_raises(n: int) -> None:
    with pytest.raises(ValueError, match="digit_count"):
        StudentIdConfig(digit_count=n)


# ---------------------------------------------------------------------------
# SectionConfig
# ---------------------------------------------------------------------------


def test_section_choice_valid() -> None:
    s = SectionConfig(
        type="choice", question_start=1, question_count=20,
        options=["A", "B", "C", "D"], score=3,
    )
    assert s.type == "choice"
    assert s.get_score_for_question(1) == 3


def test_section_judge_requires_tf_options() -> None:
    with pytest.raises(ValueError, match="T.*F"):
        SectionConfig(
            type="judge", question_start=21, question_count=10,
            options=["A", "B"], score=2,
        )


def test_section_judge_with_tf_options() -> None:
    s = SectionConfig(
        type="judge", question_start=21, question_count=10,
        options=["T", "F"], score=2,
    )
    assert s.type == "judge"


def test_section_requires_options() -> None:
    with pytest.raises(ValueError, match="options"):
        SectionConfig(
            type="choice", question_start=1, question_count=5,
            score=3,  # 缺 options
        )


def test_section_essay_requires_lines() -> None:
    with pytest.raises(ValueError, match="lines_per_question"):
        SectionConfig(
            type="essay", question_start=31, question_count=1,
            score=10,  # 缺 lines_per_question
        )


def test_section_student_id_requires_digit_count() -> None:
    with pytest.raises(ValueError, match="digit_count"):
        SectionConfig(type="student_id", question_start=0, question_count=0)


def test_section_score_xor_scores() -> None:
    """score 和 scores 必须只设一个。"""
    with pytest.raises(ValueError, match="score 和 scores"):
        SectionConfig(
            type="choice", question_start=1, question_count=2,
            options=["A", "B"], score=3, scores=[3, 3],  # 都设了
        )


def test_section_scores_length_must_match() -> None:
    with pytest.raises(ValueError, match="scores"):
        SectionConfig(
            type="choice", question_start=1, question_count=3,
            options=["A", "B"], scores=[1, 2],  # 长度不匹配
        )


def test_section_get_score_uses_scores_list() -> None:
    s = SectionConfig(
        type="choice", question_start=1, question_count=3,
        options=["A", "B"], scores=[1, 2, 3],
    )
    assert s.get_score_for_question(1) == 1
    assert s.get_score_for_question(3) == 3


def test_section_get_score_out_of_range() -> None:
    s = SectionConfig(
        type="choice", question_start=1, question_count=2,
        options=["A", "B"], score=3,
    )
    with pytest.raises(IndexError):
        s.get_score_for_question(3)


def test_section_rejects_invalid_type() -> None:
    with pytest.raises(ValueError, match="type 必须是"):
        SectionConfig(type="bogus", question_start=1, question_count=1,
                     options=["A", "B"], score=1)


def test_section_rejects_negative_gap() -> None:
    with pytest.raises(ValueError, match="before_gap_mm"):
        SectionConfig(
            type="choice", question_start=1, question_count=1,
            options=["A", "B"], score=1, before_gap_mm=-1,
        )


# ---------------------------------------------------------------------------
# PageConfig
# ---------------------------------------------------------------------------


def test_page_requires_at_least_one_section() -> None:
    with pytest.raises(ValueError, match="每页"):
        PageConfig(sections=[])


# ---------------------------------------------------------------------------
# AnswerSheetConfig
# ---------------------------------------------------------------------------


def _make_simple_config() -> AnswerSheetConfig:
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


def test_config_validate_ok() -> None:
    cfg = _make_simple_config()
    assert cfg.validate() is None


def test_config_validate_detects_overlap() -> None:
    cfg = AnswerSheetConfig(
        meta=MetaConfig(),
        student_id=StudentIdConfig(),
        pages=[PageConfig(sections=[
            SectionConfig(
                type="choice", question_start=1, question_count=25,
                options=["A", "B"], score=3,
            ),
            SectionConfig(
                type="judge", question_start=24, question_count=5,
                options=["T", "F"], score=2,
            ),
        ])],
    )
    err = cfg.validate()
    assert err is not None
    assert "重叠" in err


def test_config_validate_empty() -> None:
    cfg = AnswerSheetConfig(
        meta=MetaConfig(),
        student_id=StudentIdConfig(),
        pages=[PageConfig(sections=[
            SectionConfig(type="student_id", question_start=0, question_count=0,
                          digit_count=10),
        ])],
    )
    err = cfg.validate()
    assert err == "没有任何题目"


# ---------------------------------------------------------------------------
# from_dict / to_dict / load / save
# ---------------------------------------------------------------------------


def test_from_dict_basic() -> None:
    data = {
        "meta": {"title": "期中考试", "paper_size": "A4"},
        "student_id": {"digit_count": 10},
        "pages": [{
            "sections": [
                {"type": "choice", "question_start": 1, "question_count": 20,
                 "options": ["A", "B", "C", "D"], "score": 3},
            ]
        }],
    }
    cfg = AnswerSheetConfig.from_dict(data)
    assert cfg.meta.title == "期中考试"
    assert cfg.pages[0].sections[0].type == "choice"


def test_to_dict_roundtrip() -> None:
    cfg = _make_simple_config()
    data = cfg.to_dict()
    assert "meta" in data
    assert "pages" in data
    # 反序列化应当成功
    cfg2 = AnswerSheetConfig.from_dict(data)
    assert cfg2.meta.title == cfg.meta.title


def test_to_dict_drops_none_values() -> None:
    cfg = _make_simple_config()
    data = cfg.to_dict()
    # 顶层字段为 None 的应当被剔除
    for page in data["pages"]:
        assert "title" not in page or page["title"] is not None


def test_save_and_load(tmp_path) -> None:
    path = tmp_path / "config.json"
    cfg = _make_simple_config()
    cfg.save(path)
    loaded = AnswerSheetConfig.load(path)
    assert loaded.meta.title == cfg.meta.title
    assert len(loaded.pages) == 1


def test_save_creates_parent_dirs(tmp_path) -> None:
    path = tmp_path / "nested" / "sub" / "config.json"
    _make_simple_config().save(path)
    assert path.is_file()
