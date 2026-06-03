from pathlib import Path
import json

from exam_project.gui.grading_adapter import (
    configure_project_designer,
    default_legacy_root,
    project_paths,
)
from exam_project.gui.session import create_and_open_project


def test_project_paths_point_to_current_project_assets(tmp_path: Path) -> None:
    session = create_and_open_project(tmp_path / "sample.examproj", name="项目")

    paths = project_paths(session.project)

    assert paths["answer_key"] == str(session.project.answers_path)
    assert paths["default_folder"] == str(session.workdir / "data" / "answer_sheets")
    assert paths["output_dir"] == str(session.workdir / "data" / "output")
    assert paths["processed_dir"] == str(session.workdir / "data" / "processed")
    assert Path(paths["default_folder"]).is_dir()
    assert Path(paths["output_dir"]).is_dir()
    assert Path(paths["processed_dir"]).is_dir()


def test_default_legacy_root_is_sibling_auto_grading_system() -> None:
    assert default_legacy_root().name == "auto_grading_system"


def test_configure_project_designer_points_paths_to_current_project(
    tmp_path: Path,
) -> None:
    session = create_and_open_project(tmp_path / "sample.examproj", name="项目")

    with configure_project_designer(session.project) as designer:
        assert designer._BASE_DIR == str(session.workdir)
        assert designer._LAYOUT_PATH == str(session.project.layout_path)
        assert designer._AUTOSAVE_PATH == str(session.project.asset_path("design"))
        assert designer._SAVED_DESIGNS_DIR == str(session.workdir / "design" / "saved_designs")
        assert Path(designer._SAVED_DESIGNS_DIR).is_dir()

    assert designer._LAYOUT_PATH != str(session.project.layout_path)


def test_configure_project_designer_upgrades_invalid_design_asset(
    tmp_path: Path,
) -> None:
    session = create_and_open_project(tmp_path / "sample.examproj", name="项目")
    session.project.asset_path("design").write_text("{}", encoding="utf-8")

    with configure_project_designer(session.project):
        pass

    design = json.loads(session.project.asset_path("design").read_text(encoding="utf-8"))
    assert design["meta"]["title"] == "项目"
    assert design["pages"][0]["sections"][0]["type"] == "student_id"


def test_configure_project_designer_restores_paths_after_error(
    tmp_path: Path,
) -> None:
    session = create_and_open_project(tmp_path / "sample.examproj", name="项目")

    try:
        with configure_project_designer(session.project) as designer:
            patched_layout_path = designer._LAYOUT_PATH
            raise RuntimeError("simulated render failure")
    except RuntimeError:
        pass

    assert designer._LAYOUT_PATH != patched_layout_path
    assert designer._LAYOUT_PATH != str(session.project.layout_path)
