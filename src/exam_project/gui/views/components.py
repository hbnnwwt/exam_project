"""共享 UI 辅助。

复用 exam_project 自有的 grading/recognition 模块，不依赖 auto_grading_system。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from exam_project.grading.grading import GradingService
from exam_project.grading.llm_grader import LLMEssayGrader


# 上传的参考答案落地路径（项目工作区内）
DEFAULT_UPLOADED_AK_SUBDIR = "uploaded"


def save_uploaded_answer_key(
    uploaded_file,
    project_workdir: Path,
) -> str:
    """把用户上传的 xlsx 落地到当前项目 workdir，返回路径。"""
    target_dir = project_workdir / DEFAULT_UPLOADED_AK_SUBDIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / "_uploaded_answer_key.xlsx"
    path.write_bytes(uploaded_file.getbuffer())
    return str(path)


def clear_uploaded_answer_key(project_workdir: Path) -> None:
    """删除当前项目 workdir 下已上传的参考答案。"""
    path = project_workdir / DEFAULT_UPLOADED_AK_SUBDIR / "_uploaded_answer_key.xlsx"
    if path.is_file():
        path.unlink()


def uploaded_answer_key_exists(project_workdir: Path) -> bool:
    return (project_workdir / DEFAULT_UPLOADED_AK_SUBDIR / "_uploaded_answer_key.xlsx").is_file()


def load_svc_with_upload(
    uploaded_file,
    fallback_path: Optional[str | Path],
    project_workdir: Path,
    llm_enabled: bool = False,
    llm_api_key: str = "",
    llm_base_url: str = "",
    llm_model: str = "",
    llm_max_tokens: int = 256,
    llm_temperature: float = 0.3,
):
    """加载评分服务。优先级：用户上传 > 磁盘默认路径 > None。

    Args:
        uploaded_file: streamlit.file_uploader 返回的对象
        fallback_path: 项目 workdir 下参考答案的默认路径
        project_workdir: 当前项目工作目录
        llm_*: LLM 评分器参数（可选）
    """
    svc = None

    if uploaded_file is not None:
        try:
            ak_path = save_uploaded_answer_key(uploaded_file, project_workdir)
            svc = GradingService.from_xlsx(ak_path)
        except Exception as exc:
            import streamlit as st
            st.warning(f"上传的参考答案加载失败: {exc}")

    if svc is None and fallback_path and Path(fallback_path).is_file():
        try:
            svc = GradingService.from_xlsx(fallback_path)
        except Exception as exc:
            import streamlit as st
            st.warning(f"默认参考答案文件加载失败: {exc}")

    has_key = bool(llm_api_key.strip()) if isinstance(llm_api_key, str) else bool(llm_api_key)
    if svc and llm_enabled and has_key:
        svc.essay_grader = LLMEssayGrader(
            api_key=llm_api_key,
            base_url=llm_base_url,
            model=llm_model,
            max_tokens=llm_max_tokens,
            temperature=llm_temperature,
        )
    return svc


def load_image(path: str | Path) -> np.ndarray:
    """从路径加载图像。"""
    buf = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Cannot decode image: {path}")
    return img


def load_image_from_bytes(data: bytes) -> np.ndarray:
    """从字节流加载图像。"""
    buf = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Cannot decode image")
    return img


def render_question_table(
    q_start: int,
    q_end: int,
    answers: dict,
    result_detail: Optional[dict] = None,
) -> list[dict]:
    """渲染题号表格数据。返回 list of dict，可直接喂给 st.dataframe。"""
    rows: list[dict] = []
    for q in range(q_start, q_end + 1):
        given = answers.get(q, "-")
        if result_detail and q in result_detail:
            d = result_detail[q]
            correct = d.get("correct") or "-"
            mark = "O" if d.get("score", 0) > 0 else "X"
        else:
            correct, mark = "-", "-"
        rows.append({
            "题号": q,
            "学生答案": given or "-",
            "正确答案": correct,
            "结果": mark,
        })
    return rows


def project_paths_for_session(project_workdir: Path) -> dict[str, str]:
    """为当前项目 workdir 构造 grading views 需要的路径字典。

    返回字段：answer_key / default_folder / output_dir / processed_dir /
              api_keys / model_config / batch_checkpoint。
    """
    data_dir = project_workdir / "data"
    config_dir = project_workdir / "config"
    return {
        "answer_key": str(project_workdir / "参考答案.xlsx"),
        "default_folder": str(data_dir / "answer_sheets"),
        "output_dir": str(data_dir / "output"),
        "processed_dir": str(data_dir / "processed"),
        "api_keys": str(config_dir / "api_keys.json"),
        "model_config": str(config_dir / "model_config.json"),
        "batch_checkpoint": str(data_dir / "output" / "_batch_checkpoint.json"),
    }
