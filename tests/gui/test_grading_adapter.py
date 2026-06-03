import json
import sys
from pathlib import Path

from exam_project.gui.grading_adapter import (
    _import_legacy_module,
    configure_project_calibration,
    configure_project_designer,
    default_legacy_root,
    project_paths,
    save_json_config,
)
from exam_project.gui.session import create_and_open_project


def test_project_paths_point_to_current_project_assets(tmp_path: Path) -> None:
    session = create_and_open_project(tmp_path / "sample.examproj", name="项目")

    paths = project_paths(session.project)

    assert paths["answer_key"] == str(session.project.answers_path)
    assert paths["default_folder"] == str(session.project.answer_sheets_dir)
    assert paths["output_dir"] == str(session.project.output_dir)
    assert paths["processed_dir"] == str(session.project.processed_dir)
    assert paths["api_keys"] == str(session.project.api_keys_path)
    assert paths["model_config"] == str(session.project.model_config_path)
    assert paths["batch_checkpoint"] == str(session.project.batch_checkpoint_path)
    assert Path(paths["default_folder"]).is_dir()
    assert Path(paths["output_dir"]).is_dir()
    assert Path(paths["processed_dir"]).is_dir()
    assert session.project.config_dir.is_dir()


def test_default_legacy_root_is_sibling_auto_grading_system() -> None:
    assert default_legacy_root().name == "auto_grading_system"


def test_configure_project_designer_points_paths_to_current_project(
    tmp_path: Path,
) -> None:
    session = create_and_open_project(tmp_path / "sample.examproj", name="项目")

    with configure_project_designer(session.project) as designer:
        assert designer._BASE_DIR == str(session.workdir)
        assert designer._LAYOUT_PATH == str(session.project.layout_path)
        assert designer._AUTOSAVE_PATH == str(session.project.design_path)
        assert designer._SAVED_DESIGNS_DIR == str(session.project.saved_designs_dir)
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


def test_configure_project_calibration_points_paths_to_current_project(
    tmp_path: Path,
) -> None:
    session = create_and_open_project(tmp_path / "sample.examproj", name="项目")

    with configure_project_calibration(session.project) as calibration:
        assert calibration._BASE_DIR == str(session.workdir)
        assert calibration._LAYOUT_PATH == str(session.project.layout_path)
        assert calibration._BASELINE_PATH == str(session.project.baseline_path)

    assert calibration._LAYOUT_PATH != str(session.project.layout_path)
    assert calibration._BASELINE_PATH != str(session.project.baseline_path)


def test_configure_project_calibration_restores_paths_after_error(
    tmp_path: Path,
) -> None:
    session = create_and_open_project(tmp_path / "sample.examproj", name="项目")

    try:
        with configure_project_calibration(session.project) as calibration:
            patched_baseline_path = calibration._BASELINE_PATH
            raise RuntimeError("simulated render failure")
    except RuntimeError:
        pass

    assert calibration._BASELINE_PATH != patched_baseline_path
    assert calibration._BASELINE_PATH != str(session.project.baseline_path)


def test_save_json_config_writes_project_config_path(tmp_path: Path) -> None:
    session = create_and_open_project(tmp_path / "sample.examproj", name="项目")
    paths = project_paths(session.project)

    saved = save_json_config(
        paths["api_keys"],
        {
            "api_key": "primary",
            "api_keys": ["fallback"],
            "ocr_api_key": "ocr",
        },
    )

    assert saved["api_key"] == "primary"
    assert json.loads(Path(paths["api_keys"]).read_text(encoding="utf-8")) == saved
    assert Path(paths["api_keys"]).is_relative_to(session.workdir)


def test_save_json_config_can_clear_existing_keys(tmp_path: Path) -> None:
    session = create_and_open_project(tmp_path / "sample.examproj", name="项目")
    paths = project_paths(session.project)

    save_json_config(
        paths["api_keys"],
        {
            "api_key": "primary",
            "api_keys": ["fallback"],
            "ocr_api_key": "ocr",
        },
    )
    saved = save_json_config(
        paths["api_keys"],
        {
            "api_key": "",
            "api_keys": [],
            "ocr_api_key": "",
        },
    )

    assert saved["api_key"] == ""
    assert saved["api_keys"] == []
    assert saved["ocr_api_key"] == ""


def test_import_legacy_module_removes_new_sys_path_after_import(tmp_path: Path) -> None:
    legacy_root = tmp_path / "legacy"
    legacy_root.mkdir()
    module_name = "round3_temp_module"
    (legacy_root / f"{module_name}.py").write_text("VALUE = 42\n", encoding="utf-8")
    sys.modules.pop(module_name, None)
    root_text = str(legacy_root)
    assert root_text not in sys.path

    try:
        module = _import_legacy_module(module_name, legacy_root)

        assert module.VALUE == 42
        assert root_text not in sys.path
    finally:
        sys.modules.pop(module_name, None)


def test_import_legacy_module_preserves_existing_sys_path(tmp_path: Path) -> None:
    legacy_root = tmp_path / "legacy"
    legacy_root.mkdir()
    module_name = "round3_existing_path_module"
    (legacy_root / f"{module_name}.py").write_text("VALUE = 7\n", encoding="utf-8")
    sys.modules.pop(module_name, None)
    root_text = str(legacy_root)
    sys.path.insert(0, root_text)

    try:
        module = _import_legacy_module(module_name, legacy_root)

        assert module.VALUE == 7
        assert root_text in sys.path
    finally:
        sys.path.remove(root_text)
        sys.modules.pop(module_name, None)
