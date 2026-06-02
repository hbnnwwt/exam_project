import json
from types import MappingProxyType

import pytest

from exam_project.core.errors import ProjectValidationError
from exam_project.core.manifest import ProjectManifest, validate_asset_path


def _manifest_dict():
    return {
        "schema_version": 1,
        "project_id": "project-1",
        "name": "期末考试",
        "created_at": "2026-06-02T20:00:00+08:00",
        "updated_at": "2026-06-02T20:30:00+08:00",
        "assets": {
            "design": "design/answer_sheet.json",
            "layout": "config/sheet_layout.json",
            "baseline": "config/blank_baseline.json",
            "answers": "answers/reference_answers.xlsx",
        },
        "exam": {"student_id_digits": 10, "question_types": ["choice", "judge"]},
        "checksums": {"config/sheet_layout.json": "sha256:" + "1" * 64},
    }


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


def test_from_json_rejects_invalid_json():
    with pytest.raises(ProjectValidationError) as exc_info:
        ProjectManifest.from_json("{")

    assert exc_info.value.code == "manifest_invalid_json"


@pytest.mark.parametrize("text", [None, b"\xff"])
def test_from_json_rejects_invalid_input_types(text):
    with pytest.raises(ProjectValidationError) as exc_info:
        ProjectManifest.from_json(text)

    assert exc_info.value.code == "manifest_invalid_json"


@pytest.mark.parametrize(
    "path",
    [
        "../evil.txt",
        "/absolute/path.txt",
        "C:/absolute/path.txt",
        "config/../evil.txt",
        ".",
        "./x.txt",
        "config/./x.json",
        "config//x.json",
        "config/ /x.json",
        "config/\t/x.json",
        "config/",
        " config/x.json",
        "config/x.json ",
        r"config\x.json",
        "",
    ],
)
def test_rejects_unsafe_asset_paths(path):
    with pytest.raises(ProjectValidationError) as exc_info:
        validate_asset_path(path)

    assert exc_info.value.code == "invalid_asset_path"


def test_accepts_relative_asset_path():
    assert validate_asset_path("config/sheet_layout.json") == "config/sheet_layout.json"


@pytest.mark.parametrize(
    ("asset_key", "value"),
    [
        ("design", ""),
        ("layout", None),
        ("answers", 0),
    ],
)
def test_from_dict_rejects_invalid_asset_values(asset_key, value):
    data = _manifest_dict()
    data["assets"][asset_key] = value

    with pytest.raises(ProjectValidationError):
        ProjectManifest.from_dict(data)


@pytest.mark.parametrize("field", ["assets", "exam", "checksums"])
def test_from_dict_rejects_non_mapping_sections(field):
    data = _manifest_dict()
    data[field] = []

    with pytest.raises(ProjectValidationError) as exc_info:
        ProjectManifest.from_dict(data)

    assert exc_info.value.code == "manifest_invalid_type"


@pytest.mark.parametrize("data", [None, [], "not-a-dict"])
def test_from_dict_rejects_non_mapping_manifest(data):
    with pytest.raises(ProjectValidationError) as exc_info:
        ProjectManifest.from_dict(data)

    assert exc_info.value.code == "manifest_invalid_type"


@pytest.mark.parametrize(
    "value",
    [object(), {1, 2}, b"x", ("choice",), float("nan")],
)
def test_from_dict_rejects_unknown_non_json_values(value):
    data = _manifest_dict()
    data["extra"] = value

    with pytest.raises(ProjectValidationError) as exc_info:
        ProjectManifest.from_dict(data)

    assert exc_info.value.code == "manifest_invalid_type"


def test_from_dict_rejects_non_string_top_level_keys():
    data = _manifest_dict()
    data[1] = "bad"

    with pytest.raises(ProjectValidationError) as exc_info:
        ProjectManifest.from_dict(data)

    assert exc_info.value.code == "manifest_invalid_type"


@pytest.mark.parametrize("field", ["assets", "exam", "checksums"])
def test_from_dict_rejects_mapping_subclasses(field):
    data = _manifest_dict()
    data[field] = MappingProxyType(data[field])

    with pytest.raises(ProjectValidationError) as exc_info:
        ProjectManifest.from_dict(data)

    assert exc_info.value.code == "manifest_invalid_type"


def test_from_dict_rejects_bad_schema_version():
    data = _manifest_dict()
    data["schema_version"] = "not-int"

    with pytest.raises(ProjectValidationError) as exc_info:
        ProjectManifest.from_dict(data)

    assert exc_info.value.code == "manifest_invalid_field"


