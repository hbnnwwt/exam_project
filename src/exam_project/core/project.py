from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from exam_project.core.manifest import ProjectManifest


@dataclass(frozen=True)
class ExamProject:
    package_path: Path
    workdir: Path
    manifest: ProjectManifest
