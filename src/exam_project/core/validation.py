from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any
from zipfile import BadZipFile

import openpyxl
from openpyxl.utils.exceptions import InvalidFileException

from exam_project.core.errors import ProjectValidationError


QUESTION_TYPES = ("choice", "judge", "essay")


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def classify_question(q_num: int, layout: dict) -> str:
    for q_type in QUESTION_TYPES:
        cfg = layout.get(q_type)
        if not isinstance(cfg, dict):
            continue
        start = _int_or_none(cfg.get("question_start"))
        count = _int_or_none(cfg.get("question_count"))
        if start is None or count is None or count <= 0:
            continue
        if start <= q_num < start + count:
            return q_type
    return "essay"


def _options_for(q_type: str, layout: dict) -> list[str] | None:
    cfg = layout.get(q_type)
    if not isinstance(cfg, dict):
        return None
    options = cfg.get("options")
    if options is None:
        return None
    if isinstance(options, str):
        return [options]
    if isinstance(options, Iterable):
        return [str(option) for option in options]
    return [str(options)]


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _question_number(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError(value)
    if isinstance(value, int):
        q_num = value
    elif isinstance(value, float) and value.is_integer():
        q_num = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        q_num = int(value.strip())
    else:
        raise ValueError(value)
    if q_num <= 0:
        raise ValueError(value)
    return q_num


def validate_answer_workbook(path: Path, layout: dict) -> None:
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except (OSError, BadZipFile, InvalidFileException) as exc:
        raise ProjectValidationError(
            f"Could not open answer workbook: {path}",
            code="invalid_answer_workbook",
        ) from exc

    try:
        ws = wb.active
        for col in range(2, ws.max_column + 1):
            q_raw = ws.cell(row=1, column=col).value
            answer_raw = ws.cell(row=2, column=col).value
            if _is_blank(q_raw) or _is_blank(answer_raw):
                continue

            try:
                q_num = _question_number(q_raw)
            except ValueError as exc:
                raise ProjectValidationError(
                    f"Answer workbook header contains invalid question number: {q_raw}",
                    code="invalid_question_number",
                ) from exc

            answer = str(answer_raw).strip()
            q_type = classify_question(q_num, layout)
            options = _options_for(q_type, layout)
            if options is not None and answer not in options:
                allowed = ", ".join(options)
                raise ProjectValidationError(
                    f"question {q_num} answer {answer} does not match "
                    f"{q_type} layout; allowed answers: {allowed}",
                    code="answer_layout_mismatch",
                )
    finally:
        wb.close()
