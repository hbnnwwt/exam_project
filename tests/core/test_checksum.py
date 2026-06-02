from pathlib import Path

import pytest

from exam_project.core.checksum import build_checksums, checksum_file
from exam_project.core.errors import ProjectValidationError


def test_checksum_file_uses_sha256(tmp_path: Path):
    path = tmp_path / "sample.txt"
    path.write_text("abc", encoding="utf-8")

    assert (
        checksum_file(path)
        == "sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_build_checksums_uses_posix_paths(tmp_path: Path):
    root = tmp_path / "project"
    (root / "config").mkdir(parents=True)
    (root / "config" / "sheet_layout.json").write_text("{}", encoding="utf-8")

    result = build_checksums(root, ["config/sheet_layout.json"])

    assert set(result) == {"config/sheet_layout.json"}
    assert result["config/sheet_layout.json"].startswith("sha256:")


def test_build_checksums_skips_missing_paths_and_directories(tmp_path: Path):
    root = tmp_path / "project"
    (root / "config").mkdir(parents=True)

    result = build_checksums(root, ["config", "config/missing.json"])

    assert result == {}


def test_build_checksums_rejects_unsafe_paths(tmp_path: Path):
    with pytest.raises(ProjectValidationError) as exc_info:
        build_checksums(tmp_path, ["../evil.txt"])

    assert exc_info.value.code == "invalid_asset_path"
