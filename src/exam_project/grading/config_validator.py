"""启动时校验配置文件完整性。

缺字段给默认值 + 警告，缺文件给明确提示。
避免配置问题在深层模块报 cryptic 错误。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .defaults import model_config_defaults


# sheet_layout.json 必须包含的字段（choice/judge 可选，layout/scoring 必须）
REQUIRED_LAYOUT_KEYS = frozenset({"layout", "scoring"})


def validate_layout(path: str | Path) -> tuple[Optional[dict], list[str]]:
    """校验 sheet_layout.json。返回 (config_dict, warnings)。

    文件不存在时返回 (None, [警告])。
    缺字段时返回配置内容 + 警告列表。
    """
    path = Path(path)
    warnings: list[str] = []
    if not path.is_file():
        return None, [f"配置文件不存在: {path}"]

    cfg = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        return None, [f"配置文件根节点不是 dict: {path}"]

    missing = REQUIRED_LAYOUT_KEYS - set(cfg.keys())
    if missing:
        warnings.append(f"sheet_layout.json 缺少字段: {missing}")
    return cfg, warnings


def validate_model_config(path: str | Path) -> tuple[dict, list[str]]:
    """校验 model_config.json，补全缺省字段。

    文件不存在时返回 (defaults, [警告])。
    缺字段时补全并告警。
    """
    path = Path(path)
    warnings: list[str] = []
    if not path.is_file():
        defaults = model_config_defaults()
        return defaults, [f"模型配置不存在，使用默认值: {path}"]

    cfg = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        cfg = {}

    for key, default in model_config_defaults().items():
        if key not in cfg:
            cfg[key] = default
            warnings.append(f"model_config.json 缺 '{key}'，使用默认值: {default}")
    return cfg, warnings


def validate_all(base_dir: str | Path) -> list[str]:
    """校验 base_dir 下所有配置。返回 warnings 列表。"""
    base = Path(base_dir)
    all_warnings: list[str] = []

    layout_path = base / "config" / "sheet_layout.json"
    _, w = validate_layout(layout_path)
    all_warnings.extend(w)

    model_path = base / "config" / "model_config.json"
    _, w = validate_model_config(model_path)
    all_warnings.extend(w)

    api_path = base / "config" / "api_keys.json"
    if not api_path.is_file():
        all_warnings.append("api_keys.json 不存在（离线模式可忽略）")

    return all_warnings
