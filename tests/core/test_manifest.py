import json

import pytest

from exam_project.core.errors import ProjectValidationError
from exam_project.core.manifest import ProjectManifest, validate_asset_path


def test_manifest_round_trip_json():
    manifest = ProjectManifest(
        schema_version=1,
        project_id="project-1",
        name="期末考试",
        created_at="2026-06-02T20:00:00+08:00",
        updated_at="2026-06-02T20:30:00+08:00",
        assets={
            "design": "design/answer_sheet.json",
            "layout": "config/sheet_layout.json",
            "baseline": "config/blank_baseline.json",
            "answers": "answers/reference_answers.xlsx",
        },
        exam={"student_id_digits": 10, "question_types": ["choice", "judge"]},
        checksums={"config/sheet_layout.json": "sha256:" + "1" * 64},
    )
    loaded = ProjectManifest.from_json(manifest.to_json())
    assert loaded == manifest
    assert json.loads(loaded.to_json())["name"] == "期末考试"


@pytest.mark.parametrize(
    "path",
    [
        "../evil.txt",
        "/absolute/path.txt",
        "C:/absolute/path.txt",
        "config/../evil.txt",
        "",
    ],
)
def test_rejects_unsafe_asset_paths(path):
    with pytest.raises(ProjectValidationError):
        validate_asset_path(path)


def test_accepts_relative_asset_path():
    assert validate_asset_path("config/sheet_layout.json") == "config/sheet_layout.json"
