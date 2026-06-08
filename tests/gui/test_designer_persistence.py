import json
import os
import time
from pathlib import Path

from exam_project.core.new_project import create_exam_project
from exam_project.core.package import ExamProjectPackage
from exam_project.gui.views.designer import (
    _load_initial_designer_config,
    list_designs,
    load_design,
    save_design,
)


def _project(tmp_path: Path):
    workdir = tmp_path / "exam"
    create_exam_project(workdir, name="exam")
    return ExamProjectPackage.open_folder(workdir)


def _config(question_count: int) -> dict:
    return {
        "meta": {
            "title": f"count {question_count}",
            "paper_size": "A4",
            "numbering_mode": "continuous",
        },
        "student_id": {"digit_count": 10},
        "pages": [
            {
                "sections": [
                    {
                        "type": "student_id",
                        "question_start": 0,
                        "question_count": 0,
                        "digit_count": 10,
                    },
                    {
                        "type": "choice",
                        "question_start": 1,
                        "question_count": question_count,
                        "options": ["A", "B", "C", "D"],
                        "score": 2,
                    },
                ]
            }
        ],
    }


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _choice_count(cfg: dict) -> int:
    return next(
        section["question_count"]
        for section in cfg["pages"][0]["sections"]
        if section["type"] == "choice"
    )


def test_initial_config_loads_project_design_when_session_is_empty(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _write_json(project.design_path, _config(7))

    loaded = _load_initial_designer_config(project)

    assert _choice_count(loaded) == 7


def test_initial_config_recovers_newer_legacy_autosave(tmp_path: Path) -> None:
    project = _project(tmp_path)
    legacy_autosave = project.workdir / "saved_designs" / "_autosave.json"
    _write_json(project.design_path, _config(7))
    _write_json(legacy_autosave, _config(9))

    now = time.time()
    os.utime(project.design_path, (now - 100, now - 100))
    os.utime(legacy_autosave, (now, now))

    loaded = _load_initial_designer_config(project)

    assert _choice_count(loaded) == 9


def test_initial_config_ignores_invalid_newer_autosave(tmp_path: Path) -> None:
    project = _project(tmp_path)
    legacy_autosave = project.workdir / "saved_designs" / "_autosave.json"
    _write_json(project.design_path, _config(7))
    legacy_autosave.parent.mkdir(parents=True, exist_ok=True)
    legacy_autosave.write_text("{", encoding="utf-8")

    now = time.time()
    os.utime(project.design_path, (now - 100, now - 100))
    os.utime(legacy_autosave, (now, now))

    loaded = _load_initial_designer_config(project)

    assert _choice_count(loaded) == 7


def test_saved_designs_write_primary_path_and_read_legacy_path(tmp_path: Path) -> None:
    project = _project(tmp_path)
    primary = project.saved_designs_dir / "primary.json"
    legacy = project.workdir / "saved_designs" / "legacy.json"

    save_design("primary", _config(3), project)
    _write_json(legacy, _config(5))

    assert primary.is_file()
    assert _choice_count(load_design("primary", project)) == 3
    assert _choice_count(load_design("legacy", project)) == 5
    assert {name for name, _ in list_designs(project)} >= {"primary", "legacy"}