@pytest.mark.parametrize("schema_version", [0, 2, 1.9, True])
def test_from_dict_rejects_unsupported_schema_version(schema_version):
    data = _manifest_dict()
    data["schema_version"] = schema_version

    with pytest.raises(ProjectValidationError):
        ProjectManifest.from_dict(data)


@pytest.mark.parametrize("schema_version", [0, 2, 1.9, True])
def test_constructor_rejects_unsupported_schema_version(schema_version):
    with pytest.raises(ProjectValidationError):
        ProjectManifest(
            schema_version=schema_version,
            project_id="project-1",
            name="期末考试",
            created_at="2026-06-02T20:00:00+08:00",
            updated_at="2026-06-02T20:30:00+08:00",
            assets={
                "design": "design/answer_sheet.json",
                "layout": "config/sheet_layout.json",
                "answers": "answers/reference_answers.xlsx",
            },
            exam={"student_id_digits": 10, "question_types": ["choice", "judge"]},
            checksums={},
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("project_id", object()),
        ("name", {"x"}),
        ("created_at", 1),
        ("updated_at", ""),
    ],
)
def test_from_dict_rejects_invalid_scalar_identity_fields(field, value):
    data = _manifest_dict()
    data[field] = value

    with pytest.raises(ProjectValidationError):
        ProjectManifest.from_dict(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("project_id", object()),
        ("name", {"x"}),
        ("created_at", 1),
        ("updated_at", ""),
    ],
)
def test_constructor_rejects_invalid_scalar_identity_fields(field, value):
    kwargs = _manifest_dict()
    kwargs[field] = value

    with pytest.raises(ProjectValidationError):
        ProjectManifest(**kwargs)


def test_from_dict_rejects_non_string_asset_keys():
    data = _manifest_dict()
    data["assets"] = {
        123: "x",
        "design": "design/answer_sheet.json",
        "layout": "config/sheet_layout.json",
        "answers": "answers/reference_answers.xlsx",
    }

    with pytest.raises(ProjectValidationError) as exc_info:
        ProjectManifest.from_dict(data)

    assert exc_info.value.code == "manifest_invalid_type"


def test_constructor_rejects_non_string_asset_keys():
    data = _manifest_dict()
    data["assets"] = {
        123: "x",
        "design": "design/answer_sheet.json",
        "layout": "config/sheet_layout.json",
        "answers": "answers/reference_answers.xlsx",
    }

    with pytest.raises(ProjectValidationError) as exc_info:
        ProjectManifest(**data)

    assert exc_info.value.code == "manifest_invalid_type"


def test_constructor_rejects_invalid_asset_paths():
    with pytest.raises(ProjectValidationError):
        ProjectManifest(
            schema_version=1,
            project_id="project-1",
            name="期末考试",
            created_at="2026-06-02T20:00:00+08:00",
            updated_at="2026-06-02T20:30:00+08:00",
            assets={
                "design": "../evil",
                "layout": "config/sheet_layout.json",
                "answers": "answers/reference_answers.xlsx",
            },
            exam={"student_id_digits": 10, "question_types": ["choice", "judge"]},
            checksums={},
        )


def test_constructor_rejects_invalid_checksum_paths():
    with pytest.raises(ProjectValidationError):
        ProjectManifest(
            schema_version=1,
            project_id="project-1",
            name="期末考试",
            created_at="2026-06-02T20:00:00+08:00",
            updated_at="2026-06-02T20:30:00+08:00",
            assets={
                "design": "design/answer_sheet.json",
                "layout": "config/sheet_layout.json",
                "answers": "answers/reference_answers.xlsx",
            },
            exam={"student_id_digits": 10, "question_types": ["choice", "judge"]},
            checksums={"../evil": "sha256:x"},
        )


def test_constructor_rejects_non_json_exam_values():
    with pytest.raises(ProjectValidationError) as exc_info:
        ProjectManifest(
            schema_version=1,
            project_id="project-1",
            name="期末考试",
            created_at="2026-06-02T20:00:00+08:00",
            updated_at="2026-06-02T20:30:00+08:00",
            assets={
                "design": "design/answer_sheet.json",
                "layout": "config/sheet_layout.json",
                "answers": "answers/reference_answers.xlsx",
            },
            exam={"bad": {1, 2}},
            checksums={},
        )

    assert exc_info.value.code == "manifest_invalid_type"


