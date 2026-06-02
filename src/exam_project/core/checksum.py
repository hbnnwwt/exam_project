from __future__ import annotations

import hashlib
from pathlib import Path

from exam_project.core.manifest import validate_asset_path


def checksum_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
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
