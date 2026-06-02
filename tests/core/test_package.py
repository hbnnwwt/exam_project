import json
import zipfile
from pathlib import Path

import pytest

from exam_project.core.errors import ProjectPackageError
from exam_project.core.package import ExamProjectPackage, safe_extract_zip


def write_minimal_workdir(root: Path, name: str = "Final Exam") -> None:
    (root / "design").mkdir(exist_ok=True)
    (root / "config").mkdir(exist_ok=True)
    (root / "answers").mkdir(exist_ok=True)
    (root / "design" / "answer_sheet.json").write_text("{}", encoding="utf-8")
    (root / "config" / "sheet_layout.json").write_text("{}", encoding="utf-8")
    (root / "answers" / "reference_answers.xlsx").write_bytes(b"placeholder")
    (root / "project.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project_id": "project-1",
                "name": name,
                "created_at": "2026-06-02T20:00:00+08:00",
                "updated_at": "2026-06-02T20:00:00+08:00",
                "assets": {
                    "design": "design/answer_sheet.json",
                    "layout": "config/sheet_layout.json",
                    "answers": "answers/reference_answers.xlsx",
                    "baseline": "config/blank_baseline.json",
                },
                "exam": {"student_id_digits": 10, "question_types": ["choice"]},
                "checksums": {},
            }
        ),
        encoding="utf-8",
    )


def test_pack_and_open_project(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    write_minimal_workdir(workdir)
    package_path = tmp_path / "sample.examproj"

    ExamProjectPackage.pack(workdir, package_path)
    opened = ExamProjectPackage.open(package_path, tmp_path / "opened")

    assert opened.package_path == package_path
    assert opened.workdir == tmp_path / "opened"
    assert opened.manifest.name == "Final Exam"
    assert (opened.workdir / "config" / "sheet_layout.json").exists()


def test_safe_extract_zip_rejects_path_traversal(tmp_path: Path) -> None:
    package_path = tmp_path / "evil.examproj"
    with zipfile.ZipFile(package_path, "w") as zf:
        zf.writestr("../evil.txt", "bad")

    with pytest.raises(ProjectPackageError):
        safe_extract_zip(package_path, tmp_path / "out")

    assert not (tmp_path / "evil.txt").exists()


def test_save_creates_backup_and_replaces_with_verified_package(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    write_minimal_workdir(workdir, name="Original Exam")
    package_path = tmp_path / "sample.examproj"
    ExamProjectPackage.pack(workdir, package_path)

    write_minimal_workdir(workdir, name="Updated Exam")
    ExamProjectPackage.save(workdir, package_path)

    opened = ExamProjectPackage.open(package_path, tmp_path / "opened")
    backup = package_path.with_suffix(".examproj.bak")

    assert opened.manifest.name == "Updated Exam"
    assert backup.exists()
    assert ExamProjectPackage.open(backup, tmp_path / "backup").manifest.name == "Original Exam"
    assert not package_path.with_suffix(".examproj.tmp").exists()


def test_save_does_not_replace_existing_package_when_verify_fails(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    write_minimal_workdir(workdir, name="Original Exam")
    package_path = tmp_path / "sample.examproj"
    ExamProjectPackage.pack(workdir, package_path)

    (workdir / "project.json").unlink()

    with pytest.raises(ProjectPackageError):
        ExamProjectPackage.save(workdir, package_path)

    assert ExamProjectPackage.open(package_path, tmp_path / "opened").manifest.name == "Original Exam"
    assert not package_path.with_suffix(".examproj.tmp").exists()
