from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from exam_project.core.errors import ProjectPackageError
from exam_project.core.manifest import ProjectManifest
from exam_project.core.project import ExamProject
from exam_project.core.validation import validate_project


def _zip_entry_name(name: str) -> str:
    if not isinstance(name, str) or not name:
        raise ProjectPackageError("Project package contains an empty path")
    if "\\" in name or ":" in name:
        raise ProjectPackageError(f"Project package contains an unsafe path: {name}")

    pure = PurePosixPath(name)
    parts = pure.parts
    if not parts or pure.is_absolute() or ".." in parts:
        raise ProjectPackageError(f"Project package contains an unsafe path: {name}")
    if pure.as_posix() != name:
        raise ProjectPackageError(f"Project package contains a non-canonical path: {name}")
    return name


def _raw_zip_entry_name(info: zipfile.ZipInfo) -> str:
    return getattr(info, "orig_filename", info.filename)


def _assert_inside_target(target_root: Path, path: Path) -> None:
    try:
        path.resolve().relative_to(target_root)
    except ValueError as exc:
        raise ProjectPackageError(f"Project package entry escapes target: {path}") from exc


def _assert_inside_root(root: Path, path: Path) -> None:
    try:
        path.resolve().relative_to(root)
    except ValueError as exc:
        raise ProjectPackageError(f"Project file escapes workdir: {path}") from exc


def _remove_existing_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    if path.exists():
        shutil.rmtree(path)


def _cleanup_path(path: Path) -> None:
    try:
        _remove_existing_path(path)
    except (FileNotFoundError, OSError):
        pass


def _assert_safe_replace_target(path: Path) -> None:
    resolved = path.resolve()
    anchor = Path(resolved.anchor)
    if resolved == anchor or resolved == resolved.parent:
        raise ProjectPackageError(f"Refusing to replace unsafe path: {path}")


def _replace_directory(source: Path, target: Path) -> None:
    _assert_safe_replace_target(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    old_parent = Path(
        tempfile.mkdtemp(prefix=f".{target.name}.old-", dir=target.parent)
    )
    old_target = old_parent / target.name
    try:
        if target.exists() or target.is_symlink():
            shutil.move(str(target), str(old_target))
        shutil.move(str(source), str(target))
    except Exception:
        restored_old = False
        if old_target.exists():
            if target.exists() or target.is_symlink():
                _remove_existing_path(target)
            if target.exists() or target.is_symlink():
                raise
            shutil.move(str(old_target), str(target))
            restored_old = True
        if not restored_old and old_target.exists():
            raise
        raise
    finally:
        if not old_target.exists():
            _cleanup_path(old_parent)


def _assert_safe_open_target(package_path: Path, target_dir: Path) -> None:
    _assert_safe_replace_target(target_dir)
    package_resolved = package_path.resolve()
    target_resolved = target_dir.resolve()
    try:
        package_resolved.relative_to(target_resolved)
    except ValueError:
        return
    else:
        raise ProjectPackageError(f"Refusing to open project into unsafe path: {target_dir}")


def _package_artifact_paths(package_path: Path) -> tuple[Path, Path, Path, Path]:
    backup_path = package_path.with_suffix(package_path.suffix + ".bak")
    return (
        package_path,
        package_path.with_suffix(package_path.suffix + ".tmp"),
        backup_path,
        backup_path.with_suffix(backup_path.suffix + ".tmp"),
    )


def _casefold_zip_name(name: str) -> str:
    return "/".join(part.casefold() for part in PurePosixPath(name).parts)


def _collect_zip_entries(infos: list[zipfile.ZipInfo]) -> dict[zipfile.ZipInfo, str]:
    entries: dict[zipfile.ZipInfo, str] = {}
    seen: set[str] = set()
    for info in infos:
        name = _zip_entry_name(_raw_zip_entry_name(info))
        casefold_name = _casefold_zip_name(name)
        if casefold_name in seen:
            raise ProjectPackageError(f"Project package contains duplicate path: {name}")
        seen.add(casefold_name)
        entries[info] = name
    return entries


def safe_extract_zip(package_path: Path, target_dir: Path) -> None:
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            entries = _collect_zip_entries(zf.infolist())

            target_dir.mkdir(parents=True, exist_ok=True)
            target_root = target_dir.resolve()
            for info, name in entries.items():
                destination = target_dir / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                _assert_inside_target(target_root, destination)
                with zf.open(info, "r") as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output)
    except ProjectPackageError:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise ProjectPackageError("Project package is not a valid ZIP file") from exc


