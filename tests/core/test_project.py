import json
from pathlib import Path

import pytest

from exam_project.core.errors import ProjectError
from exam_project.core.manifest import ProjectManifest
from exam_project.core.project import ExamProject, ProjectContext


def make_project(tmp_path: Path) -> ExamProject:
    workdir = tmp_path / "work"
    (workdir / "config").mkdir(parents=True)
    (workdir / "config" / "sheet_layout.json").write_text(
        json.dumps({"layout": {}, "scoring": {"choice_score": 1}}),
        encoding="utf-8",
    )
    manifest = ProjectManifest(
        schema_version=1,
        project_id="project-1",
        name="Final Exam",
        created_at="2026-06-02T20:00:00+08:00",
        updated_at="2026-06-02T20:00:00+08:00",
        assets={
            "design": "design/answer_sheet.json",
            "layout": "config/sheet_layout.json",
            "answers": "answers/reference_answers.xlsx",
            "baseline": "config/blank_baseline.json",
        },
        exam={"student_id_digits": 10, "question_types": ["choice"]},
        checksums={},
    )
    return ExamProject(
        package_path=tmp_path / "sample.examproj",
        workdir=workdir,
        manifest=manifest,
    )


def make_project_without_baseline(tmp_path: Path) -> ExamProject:
    project = make_project(tmp_path)
    data = project.manifest.to_dict()
    data["assets"].pop("baseline")
    return ExamProject(
        package_path=project.package_path,
        workdir=project.workdir,
        manifest=ProjectManifest.from_dict(data),
    )


def test_asset_path_resolves_declared_asset_under_workdir(tmp_path: Path) -> None:
    project = make_project(tmp_path)

    assert project.asset_path("layout") == (
        project.workdir / project.manifest.assets["layout"]
    )


def test_common_asset_path_properties(tmp_path: Path) -> None:
    project = make_project(tmp_path)

    assert project.layout_path == project.workdir / "config" / "sheet_layout.json"
    assert project.answers_path == project.workdir / "answers" / "reference_answers.xlsx"
    assert project.baseline_path == project.workdir / "config" / "blank_baseline.json"


def test_load_layout_reads_layout_json_as_dict(tmp_path: Path) -> None:
    project = make_project(tmp_path)

    assert project.load_layout() == {"layout": {}, "scoring": {"choice_score": 1}}


def test_load_layout_missing_file_uses_python_io_error(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    project.layout_path.unlink()

    with pytest.raises(FileNotFoundError):
        project.load_layout()


def test_load_layout_invalid_json_uses_json_error(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    project.layout_path.write_text("{", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        project.load_layout()


def test_asset_path_rejects_undeclared_asset_key(tmp_path: Path) -> None:
    project = make_project(tmp_path)

    with pytest.raises(ProjectError, match="项目未声明资产: missing"):
        project.asset_path("missing")


def test_baseline_path_rejects_missing_optional_asset(tmp_path: Path) -> None:
    project = make_project_without_baseline(tmp_path)

    with pytest.raises(ProjectError, match="项目未声明资产: baseline"):
        _ = project.baseline_path


def test_project_context_tracks_current_project(tmp_path: Path) -> None:
    context = ProjectContext()
    project = make_project(tmp_path)

    assert context.current is None

    context.set_current(project)
    assert context.current is project
    assert context.require_current() is project

    context.clear()
    assert context.current is None


def test_project_context_requires_open_project() -> None:
    context = ProjectContext()

    with pytest.raises(ProjectError):
        context.require_current()
