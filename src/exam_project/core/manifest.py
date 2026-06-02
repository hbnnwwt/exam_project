from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import math
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


def _validate_schema_version(value: Any) -> int:
    if type(value) is not int or value != 1:
        raise ProjectValidationError(
            "project.json schema_version 无效", code="manifest_invalid_field"
        )
    return value


def _validate_text_field(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectValidationError(
            f"project.json 字段无效: {field}", code="manifest_invalid_field"
        )
    return value


def _validate_asset_key(value: Any) -> str:
    if not isinstance(value, str):
        raise ProjectValidationError(
            "project.json 资产键类型错误", code="manifest_invalid_type"
        )
    if not value.strip():
        raise ProjectValidationError(
            "project.json 资产键无效", code="manifest_invalid_field"
        )
    return value


def _validate_json_value(value: Any, field: str) -> Any:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProjectValidationError(
                f"project.json 字段类型错误: {field}", code="manifest_invalid_type"
            )
        return value
    if value is None or isinstance(value, str | int | bool):
        return value
    if isinstance(value, Mapping):
        validated = {}
        for key, nested_value in value.items():
            if not isinstance(key, str):
                raise ProjectValidationError(
                    f"project.json 字段类型错误: {field}", code="manifest_invalid_type"
                )
            validated[key] = _validate_json_value(nested_value, f"{field}.{key}")
        return validated
    if isinstance(value, list | tuple):
        return [_validate_json_value(item, field) for item in value]
    raise ProjectValidationError(
        f"project.json 字段类型错误: {field}", code="manifest_invalid_type"
    )


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze(nested_value) for key, nested_value in value.items()}
        )
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(nested_value) for key, nested_value in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


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
        raw_assets = _require_mapping(self.assets, "assets")
        raw_exam = _require_mapping(self.exam, "exam")
        raw_checksums = _require_mapping(self.checksums, "checksums")
        for asset_key in REQUIRED_ASSETS:
            if asset_key not in raw_assets:
                raise ProjectValidationError(
                    f"project.json 缺少资产声明: {asset_key}",
                    code="manifest_missing_asset",
                )
        assets = {
            _validate_asset_key(asset_key): validate_asset_path(path)
            for asset_key, path in raw_assets.items()
        }
        checksums = {}
        for path, checksum in raw_checksums.items():
            checksums[validate_asset_path(path)] = _validate_json_value(
                checksum, f"checksums.{path}"
            )
        object.__setattr__(
            self, "schema_version", _validate_schema_version(self.schema_version)
        )
        object.__setattr__(
            self, "project_id", _validate_text_field(self.project_id, "project_id")
        )
        object.__setattr__(self, "name", _validate_text_field(self.name, "name"))
        object.__setattr__(
            self, "created_at", _validate_text_field(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "updated_at", _validate_text_field(self.updated_at, "updated_at")
        )
        object.__setattr__(self, "assets", _freeze(assets))
        object.__setattr__(self, "exam", _freeze(_validate_json_value(raw_exam, "exam")))
        object.__setattr__(self, "checksums", _freeze(checksums))

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
        return cls(
            schema_version=data["schema_version"],
            project_id=data["project_id"],
            name=data["name"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            assets=dict(raw_assets),
            exam=dict(raw_exam),
            checksums=dict(raw_checksums),
        )

    @classmethod
    def from_json(cls, text: str) -> "ProjectManifest":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProjectValidationError(
                "project.json 不是合法 JSON", code="manifest_invalid_json"
            ) from exc
        return cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "assets": _thaw(self.assets),
            "exam": _thaw(self.exam),
            "checksums": _thaw(self.checksums),
        }

    def to_json(self) -> str:
        try:
            return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        except TypeError as exc:
            raise ProjectValidationError(
                "project.json 包含非 JSON 值", code="manifest_invalid_type"
            ) from exc
