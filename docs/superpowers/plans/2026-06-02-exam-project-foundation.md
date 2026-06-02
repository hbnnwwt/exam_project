# Exam Project Package Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundation for `.examproj` files: manifest, checksums, safe ZIP packaging, project runtime objects, business validation, and legacy asset import.

**Architecture:** Keep project packaging in `exam_project.core`; do not let recognition or grading algorithms know about `.examproj`. The foundation writes and opens a temporary working directory, validates assets, and exposes explicit paths and loaded data through `ExamProject`.

**Tech Stack:** Python 3.11+, standard library `zipfile`, `hashlib`, `tempfile`, `dataclasses`, `pathlib`; `openpyxl` for answer workbook validation; `pytest` for tests.

---

## Scope Check

The confirmed spec covers several independent subsystems:

- Project package core
- Answer sheet designer migration
- Recognition and calibration migration
- Grading migration
- Streamlit application shell

This plan implements only the first subsystem: the project package foundation. It is intentionally narrow because every later subsystem depends on these interfaces. Follow-up plans should be written for answer sheet migration, recognition and grading migration, then Streamlit UI.

## File Structure

Create this structure:

```text
exam_project/
  pyproject.toml
  README.md
  plan.md
  src/
    exam_project/
      __init__.py
      cli.py
      core/
        __init__.py
        checksum.py
        errors.py
        manifest.py
        package.py
        project.py
        validation.py
        legacy_import.py
  tests/
    core/
      test_checksum.py
      test_manifest.py
      test_package.py
      test_project.py
      test_validation.py
      test_legacy_import.py
    test_cli.py
```

Responsibilities:

- `checksum.py`: SHA-256 calculation and checksum map generation.
- `errors.py`: domain-specific exceptions with user-facing messages.
- `manifest.py`: `ProjectManifest` dataclass, JSON load and dump, asset path validation.
- `package.py`: safe unpack, pack, open, save, atomic replace, backup.
- `project.py`: `ExamProject` runtime object and `ProjectContext`.
- `validation.py`: asset existence, checksum, and layout/answer consistency validation.
- `legacy_import.py`: import old global assets into a new `.examproj`.
- `cli.py`: small command surface for inspect and legacy import.

## Task 1: Project Skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `src/exam_project/__init__.py`
- Create: `src/exam_project/core/__init__.py`
- Create: `tests/test_imports.py`

- [ ] **Step 1: Write the failing import test**

Create `tests/test_imports.py`:

```python
import exam_project


def test_package_imports():
    assert exam_project.__version__ == "0.1.0"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python -m pytest tests/test_imports.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'exam_project'`.

- [ ] **Step 3: Add packaging metadata**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "exam-project"
version = "0.1.0"
description = "Single-file exam project package for answer sheet design, calibration, recognition, and grading."
requires-python = ">=3.11"
dependencies = [
    "openpyxl>=3.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
]

[project.scripts]
exam-project = "exam_project.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = "-q"
```

Create `src/exam_project/__init__.py`:

```python
"""Exam project package foundation."""

__version__ = "0.1.0"
```

Create `src/exam_project/core/__init__.py`:

```python
"""Core project package primitives."""
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
python -m pytest tests/test_imports.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/exam_project/__init__.py src/exam_project/core/__init__.py tests/test_imports.py
git commit -m "chore: add project skeleton"
```

## Task 2: Domain Errors

**Files:**
- Create: `src/exam_project/core/errors.py`
- Test: `tests/core/test_errors.py`

- [ ] **Step 1: Write failing tests for user-facing errors**

Create `tests/core/test_errors.py`:

```python
from exam_project.core.errors import ProjectError, ProjectValidationError


def test_project_error_keeps_user_message():
    err = ProjectError("项目无法打开")
    assert str(err) == "项目无法打开"
    assert err.user_message == "项目无法打开"


def test_validation_error_records_code():
    err = ProjectValidationError("参考答案与布局不一致", code="answer_layout_mismatch")
    assert err.code == "answer_layout_mismatch"
    assert err.user_message == "参考答案与布局不一致"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/core/test_errors.py -v
