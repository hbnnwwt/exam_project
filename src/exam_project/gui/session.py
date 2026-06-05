from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from exam_project.core.checksum import build_checksums
from exam_project.core.legacy_import import import_legacy_project
from exam_project.core.manifest import ProjectManifest
from exam_project.core.new_project import create_exam_project
from exam_project.core.package import ExamProjectPackage
from exam_project.core.project import ExamProject
from exam_project.core.validation import validate_project


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


def open_project(folder_path: Path) -> ProjectSession:
    """打开项目文件夹（新版文件夹模式）。"""
    resolved_folder = _resolved(folder_path)
    project = ExamProjectPackage.open_folder(resolved_folder)
    return ProjectSession(project=project, workspace_root=resolved_folder.parent)


def create_and_open_project(
    folder_path: Path,
    *,
    name: str,
    student_id_digits: int = 10,
) -> ProjectSession:
    """创建新项目文件夹并打开。"""
    resolved_folder = _resolved(folder_path)
    create_exam_project(
        resolved_folder,
        name=name,
        student_id_digits=student_id_digits,
    )
    return open_project(resolved_folder)


def import_and_open_project(
    legacy_root: Path,
    folder_path: Path,
    *,
    name: str,
) -> ProjectSession:
    """从旧系统导入到项目文件夹并打开。"""
    resolved_folder = _resolved(folder_path)
    import_legacy_project(_resolved(legacy_root), resolved_folder, name=name)
    return open_project(resolved_folder)


def _refresh_manifest(workdir: Path, manifest: ProjectManifest) -> ProjectManifest:
    data = manifest.to_dict()
    data["updated_at"] = _now_iso()
    asset_paths = sorted(set(data["assets"].values()))
    data["checksums"] = build_checksums(workdir, asset_paths)
    updated = ProjectManifest.from_dict(data)
    (workdir / "project.json").write_text(updated.to_json(), encoding="utf-8")
    validate_project(workdir, updated)
    return updated


def save_project(session: ProjectSession) -> ProjectSession:
    """保存项目（刷新 manifest 并重新打包 .examproj）。"""
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


def save_project_as(session: ProjectSession, folder_path: Path) -> ProjectSession:
    """另存为新的项目文件夹。"""
    import shutil

    resolved_folder = _resolved(folder_path)
    if resolved_folder.exists():
        raise ValueError(f"目标文件夹已存在: {resolved_folder}")

    shutil.copytree(session.workdir, resolved_folder)

    # 更新 package_path 为新文件夹内的 .examproj
    package_files = list(resolved_folder.glob("*.examproj"))
    if package_files:
        new_package_path = package_files[0]
    else:
        new_package_path = resolved_folder / f"{resolved_folder.name}.examproj"
        ExamProjectPackage.pack(resolved_folder, new_package_path)

    updated_manifest = _refresh_manifest(resolved_folder, session.manifest)
    project = ExamProject(
        package_path=new_package_path,
        workdir=resolved_folder,
        manifest=updated_manifest,
    )
    return ProjectSession(
        project=project,
        workspace_root=resolved_folder.parent,
        dirty=False,
    )


def mark_dirty(session: ProjectSession) -> ProjectSession:
    return ProjectSession(
        project=session.project,
        workspace_root=session.workspace_root,
        dirty=True,
    )
