from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import openpyxl

from exam_project.core.checksum import build_checksums
from exam_project.core.errors import ProjectValidationError
from exam_project.core.manifest import ProjectManifest
from exam_project.core.package import ExamProjectPackage
from exam_project.core.validation import validate_project


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _write_blank_answers(path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.cell(row=1, column=1, value="学号")
    ws.cell(row=2, column=1, value="参考答案")
    wb.save(path)
    wb.close()


def _blank_answer_sheet_design(name: str, student_id_digits: int) -> dict:
    return {
        "meta": {
            "title": name,
            "paper_size": "A4",
            "numbering_mode": "continuous",
        },
        "student_id": {"digit_count": student_id_digits},
        "pages": [
            {
                "sections": [
                    {
                        "type": "student_id",
                        "question_start": 0,
                        "question_count": 0,
                        "digit_count": student_id_digits,
                    },
                    {
                        "type": "choice",
                        "question_start": 1,
                        "question_count": 20,
                        "options": ["A", "B", "C", "D"],
                        "score": 3,
                    },
                ]
            },
            {
                "sections": [
                    {
                        "type": "judge",
                        "question_start": 21,
                        "question_count": 10,
                        "options": ["T", "F"],
                        "score": 2,
                    },
                    {
                        "type": "essay",
                        "question_start": 31,
                        "question_count": 1,
                        "lines_per_question": 8,
                        "score": 10,
                    },
                ]
            },
        ],
    }


def create_exam_project(
    package_path: Path,
    *,
    name: str,
    student_id_digits: int = 10,
) -> None:
    if type(student_id_digits) is not int or not (6 <= student_id_digits <= 14):
        raise ProjectValidationError(
            "学号位数必须在 6 到 14 之间",
            code="invalid_student_id_digits",
        )

    with tempfile.TemporaryDirectory(prefix="exam_project_new_") as temp:
        workdir = Path(temp)
        (workdir / "design").mkdir()
        (workdir / "config").mkdir()
        (workdir / "answers").mkdir()
        (workdir / "outputs").mkdir()
        (workdir / "logs").mkdir()

        (workdir / "design" / "answer_sheet.json").write_text(
            json.dumps(
                _blank_answer_sheet_design(name, student_id_digits),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (workdir / "config" / "sheet_layout.json").write_text(
            json.dumps(
                {
                    "layout": {},
                    "scoring": {},
                    "student_id": {"digit_count": student_id_digits},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        _write_blank_answers(workdir / "answers" / "reference_answers.xlsx")

        asset_paths = [
            "design/answer_sheet.json",
            "config/sheet_layout.json",
            "answers/reference_answers.xlsx",
        ]
        now = _now_iso()
        manifest = ProjectManifest(
            schema_version=1,
            project_id=str(uuid4()),
            name=name,
            created_at=now,
            updated_at=now,
            assets={
                "design": "design/answer_sheet.json",
                "layout": "config/sheet_layout.json",
                "answers": "answers/reference_answers.xlsx",
                "baseline": "config/blank_baseline.json",
            },
            exam={
                "student_id_digits": student_id_digits,
                "question_types": ["choice", "judge", "essay"],
            },
            checksums=build_checksums(workdir, asset_paths),
        )
        (workdir / "project.json").write_text(manifest.to_json(), encoding="utf-8")
        validate_project(workdir, manifest)
        ExamProjectPackage.save(workdir, package_path)