class ExamProjectPackage:
    @staticmethod
    def pack(
        workdir: Path, package_path: Path, exclude_paths: Iterable[Path] = ()
    ) -> None:
        if not workdir.is_dir():
            raise ProjectPackageError(f"Project workdir does not exist: {workdir}")

        package_path.parent.mkdir(parents=True, exist_ok=True)
        workdir_resolved = workdir.resolve()
        excludes = {path.resolve() for path in _package_artifact_paths(package_path)}
        excludes.update(path.resolve() for path in exclude_paths)
        files = [
            path
            for path in workdir.rglob("*")
            if path.is_file() and not path.is_symlink() and path.resolve() not in excludes
        ]
        for path in files:
            _assert_inside_root(workdir_resolved, path)
        files.sort(key=lambda path: path.relative_to(workdir).as_posix())

        with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in files:
                zf.write(path, path.relative_to(workdir).as_posix())

    @staticmethod
    def open(package_path: Path, target_dir: Path) -> ExamProject:
        """从 .examproj 文件打开（兼容旧版，解压到 target_dir）。"""
        _assert_safe_open_target(package_path, target_dir)
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        staging_root = Path(
            tempfile.mkdtemp(prefix=f".{target_dir.name}.open-", dir=target_dir.parent)
        )
        staging_dir = staging_root / "opened"
        try:
            safe_extract_zip(package_path, staging_dir)
            manifest_path = staging_dir / "project.json"
            if not manifest_path.is_file():
                raise ProjectPackageError("Project package is missing project.json")

            manifest = ProjectManifest.from_json(manifest_path.read_text(encoding="utf-8"))
            validate_project(staging_dir, manifest)
            _replace_directory(staging_dir, target_dir)
            return ExamProject(package_path=package_path, workdir=target_dir, manifest=manifest)
        finally:
            _cleanup_path(staging_root)

    @staticmethod
    def open_folder(folder_path: Path) -> ExamProject:
        """从项目文件夹直接打开（新版文件夹模式）。"""
        folder = folder_path.resolve()
        if not folder.is_dir():
            raise ProjectPackageError(f"项目文件夹不存在: {folder}")

        manifest_path = folder / "project.json"
        if not manifest_path.is_file():
            raise ProjectPackageError("项目文件夹内缺少 project.json")

        manifest = ProjectManifest.from_json(manifest_path.read_text(encoding="utf-8"))
        validate_project(folder, manifest)

        # 查找或自动创建 .examproj 归档包
        package_files = list(folder.glob("*.examproj"))
        if package_files:
            package_path = package_files[0]
        else:
            package_path = folder / f"{folder.name}.examproj"
            ExamProjectPackage.pack(folder, package_path)

        return ExamProject(package_path=package_path, workdir=folder, manifest=manifest)

    @staticmethod
    def save(workdir: Path, package_path: Path) -> None:
        tmp_path = package_path.with_suffix(package_path.suffix + ".tmp")
        backup_path = package_path.with_suffix(package_path.suffix + ".bak")
        backup_tmp = backup_path.with_suffix(backup_path.suffix + ".tmp")
        verify_root = Path(tempfile.mkdtemp(prefix="exam_project_verify_"))
        verify_dir = verify_root / "opened"

        try:
            _remove_existing_path(tmp_path)
            _remove_existing_path(backup_tmp)
            ExamProjectPackage.pack(
                workdir,
                tmp_path,
                exclude_paths=(package_path, tmp_path, backup_path, backup_tmp),
            )
            ExamProjectPackage.open(tmp_path, verify_dir)
            if package_path.exists():
                _remove_existing_path(backup_path)
                shutil.copy2(package_path, backup_tmp)
                os.replace(backup_tmp, backup_path)
            os.replace(tmp_path, package_path)
        finally:
            _cleanup_path(verify_root)
            if tmp_path.exists():
                _cleanup_path(tmp_path)
            if backup_tmp.exists():
                _cleanup_path(backup_tmp)
