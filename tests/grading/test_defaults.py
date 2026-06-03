"""defaults + config_validator 测试。"""

from __future__ import annotations

import json
from pathlib import Path

from exam_project.grading.config_validator import (
    REQUIRED_LAYOUT_KEYS,
    validate_all,
    validate_layout,
    validate_model_config,
)
from exam_project.grading.defaults import (
    DEFAULT_BASE_URL,
    DEFAULT_LLM_MODEL,
    DEFAULT_OCR_MODEL,
    model_config_defaults,
)


# ---------------------------------------------------------------------------
# defaults
# ---------------------------------------------------------------------------


def test_model_config_defaults_has_required_keys() -> None:
    cfg = model_config_defaults()
    for key in ("base_url", "llm_model", "ocr_model", "llm_max_tokens", "llm_temperature"):
        assert key in cfg


def test_model_config_defaults_returns_independent_dict() -> None:
    cfg1 = model_config_defaults()
    cfg1["base_url"] = "modified"
    cfg2 = model_config_defaults()
    assert cfg2["base_url"] == DEFAULT_BASE_URL  # 不受污染


def test_default_base_url_is_https() -> None:
    assert DEFAULT_BASE_URL.startswith("https://")
    assert DEFAULT_LLM_MODEL
    assert DEFAULT_OCR_MODEL


# ---------------------------------------------------------------------------
# validate_layout
# ---------------------------------------------------------------------------


def test_validate_layout_missing_file(tmp_path: Path) -> None:
    cfg, warnings = validate_layout(tmp_path / "missing.json")
    assert cfg is None
    assert len(warnings) == 1
    assert "不存在" in warnings[0]


def test_validate_layout_valid(tmp_path: Path) -> None:
    path = tmp_path / "layout.json"
    path.write_text(json.dumps({
        "layout": {"page1_fallback": {}, "page2_fallback": {}},
        "scoring": {},
    }), encoding="utf-8")
    cfg, warnings = validate_layout(path)
    assert cfg is not None
    assert warnings == []


def test_validate_layout_missing_required_keys(tmp_path: Path) -> None:
    path = tmp_path / "layout.json"
    path.write_text(json.dumps({"layout": {}}), encoding="utf-8")
    cfg, warnings = validate_layout(path)
    assert cfg is not None
    assert any("scoring" in w for w in warnings)


def test_validate_layout_invalid_json_raises(tmp_path: Path) -> None:
    """JSON 解析错误应当传播（与 legacy 一致）。"""
    import json
    import pytest
    path = tmp_path / "bad.json"
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        validate_layout(path)


def test_validate_layout_non_dict_root(tmp_path: Path) -> None:
    path = tmp_path / "list.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    cfg, warnings = validate_layout(path)
    assert cfg is None
    assert any("不是 dict" in w for w in warnings)


def test_required_layout_keys_is_frozenset() -> None:
    assert isinstance(REQUIRED_LAYOUT_KEYS, frozenset)
    assert "layout" in REQUIRED_LAYOUT_KEYS
    assert "scoring" in REQUIRED_LAYOUT_KEYS


# ---------------------------------------------------------------------------
# validate_model_config
# ---------------------------------------------------------------------------


def test_validate_model_config_missing_file_returns_defaults(tmp_path: Path) -> None:
    cfg, warnings = validate_model_config(tmp_path / "missing.json")
    assert cfg == model_config_defaults()
    assert len(warnings) == 1


def test_validate_model_config_completes_missing_fields(tmp_path: Path) -> None:
    path = tmp_path / "model.json"
    path.write_text(json.dumps({"base_url": "http://custom"}), encoding="utf-8")
    cfg, warnings = validate_model_config(path)
    # base_url 保持用户值
    assert cfg["base_url"] == "http://custom"
    # 其他字段被补全
    assert cfg["llm_model"] == DEFAULT_LLM_MODEL
    # 每个补全字段产生一条警告
    assert len(warnings) == len(model_config_defaults()) - 1


def test_validate_model_config_non_dict_root(tmp_path: Path) -> None:
    path = tmp_path / "list.json"
    path.write_text(json.dumps("string"), encoding="utf-8")
    cfg, warnings = validate_model_config(path)
    # 非 dict 视为空 dict，全字段补全
    assert cfg == model_config_defaults()
    assert len(warnings) == len(model_config_defaults())


# ---------------------------------------------------------------------------
# validate_all
# ---------------------------------------------------------------------------


def test_validate_all_missing_files(tmp_path: Path) -> None:
    warnings = validate_all(tmp_path)
    # layout 缺失 + model 缺失 + api_keys 缺失
    assert any("sheet_layout" in w for w in warnings)
    assert any("模型配置" in w for w in warnings)
    assert any("api_keys" in w for w in warnings)


def test_validate_all_with_valid_files(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "sheet_layout.json").write_text(
        json.dumps({"layout": {}, "scoring": {}}), encoding="utf-8",
    )
    (tmp_path / "config" / "model_config.json").write_text(
        json.dumps({k: v for k, v in model_config_defaults().items()}), encoding="utf-8",
    )
    (tmp_path / "config" / "api_keys.json").write_text("{}", encoding="utf-8")
    warnings = validate_all(tmp_path)
    assert warnings == []
