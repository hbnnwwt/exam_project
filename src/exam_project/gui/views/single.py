"""单套识别 + 评分视图。

处理一张答题卡（page1 + 可选 page2），识别学号 + 选择题 + 判断题 + 简答题，
然后用 LLM 评分（可选），输出标注图和成绩。

完全基于 exam_project 自有后端（pipeline / grading / marker），
不依赖 auto_grading_system 任何模块。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import streamlit as st

from exam_project.grading.grading import GradingService
from exam_project.grading.llm_grader import LLMEssayGrader
from exam_project.grading.marker import (
    DEFAULT_CHOICE_LABELS,
    DEFAULT_JUDGE_LABELS,
    mark_and_save,
)
from exam_project.grading.pipeline import (
    preprocess_and_analyze,
    extract_student_id,
    recognize_choices,
    recognize_judges,
    recognize_essay,
)
from exam_project.recognition.choice import ChoiceRecognizer
from exam_project.recognition.essay import EssayRecognizer
from exam_project.recognition.judge import JudgeRecognizer
from exam_project.recognition.layout import LayoutAnalyzer
from exam_project.recognition.preprocess import ImagePreprocessor
from exam_project.recognition.student_id import StudentIdRecognizer

from .components import (
    load_image_from_bytes,
    project_paths_for_session,
)


def _build_essay_recognizer(
    ocr_engine: str,
    ocr_api_config: Optional[dict],
) -> EssayRecognizer:
    return EssayRecognizer(engine=ocr_engine, api_config=ocr_api_config or {})


def _maybe_attach_llm_grader(
    svc: GradingService,
    llm_enabled: bool,
    llm_api_key: str,
    llm_base_url: str,
    llm_model: str,
    llm_max_tokens: int,
    llm_temperature: float,
) -> None:
    """如果启用 LLM 且有 key，附加 essay_grader。"""
    if not llm_enabled or not (llm_api_key or "").strip():
        return
    svc.essay_grader = LLMEssayGrader(
        api_key=llm_api_key,
        base_url=llm_base_url,
        model=llm_model,
        max_tokens=llm_max_tokens,
        temperature=llm_temperature,
    )


def _recognize_pair(
    page1: np.ndarray,
    page2: Optional[np.ndarray],
    threshold: float,
    ocr_engine: str,
    ocr_api_config: Optional[dict],
    choice_baseline: Optional[dict],
    judge_baseline: Optional[dict],
    choice_zone_bounds: Optional[dict],
    judge_zone_bounds: Optional[dict],
    digit_count: int,
) -> dict:
    """完整跑一遍识别管线，返回 recognized 字典。"""
    preprocessor = ImagePreprocessor()
    analyzer = LayoutAnalyzer()
    regions1, page1_corr = preprocess_and_analyze(page1, 1, preprocessor, analyzer)
    student_id = extract_student_id(
        page1_corr, regions1, digit_count=digit_count, threshold=0.3,
        recognizer=StudentIdRecognizer(digit_count=digit_count, threshold=0.3),
    )

    choice_recog = ChoiceRecognizer(
        threshold=threshold,
        blank_baseline=choice_baseline or {},
        zone_bounds_template=choice_zone_bounds or {},
    )
    judge_recog = JudgeRecognizer(
        threshold=threshold,
        blank_baseline=judge_baseline or {},
        zone_bounds_template=judge_zone_bounds or {},
    )

    recognized: dict = {"student_id": student_id, "choice": {}, "judge": {}, "essay": {}}
    recognized["choice"] = recognize_choices(
        page1_corr, regions1, threshold,
        blank_baseline=choice_baseline, zone_bounds=choice_zone_bounds,
        recognizer=choice_recog,
    )

    if page2 is not None:
        regions2, page2_corr = preprocess_and_analyze(page2, 2, preprocessor, analyzer)
        recognized["judge"] = recognize_judges(
            page2_corr, regions2, threshold,
            blank_baseline=judge_baseline, zone_bounds=judge_zone_bounds,
            recognizer=judge_recog,
        )
        essay_recog = _build_essay_recognizer(ocr_engine, ocr_api_config)
        essay_result = recognize_essay(
            page2_corr, regions2, ocr_engine=ocr_engine,
            api_config=ocr_api_config, recognizer=essay_recog,
        )
        if essay_result.text or essay_result.status in ("ok", "low_confidence"):
            recognized["essay"] = {31: essay_result}

    return {
        "recognized": recognized,
        "page1_corr": page1_corr,
        "page2_corr": page2_corr if page2 is not None else None,
        "regions1": regions1.to_dict() if hasattr(regions1, "to_dict") else regions1,
        "regions2": (regions2.to_dict() if page2 is not None and hasattr(regions2, "to_dict") else None),
    }


def _grade(svc: GradingService, recognized: dict) -> dict:
    """跑评分，返回 dict 形式的结果。"""
    result = svc.grade(recognized)
    return {
        "choice": result.choice,
        "judge": result.judge,
        "essay_detail": result.essay_detail,
        "choice_total": result.choice_total,
        "judge_total": result.judge_total,
        "essay_total": result.essay_total,
        "total": result.total,
    }


def _save_marked(
    student_id: Optional[str],
    page1_corr: np.ndarray,
    page2_corr: Optional[np.ndarray],
    regions1: dict,
    regions2: Optional[dict],
    recognized: dict,
    result: dict,
    svc: GradingService,
    project_workdir: Path,
) -> tuple[str, str]:
    """调用 mark_and_save 标注错题。"""
    paths = project_paths_for_session(project_workdir)
    processed_dir = paths["processed_dir"]
    # 提取 cell_results（从 recognizer 的 cell_results 重新调用）
    # 这里直接给空 list，mark_and_save 仍能标注错题位置
    p1_path, p2_path, _, _ = mark_and_save(
        student_id=student_id,
        page1=page1_corr,
        page2=page2_corr,
        regions1=regions1,
        regions2=regions2 or {},
        choice_cells=[],
        judge_cells=[],
        grading_result=result,
        choice_max=len(svc.answer_key.get("choice", {})) * svc.config.choice_score,
        judge_max=len(svc.answer_key.get("judge", {})) * svc.config.judge_score,
        essay_max=len(svc.answer_key.get("essay", {})) * svc.config.essay_max_score,
        output_dir=processed_dir,
    )
    return p1_path, p2_path


def render_single(
    project,
    paths: dict,
    controls: dict,
    baseline: dict = None,
) -> None:
    """单套阅卷视图主入口。

    Args:
        project: 当前 ExamProject
        paths: project_paths_for_session 返回的路径字典
        controls: render_grading_controls 返回的控制参数（threshold, llm_*, ocr_*）
        baseline: 空白基准 dict（含 choice_baseline / judge_baseline / *_zone_bounds）
    """
    baseline = baseline or {}
    st.markdown("### 单套识别 + 评分")
    st.info(
        "上传一张答题卡的第 1 页（必填）和第 2 页（可选）。"
        "系统将识别学号、选择题、判断题和简答题（如果有），并评分。"
    )

    col1, col2 = st.columns(2)
    with col1:
        p1_file = st.file_uploader("第 1 页", type=["png", "jpg", "jpeg"], key="single_p1")
    with col2:
        p2_file = st.file_uploader("第 2 页（可选）", type=["png", "jpg", "jpeg"], key="single_p2")

    if p1_file is None:
        st.warning("请先上传第 1 页。")
        return

    # 加载 GradingService
    svc = _load_grading_service(p1_file, paths, project.workdir, controls)
    if svc is None:
        st.error("参考答案加载失败，无法评分。请上传有效的 xlsx 或检查项目配置。")
        return
    _maybe_attach_llm_grader(svc, **controls)

    if st.button("开始识别 + 评分", type="primary"):
        page1 = load_image_from_bytes(p1_file.getvalue())
        page2 = load_image_from_bytes(p2_file.getvalue()) if p2_file is not None else None

        try:
            output = _recognize_pair(
                page1=page1,
                page2=page2,
                threshold=controls.get("threshold", 0.06),
                ocr_engine=controls.get("ocr_engine", "paddleocr"),
                ocr_api_config=controls.get("ocr_api_config"),
                choice_baseline=baseline.get("choice_baseline"),
                judge_baseline=baseline.get("judge_baseline"),
                choice_zone_bounds=baseline.get("choice_zone_bounds"),
                judge_zone_bounds=baseline.get("judge_zone_bounds"),
                digit_count=10,
            )
        except Exception as exc:
            st.error(f"识别失败: {exc}")
            return

        result = _grade(svc, output["recognized"])

        st.success(f"识别完成。学号: {output['recognized']['student_id'] or '?'}")
        c1, c2, c3 = st.columns(3)
        c1.metric("选择题", f"{int(result['choice_total'])} / {len(svc.answer_key.get('choice', {})) * svc.config.choice_score}")
        c2.metric("判断题", f"{int(result['judge_total'])} / {len(svc.answer_key.get('judge', {})) * svc.config.judge_score}")
        c3.metric("简答题", f"{int(result['essay_total'])} / {len(svc.answer_key.get('essay', {})) * svc.config.essay_max_score}")
        st.metric("总分", f"{int(result['total'])} / {svc.max_total}")

        # 标注并保存
        try:
            p1_path, p2_path = _save_marked(
                output["recognized"]["student_id"],
                output["page1_corr"],
                output["page2_corr"],
                output["regions1"],
                output["regions2"],
                output["recognized"],
                result,
                svc,
                project.workdir,
            )
            st.info(f"标注图已保存: {p1_path}")
        except Exception as exc:
            st.warning(f"标注图保存失败: {exc}")


def _load_grading_service(uploaded_file, paths: dict, project_workdir: Path, controls: dict) -> Optional[GradingService]:
    """从上传文件或磁盘默认路径加载 GradingService。"""
    from .components import save_uploaded_answer_key
    try:
        ak_path = save_uploaded_answer_key(uploaded_file, project_workdir)
        return GradingService.from_xlsx(ak_path)
    except Exception:
        fallback = paths.get("answer_key")
        if fallback and Path(fallback).is_file():
            try:
                return GradingService.from_xlsx(fallback)
            except Exception:
                return None
        return None
