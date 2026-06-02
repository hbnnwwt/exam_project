from __future__ import annotations

import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from exam_project.core.checksum import build_checksums
from exam_project.core.errors import ProjectError
from exam_project.core.manifest import ProjectManifest
from exam_project.core.package import ExamProjectPackage
from exam_project.core.validation import validate_project


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def import_legacy_project(legacy_root: Path, package_path: Path, name: str) -> None:
    layout_src = legacy_root / "config" / "sheet_layout.json"
    answers_src = legacy_root / "参考答案.xlsx"
    baseline_src = legacy_root / "config" / "blank_baseline.json"

    if not layout_src.is_file():
        raise ProjectError(f"缺少旧版布局文件: {layout_src}")
    if not answers_src.is_file():
        raise ProjectError(f"缺少旧版参考答案: {answers_src}")

    with tempfile.TemporaryDirectory(prefix="exam_project_import_") as temp:
        workdir = Path(temp)
        (workdir / "design").mkdir()
        (workdir / "config").mkdir()
        (workdir / "answers").mkdir()
        (workdir / "outputs").mkdir()
        (workdir / "logs").mkdir()

        (workdir / "design" / "answer_sheet.json").write_text("{}", encoding="utf-8")
        shutil.copy2(layout_src, workdir / "config" / "sheet_layout.json")
        shutil.copy2(answers_src, workdir / "answers" / "reference_answers.xlsx")
        if baseline_src.is_file():
            shutil.copy2(baseline_src, workdir / "config" / "blank_baseline.json")

        asset_paths = [
            "design/answer_sheet.json",
            "config/sheet_layout.json",
            "answers/reference_answers.xlsx",
        ]
        if (workdir / "config" / "blank_baseline.json").is_file():
            asset_paths.append("config/blank_baseline.json")

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
            exam={"student_id_digits": 10, "question_types": ["choice", "judge", "essay"]},
            checksums=build_checksums(workdir, asset_paths),
        )
        (workdir / "project.json").write_text(manifest.to_json(), encoding="utf-8")
        validate_project(workdir, manifest)
        ExamProjectPackage.save(workdir, package_path)
