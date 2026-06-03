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
from exam_project.recognition.layout import PageRegions
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
        label = _REGION_LABELS_CN.get(sec_type, sec_type)
        cv2.putText(
            thumb_img, label, (x1, max(y1 - 5, 15)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA,
        )
    _, buf = cv2.imencode(".png", thumb_img)
    return buf.tobytes()


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
    return ["choice"] if page_idx == 0 else ["judge"]


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
    thumbs: list[bytes] = st.session_state.get("calib_thumbnails", [])

    preprocessor = ImagePreprocessor()
    images: list[np.ndarray] = []
    binaries: list[np.ndarray] = []
    corrected_images: list[np.ndarray] = []
    for path in temp_paths:
        img = preprocessor.load(path)
        result = preprocessor.process(img)
        images.append(img)
        binaries.append(result.binary)
        corrected_images.append(result.corrected)

    from exam_project.recognition.layout import LayoutAnalyzer
    analyzer = LayoutAnalyzer()
    pages_config = layout.get("_pages") if layout else None
    if pages_config:
        regions_list = analyzer.analyze_multipage(images, binaries)
    else:
        regions_list = [
            analyzer.analyze(c, b, page=idx + 1)
            for idx, (c, b) in enumerate(zip(corrected_images, binaries))
        ]

    st.session_state["calib_regions_list"] = regions_list
    st.session_state["calib_corrected_images"] = corrected_images

    total_choice = 0
    total_judge = 0
    for page_idx, (thumb, regions, orig_img) in enumerate(zip(thumbs, regions_list, images)):
        with st.container(border=True):
            c1, c2 = st.columns([1, 2])
            with c1:
                annotated = _draw_regions_on_thumbnail(
                    thumb, regions, orig_img.shape,
                )
                st.image(annotated, caption=f"第 {page_idx + 1} 页（彩色框=检测区域）")
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
                result_choice = compute_blank_baseline(temp_paths[0], layout, page=1)
                result_judge = compute_blank_baseline(temp_paths[0], layout, page=2)
                baseline = {**result_choice, **result_judge}
            else:
                baseline = compute_blank_baseline_multipage(temp_paths, layout)
            st.session_state["calib_baseline"] = baseline
            st.success(f"已计算 {len(baseline)} 个 section 的基准。")
        except Exception as exc:
            st.error(f"计算失败: {exc}")


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
    # layout 从项目 manifest 取
    layout: Optional[dict] = None
    try:
        layout_obj = project.manifest.layout
        if isinstance(layout_obj, dict):
            layout = layout_obj
        else:
            layout = layout_obj.to_dict() if hasattr(layout_obj, "to_dict") else None
    except Exception:
        layout = None

    if "calib_step" not in st.session_state:
        st.session_state["calib_step"] = 1

    page_count = 2
    if layout and layout.get("_pages"):
        page_count = len(layout["_pages"])

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
