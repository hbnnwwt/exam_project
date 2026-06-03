from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path

from exam_project.core.checksum import build_checksums
from exam_project.core.legacy_import import import_legacy_project
from exam_project.core.manifest import ProjectManifest
from exam_project.core.new_project import create_exam_project
from exam_project.core.package import ExamProjectPackage
from exam_project.core.project import ExamProject
from exam_project.core.validation import validate_project


WORKSPACE_DIR_NAME = ".exam_project_workspace"


@dataclass(frozen=True)
class ProjectSession:
    project: ExamProject
    workspace_root: Path
    dirty: bool = False

    @property
    def package_path(self) -> Path:
        return self.project.package_path

    @property
    def workdir(self) -> Path:
        return self.project.workdir

    @property
    def manifest(self) -> ProjectManifest:
        return self.project.manifest


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _resolved(path: Path) -> Path:
    return Path(path).expanduser().resolve()


def default_workspace_root(package_path: Path) -> Path:
    return _resolved(package_path).parent / WORKSPACE_DIR_NAME


def _workspace_name(package_path: Path) -> str:
    resolved = _resolved(package_path)
    digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:12]
    stem = "".join(
        char if char.isalnum() or char in ("-", "_") else "_"
        for char in resolved.stem
    ).strip("_")
    if not stem:
        stem = "project"
    return f"{stem}-{digest}"


def workspace_dir_for(package_path: Path, workspace_root: Path | None = None) -> Path:
    root = _resolved(workspace_root) if workspace_root is not None else default_workspace_root(package_path)
    return root / _workspace_name(package_path)


def _refresh_manifest(workdir: Path, manifest: ProjectManifest) -> ProjectManifest:
    data = manifest.to_dict()
    data["updated_at"] = _now_iso()
    asset_paths = sorted(set(data["assets"].values()))
    data["checksums"] = build_checksums(workdir, asset_paths)
    updated = ProjectManifest.from_dict(data)
    (workdir / "project.json").write_text(updated.to_json(), encoding="utf-8")
    validate_project(workdir, updated)
    return updated


def open_project(
    package_path: Path,
    *,
    workspace_root: Path | None = None,
) -> ProjectSession:
    resolved_package = _resolved(package_path)
    resolved_workspace_root = (
        _resolved(workspace_root)
        if workspace_root is not None
        else default_workspace_root(resolved_package)
    )
    target_dir = workspace_dir_for(resolved_package, resolved_workspace_root)
    project = ExamProjectPackage.open(resolved_package, target_dir)
    return ProjectSession(project=project, workspace_root=resolved_workspace_root)


def create_and_open_project(
    package_path: Path,
    *,
    name: str,
    student_id_digits: int = 10,
    workspace_root: Path | None = None,
) -> ProjectSession:
    resolved_package = _resolved(package_path)
    create_exam_project(
        resolved_package,
        name=name,
        student_id_digits=student_id_digits,
    )
    return open_project(resolved_package, workspace_root=workspace_root)


def import_and_open_project(
    legacy_root: Path,
    package_path: Path,
    *,
    name: str,
    workspace_root: Path | None = None,
) -> ProjectSession:
    resolved_package = _resolved(package_path)
    import_legacy_project(_resolved(legacy_root), resolved_package, name=name)
    return open_project(resolved_package, workspace_root=workspace_root)


def save_project(session: ProjectSession) -> ProjectSession:
    updated_manifest = _refresh_manifest(session.workdir, session.manifest)
    ExamProjectPackage.save(session.workdir, session.package_path)
    project = ExamProject(
        package_path=session.package_path,
        workdir=session.workdir,
        manifest=updated_manifest,
    )
    return ProjectSession(
        project=project,
        workspace_root=session.workspace_root,
        dirty=False,
    )


def save_project_as(session: ProjectSession, package_path: Path) -> ProjectSession:
    resolved_package = _resolved(package_path)
    updated_manifest = _refresh_manifest(session.workdir, session.manifest)
    ExamProjectPackage.save(session.workdir, resolved_package)
    project = ExamProject(
        package_path=resolved_package,
        workdir=session.workdir,
        manifest=updated_manifest,
    )
    return ProjectSession(
        project=project,
        workspace_root=session.workspace_root,
        dirty=False,
    )


def mark_dirty(session: ProjectSession) -> ProjectSession:
    return ProjectSession(
        project=session.project,
        workspace_root=session.workspace_root,
        dirty=True,
    )