def test_constructor_rejects_mapping_subclass_exam_values():
    data = _manifest_dict()
    data["exam"] = MappingProxyType({"student_id_digits": 10})

    with pytest.raises(ProjectValidationError) as exc_info:
        ProjectManifest(**data)

    assert exc_info.value.code == "manifest_invalid_type"


def test_from_dict_rejects_non_json_exam_values():
    data = _manifest_dict()
    data["exam"] = {"bad": {1, 2}}

    with pytest.raises(ProjectValidationError) as exc_info:
        ProjectManifest.from_dict(data)

    assert exc_info.value.code == "manifest_invalid_type"


def test_constructor_rejects_tuple_exam_values():
    data = _manifest_dict()
    data["exam"] = {"bad": ("choice", "judge")}

    with pytest.raises(ProjectValidationError) as exc_info:
        ProjectManifest(**data)

    assert exc_info.value.code == "manifest_invalid_type"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_constructor_rejects_non_finite_exam_floats(value):
    data = _manifest_dict()
    data["exam"] = {"bad": value}

    with pytest.raises(ProjectValidationError) as exc_info:
        ProjectManifest(**data)

    assert exc_info.value.code == "manifest_invalid_type"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_from_dict_rejects_non_finite_exam_floats(value):
    data = _manifest_dict()
    data["exam"] = {"bad": value}

    with pytest.raises(ProjectValidationError) as exc_info:
        ProjectManifest.from_dict(data)

    assert exc_info.value.code == "manifest_invalid_type"


def test_constructor_rejects_non_json_checksum_values():
    with pytest.raises(ProjectValidationError) as exc_info:
        ProjectManifest(
            schema_version=1,
            project_id="project-1",
            name="期末考试",
            created_at="2026-06-02T20:00:00+08:00",
            updated_at="2026-06-02T20:30:00+08:00",
            assets={
                "design": "design/answer_sheet.json",
                "layout": "config/sheet_layout.json",
                "answers": "answers/reference_answers.xlsx",
            },
            exam={"student_id_digits": 10, "question_types": ["choice", "judge"]},
            checksums={"config/sheet_layout.json": object()},
        )

    assert exc_info.value.code == "manifest_invalid_type"


@pytest.mark.parametrize(
    "value",
    [123, True, ["sha256:x"], {"alg": "sha256"}, None],
)
def test_constructor_rejects_non_string_checksum_values(value):
    data = _manifest_dict()
    data["checksums"] = {"config/sheet_layout.json": value}

    with pytest.raises(ProjectValidationError) as exc_info:
        ProjectManifest(**data)

    assert exc_info.value.code == "manifest_invalid_type"


@pytest.mark.parametrize(
    "value",
    [123, True, ["sha256:x"], {"alg": "sha256"}, None],
)
def test_from_dict_rejects_non_string_checksum_values(value):
    data = _manifest_dict()
    data["checksums"] = {"config/sheet_layout.json": value}

    with pytest.raises(ProjectValidationError) as exc_info:
        ProjectManifest.from_dict(data)

    assert exc_info.value.code == "manifest_invalid_type"


def test_manifest_mappings_are_immutable():
    manifest = ProjectManifest.from_dict(_manifest_dict())

    with pytest.raises(TypeError):
        manifest.assets["layout"] = "config/other.json"


def test_manifest_nested_exam_values_are_immutable():
    manifest = ProjectManifest.from_dict(_manifest_dict())

    assert manifest.exam["question_types"] == ("choice", "judge")
    with pytest.raises(AttributeError):
        manifest.exam["question_types"].append("essay")


def test_from_dict_copies_manifest_mappings():
    data = _manifest_dict()
    manifest = ProjectManifest.from_dict(data)
    data["assets"]["layout"] = "config/other.json"

    assert manifest.assets["layout"] == "config/sheet_layout.json"


def test_from_dict_copies_nested_exam_values():
    data = _manifest_dict()
    manifest = ProjectManifest.from_dict(data)
    data["exam"]["question_types"].append("essay")

    assert manifest.exam["question_types"] == ("choice", "judge")


def test_to_dict_returns_deep_copy_of_exam():
    manifest = ProjectManifest.from_dict(_manifest_dict())
    data = manifest.to_dict()
    data["exam"]["question_types"].append("essay")

    assert manifest.exam["question_types"] == ("choice", "judge")


def test_to_dict_output_is_json_serializable():
    manifest = ProjectManifest.from_dict(_manifest_dict())

    json.dumps(manifest.to_dict(), ensure_ascii=False, allow_nan=False)
