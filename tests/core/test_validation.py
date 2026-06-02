from pathlib import Path

import openpyxl
import pytest

from exam_project.core.errors import ProjectValidationError
from exam_project.core.validation import classify_question, validate_answer_workbook


def make_xlsx(path: Path, answers: dict[object, object]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.cell(row=1, column=1, value="student_id")
    ws.cell(row=2, column=1, value="answer")
    for idx, (q_num, answer) in enumerate(answers.items(), start=2):
        ws.cell(row=1, column=idx, value=q_num)
        ws.cell(row=2, column=idx, value=answer)
    wb.save(path)
    wb.close()


def test_classify_question_uses_choice_and_judge_ranges() -> None:
    layout = {
        "choice": {"question_start": 1, "question_count": 3, "options": ["A", "B"]},
        "judge": {"question_start": 4, "question_count": 2, "options": ["T", "F"]},
        "essay": {"question_start": 6, "question_count": 1},
    }

    assert classify_question(1, layout) == "choice"
    assert classify_question(3, layout) == "choice"
    assert classify_question(4, layout) == "judge"
    assert classify_question(5, layout) == "judge"
    assert classify_question(6, layout) == "essay"
    assert classify_question(9, layout) is None


def test_validate_answer_workbook_accepts_matching_layout_options(
    tmp_path: Path,
) -> None:
    layout = {
        "choice": {"question_start": 1, "question_count": 2, "options": ["A", "B"]},
        "judge": {"question_start": 3, "question_count": 1, "options": ["T", "F"]},
        "essay": {"question_start": 9, "question_count": 1},
    }
    path = tmp_path / "answers.xlsx"
    make_xlsx(path, {1: "A", 2: "B", 3: "T", 9: "free form"})

    validate_answer_workbook(path, layout)


def test_validate_answer_workbook_rejects_answer_layout_mismatch(
    tmp_path: Path,
) -> None:
    layout = {
        "choice": {"question_start": 1, "question_count": 2, "options": ["A", "B"]},
        "judge": {"question_start": 3, "question_count": 1, "options": ["T", "F"]},
    }
    path = tmp_path / "answers.xlsx"
    make_xlsx(path, {1: "A", 2: "C", 3: "T"})

    with pytest.raises(ProjectValidationError) as exc:
        validate_answer_workbook(path, layout)

    assert exc.value.code == "answer_layout_mismatch"
    assert "第 2 题" in exc.value.user_message
    assert "答案为 C" in exc.value.user_message
    assert "选择题" in exc.value.user_message
    assert "A/B" in exc.value.user_message


def test_validate_answer_workbook_rejects_invalid_question_header(
    tmp_path: Path,
) -> None:
    layout = {
        "choice": {"question_start": 1, "question_count": 1, "options": ["A"]},
    }
    path = tmp_path / "answers.xlsx"
    make_xlsx(path, {"Q1": "A"})

    with pytest.raises(ProjectValidationError) as exc:
        validate_answer_workbook(path, layout)

    assert exc.value.code == "invalid_question_number"
    assert "Q1" in exc.value.user_message


def test_validate_answer_workbook_rejects_unknown_question_number(
    tmp_path: Path,
) -> None:
    layout = {
        "choice": {"question_start": 1, "question_count": 1, "options": ["A"]},
    }
    path = tmp_path / "answers.xlsx"
    make_xlsx(path, {99: "A"})

    with pytest.raises(ProjectValidationError) as exc:
        validate_answer_workbook(path, layout)

    assert exc.value.code == "unknown_question_number"
    assert "第 99 题" in exc.value.user_message


def test_validate_answer_workbook_rejects_missing_answer(
    tmp_path: Path,
) -> None:
    layout = {
        "choice": {"question_start": 1, "question_count": 1, "options": ["A"]},
    }
    path = tmp_path / "answers.xlsx"
    make_xlsx(path, {1: None})

    with pytest.raises(ProjectValidationError) as exc:
        validate_answer_workbook(path, layout)

    assert exc.value.code == "missing_answer"
    assert "第 1 题" in exc.value.user_message


def test_validate_answer_workbook_rejects_missing_question_number(
    tmp_path: Path,
) -> None:
    layout = {
        "choice": {"question_start": 1, "question_count": 1, "options": ["A"]},
    }
    path = tmp_path / "answers.xlsx"
    make_xlsx(path, {None: "A"})

    with pytest.raises(ProjectValidationError) as exc:
        validate_answer_workbook(path, layout)

    assert exc.value.code == "missing_question_number"


def test_validate_answer_workbook_rejects_mapping_options(
    tmp_path: Path,
) -> None:
    layout = {
        "choice": {"question_start": 1, "question_count": 1, "options": {"A": "yes"}},
    }
    path = tmp_path / "answers.xlsx"
    make_xlsx(path, {1: "A"})

    with pytest.raises(ProjectValidationError) as exc:
        validate_answer_workbook(path, layout)

    assert exc.value.code == "invalid_layout_options"


def test_validate_answer_workbook_rejects_blank_options(tmp_path: Path) -> None:
    layout = {
        "choice": {"question_start": 1, "question_count": 1, "options": ["", " "]},
    }
    path = tmp_path / "answers.xlsx"
    make_xlsx(path, {1: "A"})

    with pytest.raises(ProjectValidationError) as exc:
        validate_answer_workbook(path, layout)

    assert exc.value.code == "invalid_layout_options"


def test_validate_answer_workbook_rejects_blank_string_options(
    tmp_path: Path,
) -> None:
    layout = {
        "choice": {"question_start": 1, "question_count": 1, "options": " "},
    }
    path = tmp_path / "answers.xlsx"
    make_xlsx(path, {1: "A"})

    with pytest.raises(ProjectValidationError) as exc:
        validate_answer_workbook(path, layout)

    assert exc.value.code == "invalid_layout_options"


def test_validate_answer_workbook_rejects_invalid_workbook_bytes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "answers.xlsx"
    path.write_bytes(b"not an xlsx")

    with pytest.raises(ProjectValidationError) as exc:
        validate_answer_workbook(path, {})

    assert exc.value.code == "invalid_answer_workbook"


def test_validate_answer_workbook_rejects_missing_workbook(tmp_path: Path) -> None:
    path = tmp_path / "missing.xlsx"

    with pytest.raises(ProjectValidationError) as exc:
        validate_answer_workbook(path, {})

    assert exc.value.code == "invalid_answer_workbook"


def test_validate_answer_workbook_rejects_empty_zip(tmp_path: Path) -> None:
    path = tmp_path / "empty.xlsx"
    path.write_bytes(b"PK\x05\x06" + b"\x00" * 18)

    with pytest.raises(ProjectValidationError) as exc:
        validate_answer_workbook(path, {})

    assert exc.value.code == "invalid_answer_workbook"