```

Expected: FAIL because `exam_project.core.errors` does not exist.

- [ ] **Step 3: Implement errors**

Create `src/exam_project/core/errors.py`:

```python
class ProjectError(Exception):
    """Base error with a message suitable for UI display."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


class ProjectPackageError(ProjectError):
    """Raised for invalid or corrupted .examproj containers."""


class ProjectValidationError(ProjectError):
    """Raised when project assets are present but inconsistent."""

    def __init__(self, user_message: str, code: str):
        super().__init__(user_message)
        self.code = code
```

- [ ] **Step 4: Run tests**

Run:

```bash
python -m pytest tests/core/test_errors.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/exam_project/core/errors.py tests/core/test_errors.py
git commit -m "feat: add project domain errors"
```

## Task 3: Manifest Model and Safe Asset Paths

**Files:**
- Create: `src/exam_project/core/manifest.py`
- Test: `tests/core/test_manifest.py`

- [ ] **Step 1: Write failing manifest tests**

Create `tests/core/test_manifest.py`:

```python
import json

import pytest

from exam_project.core.errors import ProjectValidationError
from exam_project.core.manifest import ProjectManifest, validate_asset_path


def test_manifest_round_trip_json():
    manifest = ProjectManifest(
        schema_version=1,
        project_id="project-1",
        name="期末考试",
        created_at="2026-06-02T20:00:00+08:00",
        updated_at="2026-06-02T20:30:00+08:00",
        assets={
            "design": "design/answer_sheet.json",
            "layout": "config/sheet_layout.json",
            "baseline": "config/blank_baseline.json",
            "answers": "answers/reference_answers.xlsx",
        },
        exam={"student_id_digits": 10, "question_types": ["choice", "judge"]},
        checksums={"config/sheet_layout.json": "sha256:" + "1" * 64},
    )
    loaded = ProjectManifest.from_json(manifest.to_json())
    assert loaded == manifest
    assert json.loads(loaded.to_json())["name"] == "期末考试"


@pytest.mark.parametrize(
    "path",
    [
        "../evil.txt",
        "/absolute/path.txt",
        "C:/absolute/path.txt",
        "config/../evil.txt",
        "",
    ],
)
def test_rejects_unsafe_asset_paths(path):
    with pytest.raises(ProjectValidationError):
        validate_asset_path(path)


def test_accepts_relative_asset_path():
    assert validate_asset_path("config/sheet_layout.json") == "config/sheet_layout.json"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/core/test_manifest.py -v
```

Expected: FAIL because `ProjectManifest` is not defined.

- [ ] **Step 3: Implement manifest**

Create `src/exam_project/core/manifest.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import PurePosixPath
from typing import Any

from exam_project.core.errors import ProjectValidationError


REQUIRED_ASSETS = ("design", "layout", "answers")


def validate_asset_path(path: str) -> str:
    if not isinstance(path, str) or not path.strip():
        raise ProjectValidationError("项目资产路径不能为空", code="invalid_asset_path")
    if "\\" in path:
        raise ProjectValidationError(f"项目资产路径不能使用反斜杠: {path}", code="invalid_asset_path")
    pure = PurePosixPath(path)
    parts = pure.parts
    if pure.is_absolute() or ".." in parts or ":" in path:
        raise ProjectValidationError(f"项目资产路径不安全: {path}", code="invalid_asset_path")
    return path


@dataclass(frozen=True)
class ProjectManifest:
    schema_version: int
    project_id: str
    name: str
    created_at: str
    updated_at: str
    assets: dict[str, str]
    exam: dict[str, Any]
    checksums: dict[str, str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectManifest":
        for key in ("schema_version", "project_id", "name", "created_at", "updated_at", "assets", "exam", "checksums"):
            if key not in data:
                raise ProjectValidationError(f"project.json 缺少字段: {key}", code="manifest_missing_field")
        assets = dict(data["assets"])
        for asset_key in REQUIRED_ASSETS:
            if asset_key not in assets:
                raise ProjectValidationError(f"project.json 缺少资产声明: {asset_key}", code="manifest_missing_asset")
        for path in assets.values():
            if path:
                validate_asset_path(path)
        for path in data["checksums"]:
            validate_asset_path(path)
        return cls(
            schema_version=int(data["schema_version"]),
            project_id=str(data["project_id"]),
            name=str(data["name"]),
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
            assets=assets,
            exam=dict(data["exam"]),
            checksums=dict(data["checksums"]),
        )

    @classmethod
    def from_json(cls, text: str) -> "ProjectManifest":
        return cls.from_dict(json.loads(text))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "assets": dict(self.assets),
            "exam": dict(self.exam),
            "checksums": dict(self.checksums),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
```

- [ ] **Step 4: Run tests**

Run:

```bash
python -m pytest tests/core/test_manifest.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/exam_project/core/manifest.py tests/core/test_manifest.py
git commit -m "feat: add project manifest model"
```

## Task 4: Checksums

**Files:**
- Create: `src/exam_project/core/checksum.py`
- Test: `tests/core/test_checksum.py`

- [ ] **Step 1: Write failing checksum tests**

Create `tests/core/test_checksum.py`:

```python
from pathlib import Path

from exam_project.core.checksum import checksum_file, build_checksums


def test_checksum_file_uses_sha256(tmp_path: Path):
    path = tmp_path / "sample.txt"
    path.write_text("abc", encoding="utf-8")
    assert checksum_file(path) == "sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_build_checksums_uses_posix_paths(tmp_path: Path):
    root = tmp_path / "project"
    (root / "config").mkdir(parents=True)
    (root / "config" / "sheet_layout.json").write_text("{}", encoding="utf-8")
    result = build_checksums(root, ["config/sheet_layout.json"])
    assert set(result) == {"config/sheet_layout.json"}
    assert result["config/sheet_layout.json"].startswith("sha256:")
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/core/test_checksum.py -v
```

Expected: FAIL because `checksum.py` does not exist.

- [ ] **Step 3: Implement checksums**

Create `src/exam_project/core/checksum.py`:

```python
from __future__ import annotations

import hashlib
from pathlib import Path

from exam_project.core.manifest import validate_asset_path


def checksum_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def build_checksums(root: Path, relative_paths: list[str]) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for rel in relative_paths:
        safe_rel = validate_asset_path(rel)
        path = root / safe_rel
        if path.exists() and path.is_file():
            checksums[safe_rel] = checksum_file(path)
    return checksums
```

- [ ] **Step 4: Run tests**

Run:

```bash
python -m pytest tests/core/test_checksum.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/exam_project/core/checksum.py tests/core/test_checksum.py
git commit -m "feat: add project asset checksums"
```

## Task 5: Project Package Open and Save

**Files:**
- Create: `src/exam_project/core/package.py`
- Test: `tests/core/test_package.py`

- [ ] **Step 1: Write failing package tests**

Create `tests/core/test_package.py`:

```python
import json
import zipfile
from pathlib import Path

import pytest

from exam_project.core.errors import ProjectPackageError
from exam_project.core.package import ExamProjectPackage, safe_extract_zip


def write_minimal_workdir(root: Path):
    (root / "design").mkdir()
    (root / "config").mkdir()
    (root / "answers").mkdir()
    (root / "design" / "answer_sheet.json").write_text("{}", encoding="utf-8")
    (root / "config" / "sheet_layout.json").write_text(
        json.dumps(
            {
                "layout": {},
                "scoring": {"choice_score": 1, "judge_score": 1, "essay_max_score": 20},
                "choice": {"question_start": 1, "question_count": 1, "options": ["A", "B"]},
            }
        ),
        encoding="utf-8",
    )
    (root / "answers" / "reference_answers.xlsx").write_bytes(b"not-a-real-xlsx")
    (root / "project.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project_id": "p1",
                "name": "期末考试",
                "created_at": "2026-06-02T20:00:00+08:00",
                "updated_at": "2026-06-02T20:00:00+08:00",
                "assets": {
                    "design": "design/answer_sheet.json",
                    "layout": "config/sheet_layout.json",
                    "answers": "answers/reference_answers.xlsx",
                    "baseline": "config/blank_baseline.json",
                },
                "exam": {"student_id_digits": 10, "question_types": ["choice"]},
                "checksums": {},
            }
        ),
        encoding="utf-8",
    )


def test_pack_and_open_project(tmp_path: Path):
    workdir = tmp_path / "work"
    workdir.mkdir()
    write_minimal_workdir(workdir)
    package_path = tmp_path / "sample.examproj"

    ExamProjectPackage.pack(workdir, package_path)
    opened = ExamProjectPackage.open(package_path, tmp_path / "opened")

    assert opened.manifest.name == "期末考试"
    assert (opened.workdir / "config" / "sheet_layout.json").exists()


def test_safe_extract_rejects_path_traversal(tmp_path: Path):
    package_path = tmp_path / "evil.examproj"
    with zipfile.ZipFile(package_path, "w") as zf:
        zf.writestr("../evil.txt", "bad")

    with pytest.raises(ProjectPackageError):
        safe_extract_zip(package_path, tmp_path / "out")


def test_save_creates_backup(tmp_path: Path):
    workdir = tmp_path / "work"
    workdir.mkdir()
    write_minimal_workdir(workdir)
    package_path = tmp_path / "sample.examproj"
    ExamProjectPackage.pack(workdir, package_path)

    (workdir / "project.json").write_text(
        (workdir / "project.json").read_text(encoding="utf-8").replace("期末考试", "期中考试"),
        encoding="utf-8",
    )
    ExamProjectPackage.save(workdir, package_path)

    assert package_path.exists()
    assert package_path.with_suffix(".examproj.bak").exists()
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/core/test_package.py -v
```

Expected: FAIL because `ExamProjectPackage` is not defined.

- [ ] **Step 3: Implement package handling**

Create `src/exam_project/core/package.py`:

```python
from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path, PurePosixPath

from exam_project.core.errors import ProjectPackageError
from exam_project.core.manifest import ProjectManifest
from exam_project.core.project import ExamProject


def _is_safe_zip_name(name: str) -> bool:
    pure = PurePosixPath(name)
    return bool(name) and not pure.is_absolute() and ".." not in pure.parts and ":" not in name


def safe_extract_zip(package_path: Path, target_dir: Path) -> None:
    try:
        with zipfile.ZipFile(package_path, "r") as zf:
            for info in zf.infolist():
                if not _is_safe_zip_name(info.filename):
                    raise ProjectPackageError(f"项目包包含不安全路径: {info.filename}")
            zf.extractall(target_dir)
    except zipfile.BadZipFile as exc:
        raise ProjectPackageError("项目包不是合法的 ZIP 文件") from exc


class ExamProjectPackage:
    @staticmethod
    def pack(workdir: Path, package_path: Path) -> None:
        package_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(p for p in workdir.rglob("*") if p.is_file()):
                rel = path.relative_to(workdir).as_posix()
                zf.write(path, rel)

    @staticmethod
    def open(package_path: Path, target_dir: Path) -> ExamProject:
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True)
        safe_extract_zip(package_path, target_dir)
        manifest_path = target_dir / "project.json"
        if not manifest_path.exists():
            raise ProjectPackageError("项目包缺少 project.json")
        manifest = ProjectManifest.from_json(manifest_path.read_text(encoding="utf-8"))
        return ExamProject(package_path=package_path, workdir=target_dir, manifest=manifest)

    @staticmethod
    def save(workdir: Path, package_path: Path) -> None:
        tmp_path = package_path.with_suffix(package_path.suffix + ".tmp")
        backup_path = package_path.with_suffix(package_path.suffix + ".bak")
        if tmp_path.exists():
            tmp_path.unlink()
        ExamProjectPackage.pack(workdir, tmp_path)
        verify_dir = workdir.parent / (workdir.name + "_verify")
        try:
            ExamProjectPackage.open(tmp_path, verify_dir)
            if package_path.exists():
                shutil.copy2(package_path, backup_path)
            os.replace(tmp_path, package_path)
        finally:
            if verify_dir.exists():
                shutil.rmtree(verify_dir)
            if tmp_path.exists():
                tmp_path.unlink()
```

- [ ] **Step 4: Add temporary project object needed by package tests**

Create `src/exam_project/core/project.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from exam_project.core.manifest import ProjectManifest


@dataclass(frozen=True)
class ExamProject:
    package_path: Path
    workdir: Path
    manifest: ProjectManifest
```

- [ ] **Step 5: Run tests**

Run:

```bash
python -m pytest tests/core/test_package.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/exam_project/core/package.py src/exam_project/core/project.py tests/core/test_package.py
git commit -m "feat: add exam project package handling"
```

## Task 6: Project Runtime Object and Context

**Files:**
- Modify: `src/exam_project/core/project.py`
- Test: `tests/core/test_project.py`

- [ ] **Step 1: Write failing runtime tests**

Create `tests/core/test_project.py`:

```python
import json
from pathlib import Path

from exam_project.core.manifest import ProjectManifest
from exam_project.core.project import ExamProject, ProjectContext


def make_project(tmp_path: Path) -> ExamProject:
    workdir = tmp_path / "work"
    workdir.mkdir()
    (workdir / "config").mkdir()
    (workdir / "config" / "sheet_layout.json").write_text('{"layout": {}, "scoring": {}}', encoding="utf-8")
    manifest = ProjectManifest(
        schema_version=1,
        project_id="p1",
        name="期末考试",
        created_at="2026-06-02T20:00:00+08:00",
        updated_at="2026-06-02T20:00:00+08:00",
        assets={
            "design": "design/answer_sheet.json",
            "layout": "config/sheet_layout.json",
            "answers": "answers/reference_answers.xlsx",
            "baseline": "config/blank_baseline.json",
        },
        exam={"student_id_digits": 10, "question_types": ["choice"]},
        checksums={},
    )
    return ExamProject(package_path=tmp_path / "x.examproj", workdir=workdir, manifest=manifest)


def test_project_resolves_asset_paths(tmp_path: Path):
    project = make_project(tmp_path)
    assert project.asset_path("layout") == tmp_path / "work" / "config" / "sheet_layout.json"
    assert project.load_layout() == {"layout": {}, "scoring": {}}


def test_project_context_switches_current_project(tmp_path: Path):
    context = ProjectContext()
    project = make_project(tmp_path)
    assert context.current is None
    context.set_current(project)
    assert context.require_current().manifest.name == "期末考试"
    context.clear()
    assert context.current is None
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/core/test_project.py -v
```

Expected: FAIL because `asset_path`, `load_layout`, and `ProjectContext` are missing.

- [ ] **Step 3: Expand project runtime object**

Replace `src/exam_project/core/project.py` with:

```python
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
    def __init__(self):
        self.current: ExamProject | None = None

    def set_current(self, project: ExamProject) -> None:
        self.current = project

    def require_current(self) -> ExamProject:
        if self.current is None:
            raise ProjectError("当前未打开考试项目")
        return self.current

    def clear(self) -> None:
        self.current = None
```

- [ ] **Step 4: Run tests**

Run:

```bash
python -m pytest tests/core/test_project.py tests/core/test_package.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/exam_project/core/project.py tests/core/test_project.py
git commit -m "feat: add exam project runtime context"
```

## Task 7: Asset and Business Validation

**Files:**
- Create: `src/exam_project/core/validation.py`
- Test: `tests/core/test_validation.py`

- [ ] **Step 1: Write failing validation tests**

Create `tests/core/test_validation.py`:

```python
import json
from pathlib import Path

import openpyxl
import pytest

from exam_project.core.errors import ProjectValidationError
from exam_project.core.validation import classify_question, validate_answer_workbook


def make_xlsx(path: Path, answers: dict[int, str]):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.cell(row=1, column=1, value="学号")
    ws.cell(row=2, column=1, value="参考答案")
    for idx, (q, ans) in enumerate(sorted(answers.items()), start=2):
        ws.cell(row=1, column=idx, value=q)
        ws.cell(row=2, column=idx, value=ans)
    wb.save(path)


def test_classify_question_from_layout():
    layout = {
        "choice": {"question_start": 1, "question_count": 2, "options": ["A", "B"]},
        "judge": {"question_start": 3, "question_count": 1, "options": ["T", "F"]},
    }
    assert classify_question(1, layout) == "choice"
    assert classify_question(3, layout) == "judge"
    assert classify_question(9, layout) == "essay"


def test_validate_answer_workbook_accepts_matching_answers(tmp_path: Path):
    layout = {
        "choice": {"question_start": 1, "question_count": 2, "options": ["A", "B"]},
        "judge": {"question_start": 3, "question_count": 1, "options": ["T", "F"]},
    }
    path = tmp_path / "answers.xlsx"
    make_xlsx(path, {1: "A", 2: "B", 3: "T"})
    validate_answer_workbook(path, layout)


def test_validate_answer_workbook_rejects_mismatch(tmp_path: Path):
    layout = {
        "choice": {"question_start": 1, "question_count": 3, "options": ["A", "B"]},
        "judge": {"question_start": 4, "question_count": 1, "options": ["T", "F"]},
    }
    path = tmp_path / "answers.xlsx"
    make_xlsx(path, {1: "A", 2: "B", 3: "T"})
    with pytest.raises(ProjectValidationError) as exc:
        validate_answer_workbook(path, layout)
    assert "第 3 题答案为 T" in exc.value.user_message
    assert exc.value.code == "answer_layout_mismatch"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/core/test_validation.py -v
```

Expected: FAIL because `validation.py` does not exist.

- [ ] **Step 3: Implement validation**

Create `src/exam_project/core/validation.py`:

```python
from __future__ import annotations

from pathlib import Path

import openpyxl

from exam_project.core.errors import ProjectValidationError


QUESTION_TYPES = ("choice", "judge", "essay")


def classify_question(q_num: int, layout: dict) -> str:
    for q_type in QUESTION_TYPES:
        cfg = layout.get(q_type)
        if not isinstance(cfg, dict):
            continue
        start = cfg.get("question_start")
        count = cfg.get("question_count")
        if start is None or count is None:
            continue
        end = int(start) + int(count) - 1
        if int(start) <= q_num <= end:
            return q_type
    return "essay"


def _options_for(q_type: str, layout: dict) -> list[str] | None:
    cfg = layout.get(q_type)
    if not isinstance(cfg, dict):
        return None
    options = cfg.get("options")
    if options is None:
        return None
    return [str(item) for item in options]


def validate_answer_workbook(path: Path, layout: dict) -> None:
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    for col in range(2, ws.max_column + 1):
        q_raw = ws.cell(row=1, column=col).value
        answer_raw = ws.cell(row=2, column=col).value
        if q_raw is None or answer_raw is None:
            continue
        try:
            q_num = int(q_raw)
        except (TypeError, ValueError) as exc:
            raise ProjectValidationError(f"参考答案表头包含非法题号: {q_raw}", code="invalid_question_number") from exc
        answer = str(answer_raw).strip()
        q_type = classify_question(q_num, layout)
        options = _options_for(q_type, layout)
        if options is not None and answer not in options:
            allowed = "/".join(options)
            raise ProjectValidationError(
                f"参考答案与答题卡布局不一致。第 {q_num} 题答案为 {answer}，"
                f"但布局将第 {q_num} 题声明为 {q_type}，允许答案为 {allowed}。",
                code="answer_layout_mismatch",
            )
```

- [ ] **Step 4: Run tests**

Run:

```bash
python -m pytest tests/core/test_validation.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/exam_project/core/validation.py tests/core/test_validation.py
git commit -m "feat: validate answers against layout"
```

## Task 8: Full Project Validation

**Files:**
- Modify: `src/exam_project/core/validation.py`
- Modify: `src/exam_project/core/package.py`
- Test: `tests/core/test_package_validation.py`

- [ ] **Step 1: Write failing tests for open-time validation**

Create `tests/core/test_package_validation.py`:

```python
import json
from pathlib import Path

import openpyxl
import pytest

from exam_project.core.errors import ProjectValidationError
from exam_project.core.package import ExamProjectPackage


def write_xlsx(path: Path, answers: dict[int, str]):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.cell(row=1, column=1, value="学号")
    ws.cell(row=2, column=1, value="参考答案")
    for idx, (q, ans) in enumerate(sorted(answers.items()), start=2):
        ws.cell(row=1, column=idx, value=q)
        ws.cell(row=2, column=idx, value=ans)
    wb.save(path)


def write_project(workdir: Path, layout: dict, answers: dict[int, str]):
    (workdir / "design").mkdir()
    (workdir / "config").mkdir()
    (workdir / "answers").mkdir()
    (workdir / "design" / "answer_sheet.json").write_text("{}", encoding="utf-8")
    (workdir / "config" / "sheet_layout.json").write_text(json.dumps(layout), encoding="utf-8")
    write_xlsx(workdir / "answers" / "reference_answers.xlsx", answers)
    manifest = {
        "schema_version": 1,
        "project_id": "p1",
        "name": "期末考试",
        "created_at": "2026-06-02T20:00:00+08:00",
        "updated_at": "2026-06-02T20:00:00+08:00",
        "assets": {
            "design": "design/answer_sheet.json",
            "layout": "config/sheet_layout.json",
            "answers": "answers/reference_answers.xlsx",
            "baseline": "config/blank_baseline.json",
        },
        "exam": {"student_id_digits": 10, "question_types": ["choice", "judge"]},
        "checksums": {},
    }
    (workdir / "project.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_open_rejects_answer_layout_mismatch(tmp_path: Path):
    workdir = tmp_path / "work"
    workdir.mkdir()
    layout = {
        "layout": {},
        "scoring": {},
        "choice": {"question_start": 1, "question_count": 3, "options": ["A", "B"]},
        "judge": {"question_start": 4, "question_count": 1, "options": ["T", "F"]},
    }
    write_project(workdir, layout, {1: "A", 2: "B", 3: "T"})
    package_path = tmp_path / "bad.examproj"
    ExamProjectPackage.pack(workdir, package_path)

    with pytest.raises(ProjectValidationError):
        ExamProjectPackage.open(package_path, tmp_path / "opened")
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/core/test_package_validation.py -v
```

Expected: FAIL because package open does not validate business consistency.

- [ ] **Step 3: Add full project validation**

Append to `src/exam_project/core/validation.py`:

```python
import json

from exam_project.core.checksum import checksum_file
from exam_project.core.manifest import ProjectManifest


def validate_project_assets(workdir: Path, manifest: ProjectManifest) -> None:
    for asset_key in ("design", "layout", "answers"):
        rel = manifest.assets[asset_key]
        path = workdir / rel
        if not path.exists():
            raise ProjectValidationError(f"项目缺少资产: {rel}", code="missing_asset")

    baseline_rel = manifest.assets.get("baseline")
    if baseline_rel:
        baseline_path = workdir / baseline_rel
        if not baseline_path.exists():
            return

    for rel, expected in manifest.checksums.items():
        path = workdir / rel
        if path.exists() and checksum_file(path) != expected:
            raise ProjectValidationError(f"项目资产校验失败: {rel}", code="checksum_mismatch")


def validate_project_business_rules(workdir: Path, manifest: ProjectManifest) -> None:
    layout_path = workdir / manifest.assets["layout"]
    answers_path = workdir / manifest.assets["answers"]
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    validate_answer_workbook(answers_path, layout)


def validate_project(workdir: Path, manifest: ProjectManifest) -> None:
    validate_project_assets(workdir, manifest)
    validate_project_business_rules(workdir, manifest)
```

Modify `ExamProjectPackage.open()` in `src/exam_project/core/package.py`:

```python
    @staticmethod
    def open(package_path: Path, target_dir: Path) -> ExamProject:
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True)
        safe_extract_zip(package_path, target_dir)
        manifest_path = target_dir / "project.json"
        if not manifest_path.exists():
            raise ProjectPackageError("项目包缺少 project.json")
        manifest = ProjectManifest.from_json(manifest_path.read_text(encoding="utf-8"))
        from exam_project.core.validation import validate_project
        validate_project(target_dir, manifest)
        return ExamProject(package_path=package_path, workdir=target_dir, manifest=manifest)
```

- [ ] **Step 4: Run package and validation tests**

Run:

```bash
python -m pytest tests/core/test_package.py tests/core/test_package_validation.py tests/core/test_validation.py -v
```

Expected: PASS. If `tests/core/test_package.py::test_pack_and_open_project` fails because it writes a fake xlsx, update that test to create a real xlsx using `openpyxl` and a matching layout.

- [ ] **Step 5: Commit**

```bash
git add src/exam_project/core/validation.py src/exam_project/core/package.py tests/core/test_package_validation.py tests/core/test_package.py
git commit -m "feat: validate project packages on open"
```

## Task 9: Legacy Asset Import

**Files:**
- Create: `src/exam_project/core/legacy_import.py`
- Test: `tests/core/test_legacy_import.py`

- [ ] **Step 1: Write failing legacy import test**

Create `tests/core/test_legacy_import.py`:

```python
import json
from pathlib import Path

import openpyxl

from exam_project.core.legacy_import import import_legacy_project
from exam_project.core.package import ExamProjectPackage


def write_xlsx(path: Path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.cell(row=1, column=1, value="学号")
    ws.cell(row=2, column=1, value="参考答案")
    ws.cell(row=1, column=2, value=1)
    ws.cell(row=2, column=2, value="A")
    wb.save(path)


def test_import_legacy_project_creates_examproj(tmp_path: Path):
    legacy = tmp_path / "legacy"
    (legacy / "config").mkdir(parents=True)
    (legacy / "config" / "sheet_layout.json").write_text(
        json.dumps(
            {
                "layout": {},
                "scoring": {"choice_score": 1},
                "choice": {"question_start": 1, "question_count": 1, "options": ["A", "B"]},
            }
        ),
        encoding="utf-8",
    )
    (legacy / "config" / "blank_baseline.json").write_text("{}", encoding="utf-8")
    write_xlsx(legacy / "参考答案.xlsx")

    package_path = tmp_path / "imported.examproj"
    import_legacy_project(legacy, package_path, name="导入项目")
    project = ExamProjectPackage.open(package_path, tmp_path / "opened")

    assert project.manifest.name == "导入项目"
    assert project.layout_path.exists()
    assert project.answers_path.exists()
    assert project.baseline_path.exists()
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
python -m pytest tests/core/test_legacy_import.py -v
```

Expected: FAIL because `legacy_import.py` does not exist.

- [ ] **Step 3: Implement legacy import**

Create `src/exam_project/core/legacy_import.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
import json
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

from exam_project.core.checksum import build_checksums
from exam_project.core.manifest import ProjectManifest
from exam_project.core.package import ExamProjectPackage
from exam_project.core.validation import validate_project


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def import_legacy_project(legacy_root: Path, package_path: Path, name: str) -> None:
    layout_src = legacy_root / "config" / "sheet_layout.json"
    answers_src = legacy_root / "参考答案.xlsx"
    baseline_src = legacy_root / "config" / "blank_baseline.json"
    if not layout_src.exists():
        raise FileNotFoundError(f"缺少旧版布局文件: {layout_src}")
    if not answers_src.exists():
        raise FileNotFoundError(f"缺少旧版参考答案: {answers_src}")

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
        if baseline_src.exists():
            shutil.copy2(baseline_src, workdir / "config" / "blank_baseline.json")

        asset_paths = [
            "design/answer_sheet.json",
            "config/sheet_layout.json",
            "answers/reference_answers.xlsx",
        ]
        if (workdir / "config" / "blank_baseline.json").exists():
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
        ExamProjectPackage.pack(workdir, package_path)
```

- [ ] **Step 4: Run test**

Run:

```bash
python -m pytest tests/core/test_legacy_import.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/exam_project/core/legacy_import.py tests/core/test_legacy_import.py
git commit -m "feat: import legacy assets into exam project"
```

## Task 10: CLI Inspect and Legacy Import

**Files:**
- Create: `src/exam_project/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

import openpyxl


def write_xlsx(path: Path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.cell(row=1, column=1, value="学号")
    ws.cell(row=2, column=1, value="参考答案")
    ws.cell(row=1, column=2, value=1)
    ws.cell(row=2, column=2, value="A")
    wb.save(path)


def test_cli_import_legacy_and_inspect(tmp_path: Path):
    legacy = tmp_path / "legacy"
    (legacy / "config").mkdir(parents=True)
    (legacy / "config" / "sheet_layout.json").write_text(
        json.dumps(
            {
                "layout": {},
                "scoring": {},
                "choice": {"question_start": 1, "question_count": 1, "options": ["A", "B"]},
            }
        ),
        encoding="utf-8",
    )
    write_xlsx(legacy / "参考答案.xlsx")
    package_path = tmp_path / "demo.examproj"

    import_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "exam_project.cli",
            "import-legacy",
            str(legacy),
            str(package_path),
            "--name",
            "演示项目",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert import_result.returncode == 0
    assert package_path.exists()

    inspect_result = subprocess.run(
        [sys.executable, "-m", "exam_project.cli", "inspect", str(package_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert inspect_result.returncode == 0
    assert "演示项目" in inspect_result.stdout
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
python -m pytest tests/test_cli.py -v
```

Expected: FAIL because `exam_project.cli` does not exist.

- [ ] **Step 3: Implement CLI**

Create `src/exam_project/cli.py`:

```python
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from exam_project.core.errors import ProjectError
from exam_project.core.legacy_import import import_legacy_project
from exam_project.core.package import ExamProjectPackage


def _cmd_import_legacy(args: argparse.Namespace) -> int:
    import_legacy_project(Path(args.legacy_root), Path(args.output), name=args.name)
    print(f"已创建考试项目: {args.output}")
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory(prefix="exam_project_inspect_") as temp:
        project = ExamProjectPackage.open(Path(args.package), Path(temp))
        print(json.dumps(project.manifest.to_dict(), ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="exam-project", description="考试项目包工具")
    sub = parser.add_subparsers(dest="command", required=True)

    import_parser = sub.add_parser("import-legacy", help="从旧系统资产创建 .examproj")
    import_parser.add_argument("legacy_root")
    import_parser.add_argument("output")
    import_parser.add_argument("--name", required=True)
    import_parser.set_defaults(func=_cmd_import_legacy)

    inspect_parser = sub.add_parser("inspect", help="检查 .examproj 并输出 manifest")
    inspect_parser.add_argument("package")
    inspect_parser.set_defaults(func=_cmd_inspect)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ProjectError as exc:
        parser.exit(2, exc.user_message + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run CLI tests**

Run:

```bash
python -m pytest tests/test_cli.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/exam_project/cli.py tests/test_cli.py
git commit -m "feat: add exam project CLI"
```

## Task 11: README Update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace README with project foundation docs**

Replace `README.md` with:

```markdown
# exam_project

`exam_project` manages single-file `.examproj` exam packages.

An exam project contains:

- answer sheet design
- recognition layout
- reference answers
- blank-sheet calibration
- recognition and grading outputs

The first implementation milestone provides the core package format, manifest validation, checksum validation, and legacy asset import.

## Development

Install in editable mode:

```bash
python -m pip install -e .[dev]
```

Run tests:

```bash
python -m pytest
```

## CLI

Import assets from the old project layout:

```bash
python -m exam_project.cli import-legacy E:\path\to\auto_grading_system demo.examproj --name "期末考试"
```

Inspect a project package:

```bash
python -m exam_project.cli inspect demo.examproj
```
```

- [ ] **Step 2: Run docs-adjacent checks**

Run:

```bash
python -m pytest
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document exam project foundation"
```

## Task 12: Final Verification

**Files:**
- No new files.

- [ ] **Step 1: Run full test suite**

Run:

```bash
python -m pytest -v
```

Expected: all tests PASS.

- [ ] **Step 2: Exercise CLI manually**

Create a tiny legacy fixture in a temporary folder and run:

```bash
python -m exam_project.cli inspect sample.examproj
```

Expected: JSON manifest printed with `schema_version`, `project_id`, `name`, `assets`, `exam`, and `checksums`.

- [ ] **Step 3: Check git status**

Run:

```bash
git status --short
```

Expected: no uncommitted changes.

## Self-Review

Spec coverage in this plan:

- Covered: `.examproj` ZIP container, manifest, checksum, safe extraction, atomic save, backup, project runtime object, validation, legacy import, CLI inspection.
- Deferred to follow-up plans: answer sheet designer migration, blank calibration UI, recognition and grading migration, Streamlit project workflow.

Plan scan:

- 已扫描含混步骤和空泛错误处理描述；计划中的实现步骤都有具体代码或具体命令。

Type consistency:

- `ProjectManifest`, `ExamProject`, `ProjectContext`, `ExamProjectPackage`, `validate_project`, and `import_legacy_project` are defined before later tasks consume them.
