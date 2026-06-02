from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any

from exam_project.core.errors import ProjectValidationError


REQUIRED_ASSETS = ("design", "layout", "answers")
REQUIRED_FIELDS = (
    "schema_version",
    "project_id",
    "name",
    "created_at",
    "updated_at",
    "assets",
    "exam",
    "checksums",
)


def validate_asset_path(path: str) -> str:
    if not isinstance(path, str) or not path.strip():
        raise ProjectValidationError("项目资产路径不能为空", code="invalid_asset_path")
    if path != path.strip():
        raise ProjectValidationError(f"项目资产路径不规范: {path}", code="invalid_asset_path")
    if "\\" in path:
        raise ProjectValidationError(
            f"项目资产路径不能使用反斜杠: {path}", code="invalid_asset_path"
        )
    if path.endswith("/"):
        raise ProjectValidationError(f"项目资产路径不能是目录: {path}", code="invalid_asset_path")
    pure = PurePosixPath(path)
    parts = pure.parts
    normalized = pure.as_posix()
    if normalized == "." or normalized != path:
        raise ProjectValidationError(f"项目资产路径不规范: {path}", code="invalid_asset_path")
    if pure.is_absolute() or ".." in parts or ":" in path:
        raise ProjectValidationError(f"项目资产路径不安全: {path}", code="invalid_asset_path")
    return path


def _require_mapping(value: Any, field: str) -> Mapping[Any, Any]:
    if not isinstance(value, Mapping):
        raise ProjectValidationError(
            f"project.json 字段类型错误: {field}", code="manifest_invalid_type"
        )
    return value


def _coerce_int_field(data: Mapping[str, Any], field: str) -> int:
    try:
        return int(data[field])
    except (TypeError, ValueError) as exc:
        raise ProjectValidationError(
            f"project.json 字段无效: {field}", code="manifest_invalid_field"
        ) from exc


def _coerce_str_field(data: Mapping[str, Any], field: str) -> str:
    try:
        return str(data[field])
    except Exception as exc:
        raise ProjectValidationError(
            f"project.json 字段无效: {field}", code="manifest_invalid_field"
        ) from exc


@dataclass(frozen=True)
class ProjectManifest:
    schema_version: int
    project_id: str
    name: str
    created_at: str
    updated_at: str
    assets: Mapping[str, str]
    exam: Mapping[str, Any]
    checksums: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "assets", MappingProxyType(dict(self.assets)))
        object.__setattr__(self, "exam", MappingProxyType(dict(self.exam)))
        object.__setattr__(self, "checksums", MappingProxyType(dict(self.checksums)))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProjectManifest":
        data = _require_mapping(data, "project")
        for key in REQUIRED_FIELDS:
            if key not in data:
                raise ProjectValidationError(
                    f"project.json 缺少字段: {key}", code="manifest_missing_field"
                )
        raw_assets = _require_mapping(data["assets"], "assets")
        raw_exam = _require_mapping(data["exam"], "exam")
        raw_checksums = _require_mapping(data["checksums"], "checksums")
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
        checksums = {
            validate_asset_path(path): checksum
            for path, checksum in raw_checksums.items()
        }
        return cls(
            schema_version=_coerce_int_field(data, "schema_version"),
            project_id=_coerce_str_field(data, "project_id"),
            name=_coerce_str_field(data, "name"),
            created_at=_coerce_str_field(data, "created_at"),
            updated_at=_coerce_str_field(data, "updated_at"),
            assets=assets,
            exam=dict(raw_exam),
            checksums=checksums,
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
