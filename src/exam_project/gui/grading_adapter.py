from __future__ import annotations

from contextlib import contextmanager
import importlib
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from exam_project.core.project import ExamProject


def default_legacy_root() -> Path:
    return Path(__file__).resolve().parents[4] / "auto_grading_system"


def project_paths(project: ExamProject) -> dict[str, str]:
    workdir = project.workdir
    data_dir = workdir / "data"
    output_dir = data_dir / "output"
    processed_dir = data_dir / "processed"
    answer_sheets_dir = data_dir / "answer_sheets"
    for path in (output_dir, processed_dir, answer_sheets_dir, workdir / "config"):
        path.mkdir(parents=True, exist_ok=True)
    return {
        "answer_key": str(project.answers_path),
        "default_folder": str(answer_sheets_dir),
        "output_dir": str(output_dir),
        "processed_dir": str(processed_dir),
        "api_keys": str(workdir / "config" / "api_keys.json"),
        "model_config": str(workdir / "config" / "model_config.json"),
        "batch_checkpoint": str(output_dir / "_batch_checkpoint.json"),
    }


def _import_legacy_module(name: str, legacy_root: Path) -> ModuleType:
    root_text = str(legacy_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    return importlib.import_module(name)


def _default_design(project: ExamProject) -> dict[str, Any]:
    digit_count = project.manifest.exam.get("student_id_digits", 10)
    if type(digit_count) is not int or not (6 <= digit_count <= 14):
        digit_count = 10
    return {
        "meta": {
            "title": project.manifest.name,
            "paper_size": "A4",
            "numbering_mode": "continuous",
        },
        "student_id": {"digit_count": digit_count},
        "pages": [
            {
                "sections": [
                    {
                        "type": "student_id",
                        "question_start": 0,
                        "question_count": 0,
                        "digit_count": digit_count,
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


def _configure_project_designer(
    project: ExamProject,
    legacy_root: Path | None = None,
) -> ModuleType:
    root = legacy_root or default_legacy_root()
    designer = _import_legacy_module("views.designer_view", root)

    project.asset_path("design").parent.mkdir(parents=True, exist_ok=True)
    project.layout_path.parent.mkdir(parents=True, exist_ok=True)
    saved_designs_dir = project.workdir / "design" / "saved_designs"
    saved_designs_dir.mkdir(parents=True, exist_ok=True)

    designer._BASE_DIR = str(project.workdir)
    designer._LAYOUT_PATH = str(project.layout_path)
    designer._SAVED_DESIGNS_DIR = str(saved_designs_dir)
    designer._AUTOSAVE_PATH = str(project.asset_path("design"))

    try:
        data = json.loads(project.asset_path("design").read_text(encoding="utf-8"))
        designer.AnswerSheetConfig.from_dict(data)
    except Exception:
        project.asset_path("design").write_text(
            json.dumps(_default_design(project), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return designer


@contextmanager
def configure_project_designer(
    project: ExamProject,
    legacy_root: Path | None = None,
):
    root = legacy_root or default_legacy_root()
    designer = _import_legacy_module("views.designer_view", root)
    backup = {
        "_BASE_DIR": designer._BASE_DIR,
        "_LAYOUT_PATH": designer._LAYOUT_PATH,
        "_SAVED_DESIGNS_DIR": designer._SAVED_DESIGNS_DIR,
        "_AUTOSAVE_PATH": designer._AUTOSAVE_PATH,
    }
    try:
        yield _configure_project_designer(project, root)
    finally:
        for name, value in backup.items():
            setattr(designer, name, value)


def _fallbacks(layout: dict[str, Any], key: str, defaults: dict[str, list[float]]) -> dict[str, tuple[float, float]]:
    cfg = layout.get("layout", {})
    if not isinstance(cfg, dict):
        cfg = {}
    values = cfg.get(key, {})
    if not isinstance(values, dict):
        values = {}
    merged = {**defaults, **values}
    return {name: tuple(raw) for name, raw in merged.items()}


def apply_project_layout(project: ExamProject, legacy_root: Path | None = None) -> None:
    root = legacy_root or default_legacy_root()
    layout = project.load_layout()

    pipeline = _import_legacy_module("modules.pipeline", root)
    layout_module = _import_legacy_module("modules.layout", root)
    grading = _import_legacy_module("modules.grading", root)
    marker = _import_legacy_module("modules.marker", root)
    single_view = _import_legacy_module("views.single_view", root)
    batch_view = _import_legacy_module("views.batch_view", root)
    components = _import_legacy_module("views.components", root)

    pipeline.LAYOUT = layout
    layout_module._LAYOUT = layout
    grading.LAYOUT = layout
    marker.LAYOUT = layout
    marker._choice_layout = layout.get("choice", {})
    marker._judge_layout = layout.get("judge", {})
    single_view.LAYOUT = layout
    batch_view.LAYOUT = layout

    analyzer = layout_module.LayoutAnalyzer
    analyzer.PAGE1_FALLBACK = _fallbacks(
        layout,
        "page1_fallback",
        {"student_id": [0.06, 0.26], "choice": [0.28, 0.80]},
    )
    analyzer.PAGE2_FALLBACK = _fallbacks(
        layout,
        "page2_fallback",
        {"judge": [0.06, 0.46], "essay": [0.50, 0.90]},
    )

    upload_path = project.workdir / "answers" / "_uploaded_answer_key.xlsx"
    components._UPLOADED_AK_PATH = str(upload_path)


def load_baseline(project: ExamProject, legacy_root: Path | None = None) -> dict[str, Any]:
    if not project.baseline_path.is_file():
        return {
            "choice_baseline": None,
            "judge_baseline": None,
            "choice_zone_bounds": None,
            "judge_zone_bounds": None,
        }

    root = legacy_root or default_legacy_root()
    blank = _import_legacy_module("modules.blank_calibrator", root)
    raw = blank.load_baseline(str(project.baseline_path))
    return {
        "choice_baseline": blank.get_choice_baseline_dict(raw),
        "judge_baseline": blank.get_judge_baseline_dict(raw),
        "choice_zone_bounds": blank.get_choice_zone_bounds(raw),
        "judge_zone_bounds": blank.get_judge_zone_bounds(raw),
    }


def load_model_config(path: str) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.is_file():
        return {}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}
