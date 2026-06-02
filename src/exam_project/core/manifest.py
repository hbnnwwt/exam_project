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
        raise ProjectValidationError(
            f"项目资产路径不能使用反斜杠: {path}", code="invalid_asset_path"
        )
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
        for key in (
            "schema_version",
            "project_id",
            "name",
            "created_at",
            "updated_at",
            "assets",
            "exam",
            "checksums",
        ):
            if key not in data:
                raise ProjectValidationError(
                    f"project.json 缺少字段: {key}", code="manifest_missing_field"
                )
        raw_assets = dict(data["assets"])
        for asset_key in REQUIRED_ASSETS:
            if asset_key not in raw_assets:
                raise ProjectValidationError(
                    f"project.json 缺少资产声明: {asset_key}",
                    code="manifest_missing_asset",
                )
        assets = {
            asset_key: validate_asset_path(path)
            for asset_key, path in raw_assets.items()
        }
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
