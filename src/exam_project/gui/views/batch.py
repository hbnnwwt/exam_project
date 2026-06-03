"""批量阅卷视图。

遍历 data/answer_sheets 目录下所有答题卡，识别并评分，输出 xlsx 结果。

完全基于 exam_project 自有后端。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import streamlit as st

from exam_project.grading.grading import GradingService
from exam_project.grading.llm_grader import LLMEssayGrader
from exam_project.grading.marker import mark_and_save
from exam_project.grading.pipeline import (
    extract_student_id,
    preprocess_and_analyze,
    recognize_choices,
    recognize_essay,
    recognize_judges,
)
from exam_project.recognition.choice import ChoiceRecognizer
from exam_project.recognition.essay import EssayRecognizer
from exam_project.recognition.judge import JudgeRecognizer
from exam_project.recognition.layout import LayoutAnalyzer
from exam_project.recognition.preprocess import ImagePreprocessor
from exam_project.recognition.student_id import StudentIdRecognizer
from exam_project.constants import sorted_image_paths, is_image_file

from .components import (
    load_image_from_bytes,
    project_paths_for_session,
)


# checkpoint 文件名
BATCH_CHECKPOINT_NAME = "_batch_checkpoint.json"


def _load_checkpoint(checkpoint_path: Path) -> dict:
    """加载批量检查点（已处理的学号集合）。"""
    if not checkpoint_path.is_file():
        return {"processed": {}}
    try:
        return json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"processed": {}}


def _save_checkpoint(checkpoint_path: Path, data: dict) -> None:
    """原子保存检查点。"""
    tmp = checkpoint_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(checkpoint_path)


def _find_answer_sheets(answer_sheets_dir: Path) -> list[Path]:
    """收集目录下所有图像文件，按自然数顺序。"""
    if not answer_sheets_dir.is_dir():
        return []
    paths = [p for p in answer_sheets_dir.iterdir() if p.is_file() and is_image_file(p)]
    return sorted_image_paths([str(p) for p in paths])


def _pair_pages(sheets: list[Path]) -> list[tuple[Optional[Path], Optional[Path]]]:
    """把单页/双页答题卡配对。

    命名约定：xxx_page1.png + xxx_page2.png → 同一学生。
    单独一个 png → 单页。
    """
    by_stem: dict[str, dict[int, Path]] = {}
    singles: list[Path] = []
    for path in sheets:
        name = path.stem
        if name.endswith("_page1"):
            stem = name[:-6]
            by_stem.setdefault(stem, {})[1] = path
        elif name.endswith("_page2"):
            stem = name[:-6]
            by_stem.setdefault(stem, {})[2] = path
        else:
            singles.append(path)

    pairs: list[tuple[Optional[Path], Optional[Path]]] = []
    for stem in sorted(by_stem.keys()):
        d = by_stem[stem]
        pairs.append((d.get(1), d.get(2)))
    for s in singles:
        pairs.append((s, None))
    return pairs


def _process_one(
    page1_path: Path,
    page2_path: Optional[Path],
    project,
    paths: dict,
    controls: dict,
    baseline: dict,
) -> tuple[Optional[str], dict, Optional[np.ndarray], Optional[np.ndarray], dict, Optional[dict]]:
    """处理单套答题卡。返回 (student_id, recognized, page1_corr, page2_corr, regions1, regions2)。"""
    page1 = cv2.imdecode(np.fromfile(str(page1_path), dtype=np.uint8), cv2.IMREAD_COLOR)
    page2 = None
    if page2_path is not None:
        page2 = cv2.imdecode(np.fromfile(str(page2_path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if page1 is None:
        raise ValueError(f"无法加载图像: {page1_path}")

    preprocessor = ImagePreprocessor()
    analyzer = LayoutAnalyzer()
    regions1, page1_corr = preprocess_and_analyze(page1, 1, preprocessor, analyzer)
    student_id = extract_student_id(
        page1_corr, regions1, digit_count=10, threshold=0.3,
        recognizer=StudentIdRecognizer(digit_count=10, threshold=0.3),
    )

    choice_recog = ChoiceRecognizer(
        threshold=controls.get("threshold", 0.06),
        blank_baseline=baseline.get("choice_baseline") or {},
        zone_bounds_template=baseline.get("choice_zone_bounds") or {},
    )
    judge_recog = JudgeRecognizer(
        threshold=controls.get("threshold", 0.06),
        blank_baseline=baseline.get("judge_baseline") or {},
        zone_bounds_template=baseline.get("judge_zone_bounds") or {},
    )
    essay_recog = EssayRecognizer(
        engine=controls.get("ocr_engine", "paddleocr"),
        api_config=controls.get("ocr_api_config") or {},
    )

    recognized: dict = {"student_id": student_id, "choice": {}, "judge": {}, "essay": {}}
    recognized["choice"] = recognize_choices(
        page1_corr, regions1, controls.get("threshold", 0.06),
        blank_baseline=baseline.get("choice_baseline"),
        zone_bounds=baseline.get("choice_zone_bounds"),
        recognizer=choice_recog,
    )

    page2_corr: Optional[np.ndarray] = None
    regions2: Optional[dict] = None
    if page2 is not None:
        regions2_obj, page2_corr = preprocess_and_analyze(page2, 2, preprocessor, analyzer)
        recognized["judge"] = recognize_judges(
            page2_corr, regions2_obj, controls.get("threshold", 0.06),
            blank_baseline=baseline.get("judge_baseline"),
            zone_bounds=baseline.get("judge_zone_bounds"),
            recognizer=judge_recog,
        )
        essay_result = recognize_essay(
            page2_corr, regions2_obj,
            ocr_engine=controls.get("ocr_engine", "paddleocr"),
            api_config=controls.get("ocr_api_config"),
            recognizer=essay_recog,
        )
        if essay_result.text or essay_result.status in ("ok", "low_confidence"):
            recognized["essay"] = {31: essay_result}
        regions2 = regions2_obj.to_dict() if hasattr(regions2_obj, "to_dict") else regions2_obj

    return (
        student_id, recognized, page1_corr, page2_corr,
        regions1.to_dict() if hasattr(regions1, "to_dict") else regions1,
        regions2,
    )


def _save_results_xlsx(
    svc: GradingService,
    template_path: Optional[Path],
    output_path: Path,
    student_results: list[tuple[Optional[str], dict]],
) -> None:
    """保存批量评分结果为 xlsx。"""
    if template_path and template_path.is_file():
        svc.save_result_xlsx(template_path, output_path, student_results)
    else:
        # 无模板时直接生成简单 xlsx
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.cell(row=1, column=1, value="学号")
        ws.cell(row=1, column=2, value="选择题总分")
        ws.cell(row=1, column=3, value="判断题总分")
        ws.cell(row=1, column=4, value="简答题总分")
        ws.cell(row=1, column=5, value="总分")
        for idx, (sid, _) in enumerate(student_results, start=2):
            result = svc.grade(student_results[idx - 2][1])
            ws.cell(row=idx, column=1, value=sid)
            ws.cell(row=idx, column=2, value=result.choice_total)
            ws.cell(row=idx, column=3, value=result.judge_total)
            ws.cell(row=idx, column=4, value=result.essay_total)
            ws.cell(row=idx, column=5, value=result.total)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(output_path)


def render_batch(
    project,
    paths: dict,
    controls: dict,
    baseline: dict = None,
) -> None:
    """批量阅卷视图主入口。"""
    baseline = baseline or {}
    st.markdown("### 批量阅卷")
    st.info(
        "将答题卡图片（page1 + 可选 page2）放到项目 `data/answer_sheets/` 目录下，"
        "点击开始批量识别。"
    )

    paths_dict = project_paths_for_session(project.workdir)
    answer_sheets_dir = Path(paths_dict["default_folder"])
    processed_dir = Path(paths_dict["processed_dir"])
    checkpoint_path = Path(paths_dict["batch_checkpoint"])
    template_xlsx = Path(paths_dict["answer_key"])

    sheets = _find_answer_sheets(answer_sheets_dir)
    if not sheets:
        st.warning(f"未在 {answer_sheets_dir} 找到图像文件。")
        return

    pairs = _pair_pages(sheets)
    st.write(f"找到 {len(sheets)} 张图像，{len(pairs)} 个学生。")

    # 加载 GradingService
    svc = _load_grading_service(template_xlsx)
    if svc is None:
        st.error("参考答案加载失败，请先在项目 config 目录放置有效的 参考答案.xlsx。")
        return
    if controls.get("llm_enabled") and (controls.get("llm_api_key") or "").strip():
        svc.essay_grader = LLMEssayGrader(
            api_key=controls.get("llm_api_key"),
            base_url=controls.get("llm_base_url"),
            model=controls.get("llm_model"),
            max_tokens=controls.get("llm_max_tokens", 256),
            temperature=controls.get("llm_temperature", 0.3),
        )

    if not st.button("开始批量识别 + 评分", type="primary"):
        return

    checkpoint = _load_checkpoint(checkpoint_path)
    student_results: list[tuple[Optional[str], dict]] = []
    progress = st.progress(0.0)
    for idx, (p1, p2) in enumerate(pairs, start=1):
        if p1 is None:
            continue
        student_id_hint = (p1.stem if p1 else "?")
        if student_id_hint in checkpoint["processed"]:
            continue
        try:
            sid, recognized, p1_corr, p2_corr, regions1, regions2 = _process_one(
                p1, p2, project, paths_dict, controls, baseline,
            )
            result = svc.grade(recognized)
            student_results.append((sid, recognized))

            # 标注并保存
            mark_and_save(
                student_id=sid,
                page1=p1_corr,
                page2=p2_corr,
                regions1=regions1,
                regions2=regions2 or {},
                choice_cells=[],
                judge_cells=[],
                grading_result={
                    "choice_total": result.choice_total,
                    "judge_total": result.judge_total,
                    "essay_total": result.essay_total,
                    "choice": dict(result.choice),
                    "judge": dict(result.judge),
                },
                choice_max=len(svc.answer_key.get("choice", {})) * svc.config.choice_score,
                judge_max=len(svc.answer_key.get("judge", {})) * svc.config.judge_score,
                essay_max=len(svc.answer_key.get("essay", {})) * svc.config.essay_max_score,
                output_dir=processed_dir,
            )
            checkpoint["processed"][student_id_hint] = True
            _save_checkpoint(checkpoint_path, checkpoint)
        except Exception as exc:
            st.warning(f"处理 {p1.name} 失败: {exc}")
        progress.progress(idx / len(pairs))

    # 输出 xlsx
    if student_results:
        output_xlsx = processed_dir.parent / "结果.xlsx"
        try:
            _save_results_xlsx(svc, template_xlsx, output_xlsx, student_results)
            st.success(f"批量完成。{len(student_results)} 个学生，结果已保存到 {output_xlsx}")
        except Exception as exc:
            st.error(f"保存结果失败: {exc}")
    else:
        st.info("没有新处理的学生（可能都已处理过）。")


def _load_grading_service(template_xlsx: Path) -> Optional[GradingService]:
    if not template_xlsx.is_file():
        return None
    try:
        return GradingService.from_xlsx(template_xlsx)
    except Exception:
        return None
