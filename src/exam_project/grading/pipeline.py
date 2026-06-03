"""识别管线编排。

提供识别一整张答题卡（单页或多页）的高层函数。
所有函数显式接受配置参数，不再有 import-time LAYOUT 全局。
"""

from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from exam_project.recognition.choice import ChoiceRecognizer
from exam_project.recognition.essay import ApiConfig as EssayApiConfig, EssayRecognizer
from exam_project.recognition.judge import JudgeRecognizer
from exam_project.recognition.layout import LayoutAnalyzer
from exam_project.recognition.preprocess import ImagePreprocessor
from exam_project.recognition.student_id import StudentIdRecognizer
from exam_project.recognition.types import RecognizeResult


def _valid_region(val) -> bool:
    """检查 region 是否为有效且非空的 (x, y, w, h) 序列。

    任意维度为 0 或负数视为无效。
    """
    if not (
        isinstance(val, (tuple, list))
        and len(val) == 4
        and all(isinstance(v, (int, float)) for v in val)
    ):
        return False
    _, _, w, h = val
    return w > 0 and h > 0


def get_essay_questions(answer_key: Optional[dict] = None) -> list[int]:
    """获取简答题题号列表，优先从答案键推断，否则 fallback 到 [31]。"""
    if answer_key is not None and "essay" in answer_key:
        if answer_key["essay"]:
            return sorted(answer_key["essay"].keys())
        return []
    return [31]


def preprocess_and_analyze(
    image: np.ndarray,
    page: int,
    preprocessor: Optional[ImagePreprocessor] = None,
    analyzer: Optional[LayoutAnalyzer] = None,
) -> tuple[dict, np.ndarray]:
    """预处理图像并分析版面，返回 (regions_dict, corrected_image)。"""
    if preprocessor is None:
        preprocessor = ImagePreprocessor()
    if analyzer is None:
        analyzer = LayoutAnalyzer()
    result = preprocessor.process(image)
    corrected, _, _, binary = (
        result.corrected, result.gray, result.enhanced, result.binary
    )
    page_regions = analyzer.analyze(corrected, binary, page=page)
    return (
        {
            "student_id": page_regions.student_id,
            "choice": page_regions.choice,
            "judge": page_regions.judge,
            "essay": page_regions.essay,
            "image_size": page_regions.image_size,
        },
        corrected,
    )


def extract_student_id(
    image: np.ndarray,
    regions: dict,
    digit_count: Optional[int] = None,
    threshold: float = 0.3,
    recognizer: Optional[StudentIdRecognizer] = None,
) -> Optional[str]:
    """从版面区域中提取学号。"""
    if recognizer is None:
        recognizer = StudentIdRecognizer(digit_count=digit_count or 10, threshold=threshold)
    region = regions.get("student_id")
    if not _valid_region(region):
        return None
    x, y, w, h = region
    roi = image[y:y + h, x:x + w]
    return recognizer.recognize(roi)


def recognize_choices(
    image: np.ndarray,
    regions: dict,
    threshold: float = 0.06,
    blank_baseline: Optional[dict] = None,
    zone_bounds: Optional[dict] = None,
    recognizer: Optional[ChoiceRecognizer] = None,
) -> dict:
    """识别选择题答案。"""
    if recognizer is None:
        recognizer = ChoiceRecognizer(
            threshold=threshold,
            blank_baseline=blank_baseline,
            zone_bounds_template=zone_bounds,
        )
    region = regions.get("choice")
    if not _valid_region(region):
        return {}
    x, y, w, h = region
    roi = image[y:y + h, x:x + w]
    result = recognizer.recognize_all_with_viz(
        roi,
        question_count=recognizer.zone_count * 5,  # 默认 5 行
        question_start=1,
        fixed_grid=(5, 4),
    )
    return result.answers


def recognize_judges(
    image: np.ndarray,
    regions: dict,
    threshold: float = 0.06,
    blank_baseline: Optional[dict] = None,
    zone_bounds: Optional[dict] = None,
    recognizer: Optional[JudgeRecognizer] = None,
) -> dict:
    """识别判断题答案。"""
    if recognizer is None:
        recognizer = JudgeRecognizer(
            threshold=threshold,
            blank_baseline=blank_baseline,
            zone_bounds_template=zone_bounds,
        )
    region = regions.get("judge")
    if not _valid_region(region):
        return {}
    x, y, w, h = region
    roi = image[y:y + h, x:x + w]
    result = recognizer.recognize_all_with_viz(
        roi,
        question_count=recognizer.zone_count * 5,
        question_start=21,
        rows_n=3,
        cols_n=4,
    )
    return result.answers


def recognize_essay(
    image: np.ndarray,
    regions: dict,
    ocr_engine: str = "paddleocr",
    api_config: Optional[dict] = None,
    recognizer: Optional[EssayRecognizer] = None,
) -> RecognizeResult:
    """识别简答题答案，返回 RecognizeResult。"""
    if recognizer is None:
        recognizer = EssayRecognizer(
            engine=ocr_engine,
            api_config=api_config or {},
        )
    region = regions.get("essay")
    if not _valid_region(region):
        return RecognizeResult(text="", status="blank", error="未检测到简答题区域")
    x, y, w, h = region
    roi = image[y:y + h, x:x + w]
    return recognizer.recognize(roi)


def process_student_pair(
    page1_path: str,
    page2_path: Optional[str] = None,
    preprocessor: Optional[ImagePreprocessor] = None,
    analyzer: Optional[LayoutAnalyzer] = None,
    digit_count: Optional[int] = None,
    threshold: float = 0.5,
    essay_questions: Optional[list[int]] = None,
    choice_baseline: Optional[dict] = None,
    judge_baseline: Optional[dict] = None,
) -> tuple[Optional[str], dict]:
    """处理一个学生的答题卡（第一页 + 可选第二页）。

    Returns:
        (student_id, recognized_answers)
    """
    if preprocessor is None:
        preprocessor = ImagePreprocessor()
    if analyzer is None:
        analyzer = LayoutAnalyzer()
    if essay_questions is None:
        essay_questions = get_essay_questions()

    image1_preprocessor = preprocessor
    image1_analyzer = analyzer
    image1 = preprocessor.load(page1_path)
    regions1, image1 = preprocess_and_analyze(
        image1, 1, image1_preprocessor, image1_analyzer,
    )

    student_id = extract_student_id(image1, regions1, digit_count, threshold)
    choice_answers = recognize_choices(
        image1, regions1, threshold,
        blank_baseline=choice_baseline,
    )

    recognized: dict = {"choice": choice_answers, "judge": {}, "essay": {}}

    if page2_path:
        image2 = preprocessor.load(page2_path)
        regions2, image2 = preprocess_and_analyze(
            image2, 2, image1_preprocessor, image1_analyzer,
        )
        recognized["judge"] = recognize_judges(
            image2, regions2, threshold,
            blank_baseline=judge_baseline,
        )
        essay_result = recognize_essay(image2, regions2)
        if essay_result.text or essay_result.status in ("ok", "low_confidence"):
            q = essay_questions[0] if essay_questions else 31
            recognized["essay"] = {q: essay_result}

    return student_id, recognized
