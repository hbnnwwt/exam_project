from pathlib import Path

from exam_project.gui.grading_adapter import default_legacy_root, project_paths
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
