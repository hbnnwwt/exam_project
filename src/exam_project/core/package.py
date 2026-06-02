from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from exam_project.core.errors import ProjectPackageError
from exam_project.core.manifest import ProjectManifest
from exam_project.core.project import ExamProject


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


def _assert_inside_target(target_root: Path, path: Path) -> None:
    try:
        path.resolve().relative_to(target_root)
    except ValueError as exc:
        raise ProjectPackageError(f"Project package entry escapes target: {path}") from exc


def _remove_existing_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    if path.exists():
        shutil.rmtree(path)


def safe_extract_zip(package_path: Path, target_dir: Path) -> None:
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            infos = zf.infolist()
            for info in infos:
                _zip_entry_name(info.filename)

            target_dir.mkdir(parents=True, exist_ok=True)
            target_root = target_dir.resolve()
            for info in infos:
                name = _zip_entry_name(info.filename)
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
    def pack(workdir: Path, package_path: Path) -> None:
        if not workdir.is_dir():
            raise ProjectPackageError(f"Project workdir does not exist: {workdir}")

        package_path.parent.mkdir(parents=True, exist_ok=True)
        package_resolved = package_path.resolve()
        files = [
            path
            for path in workdir.rglob("*")
            if path.is_file() and path.resolve() != package_resolved
        ]
        files.sort(key=lambda path: path.relative_to(workdir).as_posix())

        with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in files:
                zf.write(path, path.relative_to(workdir).as_posix())

    @staticmethod
    def open(package_path: Path, target_dir: Path) -> ExamProject:
        _remove_existing_path(target_dir)
        target_dir.mkdir(parents=True)
        safe_extract_zip(package_path, target_dir)

        manifest_path = target_dir / "project.json"
        if not manifest_path.is_file():
            raise ProjectPackageError("Project package is missing project.json")

        manifest = ProjectManifest.from_json(manifest_path.read_text(encoding="utf-8"))
        return ExamProject(package_path=package_path, workdir=target_dir, manifest=manifest)

    @staticmethod
    def save(workdir: Path, package_path: Path) -> None:
        tmp_path = package_path.with_suffix(package_path.suffix + ".tmp")
        backup_path = package_path.with_suffix(package_path.suffix + ".bak")
        verify_root = Path(tempfile.mkdtemp(prefix="exam_project_verify_"))
        verify_dir = verify_root / "opened"

        try:
            _remove_existing_path(tmp_path)
            ExamProjectPackage.pack(workdir, tmp_path)
            ExamProjectPackage.open(tmp_path, verify_dir)
            if package_path.exists():
                shutil.copy2(package_path, backup_path)
            os.replace(tmp_path, package_path)
        finally:
            _remove_existing_path(verify_root)
            if tmp_path.exists():
                _remove_existing_path(tmp_path)
