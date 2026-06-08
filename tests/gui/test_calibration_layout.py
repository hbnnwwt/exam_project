from pathlib import Path

from exam_project.gui.views.calibration import (
    _REGION_LABELS_IMAGE,
    _expected_sections,
    _layout_fallback_regions,
    _load_project_layout,
)


LAYOUT = {
    "layout": {
        "page1_fallback": {
            "student_id": [0.0233, 0.514],
            "choice": [0.5372, 0.8284],
        },
        "page2_fallback": {
            "judge": [0.0, 0.1613],
            "essay": [0.183, 0.927],
        },
    }
}


LAYOUT_WITH_PAGES = {
    "layout": {
        "page1_fallback": {"choice": [0.10, 0.20]},
        "page2_fallback": {"choice": [0.70, 0.90]},
    },
    "_pages": [
        {"page_number": 1, "sections": [{"type": "choice"}]},
        {"page_number": 2, "sections": [{"type": "choice"}]},
    ],
}


def test_expected_sections_from_fallback_layout_without_pages() -> None:
    assert _expected_sections(LAYOUT, 0) == ["student_id", "choice"]
    assert _expected_sections(LAYOUT, 1) == ["judge", "essay"]


def test_layout_fallback_regions_use_full_width_and_y_ratios() -> None:
    page1 = _layout_fallback_regions(LAYOUT, 0, (1000, 800, 3))
    page2 = _layout_fallback_regions(LAYOUT, 1, (1000, 800, 3))

    assert page1["student_id"] == (0, 150, 800, 361)
    assert page1["choice"] == (0, 522, 800, 216)
    assert page2["judge"] == (0, 108, 800, 130)
    assert page2["essay"] == (0, 249, 800, 582)


def test_layout_fallback_regions_can_calibrate_from_detected_essay() -> None:
    regions = _layout_fallback_regions(
        LAYOUT,
        1,
        (6736, 4764, 3),
        ((171, 1869, 4319, 3829),),
    )

    assert regions["judge"] == (0, 897, 4764, 875)
    assert regions["essay"] == (0, 1838, 4764, 3874)


def test_layout_fallback_regions_include_current_page2_judge_frame() -> None:
    regions = _layout_fallback_regions(
        LAYOUT,
        1,
        (6736, 4764, 3),
        ((183, 1880, 4301, 3810),),
    )

    assert regions["judge"] == (0, 912, 4764, 870)
    assert regions["judge"][1] < 927


def test_layout_fallback_regions_with_pages_use_current_page_ratios() -> None:
    page1 = _layout_fallback_regions(LAYOUT_WITH_PAGES, 0, (1000, 800, 3))
    page2 = _layout_fallback_regions(LAYOUT_WITH_PAGES, 1, (1000, 800, 3))

    assert page1["choice"][1] < 300
    assert page2["choice"][1] > 600


def test_image_overlay_labels_are_ascii() -> None:
    for label in _REGION_LABELS_IMAGE.values():
        label.encode("ascii")


def test_load_project_layout_reads_project_asset() -> None:
    class Project:
        layout_path = Path("unused")

        def load_layout(self) -> dict:
            return LAYOUT

    assert _load_project_layout(Project()) == LAYOUT
