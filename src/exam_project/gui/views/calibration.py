"""空白答卷校准视图（4 步向导：上传 → 确认 → 计算 → 保存）。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import streamlit as st

from exam_project.recognition.blank_calibrator import (
    compute_blank_baseline,
    compute_blank_baseline_multipage,
    load_baseline,
    save_baseline,
)
from exam_project.recognition.layout import LayoutAnalyzer, LayoutConfig, PageRegions
from exam_project.recognition.preprocess import ImagePreprocessor

from .components import load_image_from_bytes, project_paths_for_session


# 区域类型颜色（BGR）—— 用于缩略图标注
_REGION_COLORS_BGR = {
    "student_id": (255, 100, 50),
    "choice": (50, 200, 50),
    "judge": (50, 150, 255),
    "essay": (255, 50, 200),
}
_REGION_LABELS_CN = {
    "student_id": "学号",
    "choice": "选择题",
    "judge": "判断题",
    "essay": "简答题",
    "solution": "解答题",
}
_REGION_LABELS_IMAGE = {
    "student_id": "ID",
    "choice": "Choice",
    "judge": "Judge",
    "essay": "Essay",
    "solution": "Solution",
}


# ============================================================================
# 工具函数
# ============================================================================


def _save_uploaded_file(uploaded_file) -> str:
    """将 UploadedFile 落盘到临时文件，返回路径。"""
    suffix = "." + uploaded_file.name.split(".")[-1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getvalue())
        return tmp.name


def _make_thumbnail(image_bgr: np.ndarray, max_size: int = 300) -> bytes:
    """生成缩略图 PNG bytes。"""
    h, w = image_bgr.shape[:2]
    scale = max_size / max(h, w)
    if scale < 1:
        thumb = cv2.resize(
            image_bgr, (int(w * scale), int(h * scale)),
            interpolation=cv2.INTER_AREA,
        )
    else:
        thumb = image_bgr
    thumb_rgb = cv2.cvtColor(thumb, cv2.COLOR_BGR2RGB)
    _, buf = cv2.imencode(".png", thumb_rgb)
    return buf.tobytes()


def _draw_regions_on_thumbnail(
    thumb_bytes: bytes,
    regions: PageRegions,
    original_shape: tuple,
) -> bytes:
    """在缩略图上绘制检测到的区域边框。"""
    thumb_arr = np.frombuffer(thumb_bytes, dtype=np.uint8)
    thumb_img = cv2.imdecode(thumb_arr, cv2.IMREAD_COLOR)
    if thumb_img is None:
        return thumb_bytes
    thumb_h, thumb_w = thumb_img.shape[:2]
    orig_h, orig_w = original_shape[:2]
    scale_x = thumb_w / orig_w
    scale_y = thumb_h / orig_h
    for sec_type, roi in [
        ("student_id", regions.student_id),
        ("choice", regions.choice),
        ("judge", regions.judge),
        ("essay", regions.essay),
    ]:
        if roi is None:
            continue
        x, y, w, h = roi
        x1, y1 = int(x * scale_x), int(y * scale_y)
        x2, y2 = int((x + w) * scale_x), int((y + h) * scale_y)
        color = _REGION_COLORS_BGR.get(sec_type, (200, 200, 200))
        cv2.rectangle(thumb_img, (x1, y1), (x2, y2), color, 2)
        label = _REGION_LABELS_IMAGE.get(sec_type, sec_type)
        cv2.putText(
            thumb_img, label, (x1, max(y1 - 5, 15)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA,
        )
    _, buf = cv2.imencode(".png", thumb_img)
    return buf.tobytes()


def _image_to_png_bytes(image: np.ndarray, max_size: int = 700) -> bytes:
    """Encode a BGR or grayscale image as display-sized PNG bytes."""
    if image.ndim == 2:
        display = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    else:
        display = image
    return _make_thumbnail(display, max_size=max_size)


def _page_fallback_key(page_idx: int) -> str:
    return f"page{page_idx + 1}_fallback"


def _expected_sections(layout: Optional[dict], page_idx: int) -> list[str]:
    """从 layout 配置推导某页应有的 section 列表。"""
    if not layout:
        return ["choice"] if page_idx == 0 else ["judge"]
    pages = layout.get("_pages")
    if pages and page_idx < len(pages):
        page_spec = pages[page_idx]
        if isinstance(page_spec, dict):
            return [
                sec.get("type") for sec in page_spec.get("sections", [])
                if isinstance(sec, dict) and sec.get("type")
            ]
        return [s for s in page_spec or [] if s]
    fallback = layout.get("layout", {}).get(_page_fallback_key(page_idx), {})
    if isinstance(fallback, dict):
        return [
            sec
            for sec in ("student_id", "choice", "judge", "essay", "solution")
            if sec in fallback
        ]
    return ["choice"] if page_idx == 0 else ["judge"]


def _layout_fallback_regions(
    layout: Optional[dict],
    page_idx: int,
    image_shape: tuple,
    boxes: tuple[tuple[int, int, int, int], ...] = (),
) -> dict[str, tuple[int, int, int, int]]:
    """Convert layout.pageN_fallback y-ranges into full-width pixel rectangles."""
    if not layout:
        return {}
    h, w = image_shape[:2]
    pages = layout.get("_pages")
    if pages and page_idx < len(pages):
        page_spec = pages[page_idx]
    else:
        fallback = layout.get("layout", {}).get(_page_fallback_key(page_idx), {})
        if not isinstance(fallback, dict):
            return {}
        page_spec = {
            "page_number": page_idx + 1,
            "sections": [{"type": sec} for sec in fallback],
        }
    analyzer = LayoutAnalyzer(LayoutConfig.from_dict(layout))
    return analyzer.fallback_regions_from_spec(page_spec, h, w, boxes)


def _regions_to_map(regions: PageRegions) -> dict[str, tuple[int, int, int, int]]:
    result: dict[str, tuple[int, int, int, int]] = {}
    for sec in ("student_id", "choice", "judge", "essay"):
        roi = _get_region(regions, sec)
        if roi is not None:
            result[sec] = roi
    return result


def _draw_region_map_on_image(
    image_bgr: np.ndarray,
    regions: dict[str, tuple[int, int, int, int]],
    *,
    max_size: int = 700,
) -> bytes:
    display = image_bgr.copy()
    font_scale = max(0.8, min(3.0, image_bgr.shape[1] / 1600))
    thickness = max(2, int(font_scale * 2))
    for sec_type, roi in regions.items():
        x, y, w, h = roi
        color = _REGION_COLORS_BGR.get(sec_type, (200, 200, 200))
        cv2.rectangle(display, (x, y), (x + w, y + h), color, thickness)
        label = _REGION_LABELS_IMAGE.get(sec_type, sec_type)
        (text_w, text_h), baseline = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
        )
        label_x = max(x + int(12 * font_scale), int(18 * font_scale))
        if y > text_h + baseline + int(18 * font_scale):
            label_y = y - int(10 * font_scale)
        else:
            label_y = y + text_h + baseline + int(10 * font_scale)
        bg_x0 = max(0, label_x - int(8 * font_scale))
        bg_y0 = max(0, label_y - text_h - baseline - int(6 * font_scale))
        bg_x1 = min(display.shape[1], label_x + text_w + int(8 * font_scale))
        bg_y1 = min(display.shape[0], label_y + baseline + int(6 * font_scale))
        cv2.rectangle(display, (bg_x0, bg_y0), (bg_x1, bg_y1), (255, 255, 255), -1)
        cv2.putText(
            display,
            label,
            (label_x, label_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            color,
            thickness,
            cv2.LINE_AA,
        )
    return _image_to_png_bytes(display, max_size=max_size)


def _crop_region_png(
    image_bgr: np.ndarray,
    roi: tuple[int, int, int, int],
    max_size: int = 420,
) -> bytes:
    x, y, w, h = roi
    crop = image_bgr[y:y + h, x:x + w]
    if crop.size == 0:
        return b""
    return _image_to_png_bytes(crop, max_size=max_size)


def _load_project_layout(project) -> Optional[dict]:
    try:
        return project.load_layout()
    except Exception:
        return None


def _render_page_debug(
    layout: Optional[dict],
    page_idx: int,
    regions: PageRegions,
    original: np.ndarray,
    orientation_viz: np.ndarray,
    corrected: np.ndarray,
    gray: np.ndarray,
    enhanced: np.ndarray,
    binary: np.ndarray,
    correction_deg: float,
    applied_rotation_deg: float,
    residual_deg: float,
    sections: list[str],
) -> None:
    layout_regions = _layout_fallback_regions(
        layout, page_idx, corrected.shape, regions.boxes
    )
    detected_regions = _regions_to_map(regions)

    m1, m2, m3 = st.columns(3)
    m1.metric("检测倾斜", f"{correction_deg:+.2f}°")
    m2.metric("应用旋转", f"{applied_rotation_deg:+.2f}°")
    m3.metric("矫正后残余", f"{residual_deg:+.2f}°")

    with st.expander("1. 方向矫正", expanded=True):
        p1, p2, p3 = st.columns(3)
        p1.image(_image_to_png_bytes(original), caption="原图")
        p2.image(
            _image_to_png_bytes(orientation_viz),
            caption=f"角度检测 {correction_deg:+.1f}°",
        )
        p3.image(
            _image_to_png_bytes(corrected),
            caption=f"方向矫正后，应用旋转 {applied_rotation_deg:+.1f}°",
        )

    with st.expander("2. 图像增强", expanded=False):
        p1, p2, p3 = st.columns(3)
        p1.image(_image_to_png_bytes(gray), caption="去噪灰度")
        p2.image(_image_to_png_bytes(enhanced), caption="对比度增强")
        p3.image(_image_to_png_bytes(binary), caption="二值化")

    with st.expander("3. layout 推断", expanded=False):
        if layout_regions:
            st.image(
                _draw_region_map_on_image(corrected, layout_regions),
                caption="根据 layout.pageN_fallback 推断的区域",
            )
            fallback = (
                layout.get("layout", {}).get(_page_fallback_key(page_idx), {})
                if layout else {}
            )
            st.json({
                sec: {"box": box, "ratio": fallback.get(sec)}
                for sec, box in layout_regions.items()
            })
        else:
            st.warning("当前 layout 未声明本页 fallback 区域。")

    with st.expander("4. 检测结果", expanded=False):
        if detected_regions:
            st.image(
                _draw_region_map_on_image(corrected, detected_regions),
                caption="LayoutAnalyzer 最终检测区域（方向矫正后坐标）",
            )
        else:
            st.warning("LayoutAnalyzer 未检测到有效区域。")
        if regions.boxes:
            st.json({"raw_boxes": list(regions.boxes)})

    with st.expander("5. 区域裁剪", expanded=False):
        crop_cols = st.columns(max(1, min(4, len(sections))))
        for idx, sec in enumerate(sections):
            roi = detected_regions.get(sec) or layout_regions.get(sec)
            with crop_cols[idx % len(crop_cols)]:
                st.caption(_REGION_LABELS_CN.get(sec, sec))
                if roi is None:
                    st.warning("无区域")
                    continue
                crop_png = _crop_region_png(corrected, roi)
                if crop_png:
                    st.image(crop_png)
                st.code(str(roi), language=None)


# ============================================================================
# 步骤渲染
# ============================================================================


def _render_step_1(page_count: int) -> None:
    st.markdown("#### 第 1 步：上传空白答卷")
    st.info(
        "请打印生成的答题卡，**不要填涂任何选项**，"
        "用扫描仪或手机拍照后上传。"
    )

    uploaded: list = []
    for i in range(page_count):
        label = f"第 {i + 1} 页"
        f = st.file_uploader(
            label, type=["png", "jpg", "jpeg"],
            key=f"calib_upload_p{i}",
        )
        uploaded.append(f)

    all_uploaded = all(f is not None for f in uploaded)
    if st.button("下一步", type="primary", disabled=not all_uploaded):
        temp_paths: list[str] = []
        thumbs: list[bytes] = []
        for f in uploaded:
            path = _save_uploaded_file(f)
            temp_paths.append(path)
            img = load_image_from_bytes(f.getvalue())
            thumbs.append(_make_thumbnail(img))
        st.session_state["calib_temp_paths"] = temp_paths
        st.session_state["calib_thumbnails"] = thumbs
        st.session_state["calib_step"] = 2
        st.rerun()


def _render_step_2(layout: Optional[dict], page_count: int) -> None:
    st.markdown("#### 第 2 步：确认检测区域")

    temp_paths: list[str] = st.session_state.get("calib_temp_paths", [])

    preprocessor = ImagePreprocessor()
    images: list[np.ndarray] = []
    binaries: list[np.ndarray] = []
    corrected_images: list[np.ndarray] = []
    grays: list[np.ndarray] = []
    enhanced_images: list[np.ndarray] = []
    orientation_viz_list: list[np.ndarray] = []
    corrections: list[float] = []
    applied_rotations: list[float] = []
    residuals: list[float] = []
    for path in temp_paths:
        img = preprocessor.load(path)
        prepared = preprocessor.resize(img)
        gray_raw = cv2.cvtColor(prepared, cv2.COLOR_BGR2GRAY)
        _, binary_raw = cv2.threshold(
            gray_raw, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        result = preprocessor.process(prepared)
        images.append(prepared)
        binaries.append(result.binary)
        corrected_images.append(result.corrected)
        grays.append(result.gray)
        enhanced_images.append(result.enhanced)
        orientation_viz_list.append(
            ImagePreprocessor.draw_orientation_detection(binary_raw)
        )
        corrections.append(result.correction_deg)
        applied_rotations.append(result.applied_rotation_deg)
        corrected_gray_raw = cv2.cvtColor(result.corrected, cv2.COLOR_BGR2GRAY)
        _, corrected_binary_raw = cv2.threshold(
            corrected_gray_raw, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        residuals.append(ImagePreprocessor.detect_orientation(corrected_binary_raw))

    analyzer = LayoutAnalyzer(LayoutConfig.from_dict(layout or {}))
    pages_config = layout.get("_pages") if layout else None
    if pages_config:
        regions_list = analyzer.analyze_multipage(corrected_images, binaries)
    else:
        regions_list = [
            analyzer.analyze(c, b, page=idx + 1)
            for idx, (c, b) in enumerate(zip(corrected_images, binaries))
        ]

    st.session_state["calib_regions_list"] = regions_list
    st.session_state["calib_corrected_images"] = corrected_images

    total_choice = 0
    total_judge = 0
    for page_idx, (regions, orig_img, corrected_img) in enumerate(
        zip(regions_list, images, corrected_images)
    ):
        with st.container(border=True):
            c1, c2 = st.columns([1, 2])
            with c1:
                annotated = _draw_regions_on_thumbnail(
                    _make_thumbnail(corrected_img), regions, corrected_img.shape,
                )
                st.image(annotated, caption=f"第 {page_idx + 1} 页（方向矫正后检测区域）")
            with c2:
                sections = _expected_sections(layout, page_idx)
                detected: list[str] = []
                for sec in sections:
                    if _get_region(regions, sec) is not None:
                        detected.append(sec)
                        if sec == "choice":
                            total_choice += 1
                        elif sec == "judge":
                            total_judge += 1
                st.markdown(f"**期望**: {', '.join(sections) or '无'}")
                st.markdown(f"**检测到**: {', '.join(detected) or '无'}")
                _render_page_debug(
                    layout,
                    page_idx,
                    regions,
                    orig_img,
                    orientation_viz_list[page_idx],
                    corrected_img,
                    grays[page_idx],
                    enhanced_images[page_idx],
                    binaries[page_idx],
                    corrections[page_idx],
                    applied_rotations[page_idx],
                    residuals[page_idx],
                    sections,
                )

    st.divider()
    c1, c2 = st.columns(2)
    c1.metric("选择题区域", f"{total_choice} 页")
    c2.metric("判断题区域", f"{total_judge} 页")

    c1, c2 = st.columns(2)
    if c1.button("返回"):
        st.session_state["calib_step"] = 1
        st.rerun()
    if c2.button("下一步", type="primary"):
        st.session_state["calib_step"] = 3
        st.rerun()


def _get_region(regions: PageRegions, sec_type: str) -> Optional[tuple]:
    if sec_type == "student_id":
        return regions.student_id
    if sec_type == "choice":
        return regions.choice
    if sec_type == "judge":
        return regions.judge
    if sec_type == "essay":
        return regions.essay
    return None


def _render_step_3(layout: Optional[dict], page_count: int) -> None:
    st.markdown("#### 第 3 步：计算空白基准")
    temp_paths: list[str] = st.session_state.get("calib_temp_paths", [])
    if not temp_paths:
        st.error("未找到上传的图像，请返回第 1 步重新上传。")
        return
    if st.button("开始计算", type="primary"):
        try:
            if page_count == 1 and not (layout and layout.get("_pages")):
                # 单页 + 旧布局：分别算 choice (page=1) 和 judge (page=2)
                result_choice, viz_choice = compute_blank_baseline(temp_paths[0], layout, page=1, viz=True)
                result_judge, viz_judge = compute_blank_baseline(temp_paths[0], layout, page=2, viz=True)
                baseline = {**result_choice, **result_judge}
                viz_pages = viz_choice + viz_judge
            else:
                baseline, viz_pages = compute_blank_baseline_multipage(temp_paths, layout, viz=True)
            st.session_state["calib_baseline"] = baseline
            st.session_state["calib_viz"] = viz_pages
            st.success(f"已计算 {len(baseline)} 个 section 的基准。")
        except Exception as exc:
            st.error(f"计算失败: {exc}")

    # 展示可视化结果
    viz_pages = st.session_state.get("calib_viz")
    if viz_pages:
        st.markdown("---")
        st.markdown("**📊 计算过程可视化**")
        for page_viz in viz_pages:
            st.markdown(f"**第 {page_viz['page_idx'] + 1} 页**")
            for sec_type, sec_viz in page_viz["sections"].items():
                st.markdown(f"*{sec_type} 区域*")
                cols = st.columns(3)
                with cols[0]:
                    st.image(sec_viz["roi_image"], caption="ROI + 填涂起始线（红）")
                with cols[1]:
                    st.image(sec_viz["grid_image"], caption="网格分割")
                with cols[2]:
                    if sec_viz["sample_cell_image"]:
                        st.image(sec_viz["sample_cell_image"], caption="气泡位置检测")
                    else:
                        st.caption("无气泡位置数据")
                # 统计摘要
                stats = sec_viz["stats_summary"]
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("题目数", stats["question_count"])
                m2.metric("灰度均值", f"{stats['mean_avg']:.1f}")
                m3.metric("灰度范围", f"{stats['mean_min']:.1f} ~ {stats['mean_max']:.1f}")
                m4.metric("标准差均值", f"{stats['std_avg']:.1f}")
                st.divider()


def _render_step_4(project_workdir: Path) -> None:
    st.markdown("#### 第 4 步：保存到项目")
    baseline = st.session_state.get("calib_baseline")
    if not baseline:
        st.warning("尚未计算基准，请先完成第 3 步。")
        return
    paths = project_paths_for_session(project_workdir)
    baseline_path = Path(paths["api_keys"]).parent / "blank_baseline.json"

    if st.button("保存到当前项目", type="primary"):
        try:
            save_baseline(baseline, baseline_path)
            st.success(f"已保存到 {baseline_path}")
        except Exception as exc:
            st.error(f"保存失败: {exc}")


# ============================================================================
# 公开入口
# ============================================================================


def render_calibration_view(
    project,
    legacy_root: Optional[Path] = None,
) -> None:
    """校准视图主入口。

    Args:
        project: 当前打开的 ExamProject
        legacy_root: 保留参数以兼容旧 call site；exam_project 自有实现不需要
    """
    # layout 从项目资产读取；manifest 只声明路径，不保存 layout 内容。
    layout = _load_project_layout(project)

    if "calib_step" not in st.session_state:
        st.session_state["calib_step"] = 1

    page_count = 2
    if layout and layout.get("_pages"):
        page_count = len(layout["_pages"])
    elif layout and isinstance(layout.get("layout"), dict):
        fallback_pages = [
            key for key in layout["layout"]
            if key.startswith("page") and key.endswith("_fallback")
        ]
        if fallback_pages:
            page_count = len(fallback_pages)

    step = st.session_state["calib_step"]
    if step == 1:
        _render_step_1(page_count)
    elif step == 2:
        _render_step_2(layout, page_count)
    elif step == 3:
        _render_step_3(layout, page_count)
    elif step == 4:
        _render_step_4(project.workdir)
    else:
        st.session_state["calib_step"] = 1
        st.rerun()
