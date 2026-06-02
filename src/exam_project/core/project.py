from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from exam_project.core.errors import ProjectError
from exam_project.core.manifest import ProjectManifest, validate_asset_path


@dataclass(frozen=True)
class ExamProject:
    package_path: Path
    workdir: Path
    manifest: ProjectManifest

    def asset_path(self, asset_key: str) -> Path:
        if asset_key not in self.manifest.assets:
            raise ProjectError(f"项目未声明资产: {asset_key}")
        rel = validate_asset_path(self.manifest.assets[asset_key])
        return self.workdir / rel

    @property
    def layout_path(self) -> Path:
        return self.asset_path("layout")

    @property
    def answers_path(self) -> Path:
        return self.asset_path("answers")

    @property
    def baseline_path(self) -> Path:
        return self.asset_path("baseline")

    def load_layout(self) -> dict:
        return json.loads(self.layout_path.read_text(encoding="utf-8"))


class ProjectContext:
    def __init__(self) -> None:
        self.current: ExamProject | None = None

    def set_current(self, project: ExamProject) -> None:
        self.current = project

    def require_current(self) -> ExamProject:
        if self.current is None:
            raise ProjectError("当前未打开考试项目")
        return self.current

    def clear(self) -> None:
        self.current = None
