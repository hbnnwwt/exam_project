from __future__ import annotations

import importlib
import tempfile
from pathlib import Path
from typing import Any

import streamlit as st

from exam_project.core.errors import ProjectError
from exam_project.core.package import ExamProjectPackage
from exam_project.gui.session import (
    ProjectSession,
    create_and_open_project,
    import_and_open_project,
    open_project,
    save_project,
    save_project_as,
)


SESSION_KEY = "exam_project_session"
FLASH_KEY = "exam_project_flash"
DESIGNER_PROJECT_KEY = "exam_project_designer_project_id"


def inspect_package(package_path: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="exam_project_gui_inspect_") as temp:
        project = ExamProjectPackage.open(package_path, Path(temp) / "opened")
        return project.manifest.to_dict()


def show_project_error(error: Exception) -> None:
    if isinstance(error, ProjectError):
        st.error(error.user_message)
    else:
        st.error(str(error))


def current_session() -> ProjectSession | None:
    value = st.session_state.get(SESSION_KEY)
    return value if isinstance(value, ProjectSession) else None


def set_current_session(session: ProjectSession) -> None:
    st.session_state[SESSION_KEY] = session


def clear_current_session() -> None:
    st.session_state.pop(SESSION_KEY, None)


def show_flash_message() -> None:
    message = st.session_state.pop(FLASH_KEY, None)
    if message:
        st.success(message)


def _split_semicolon(text: str) -> list[str]:
    import re

    return [part.strip() for part in re.split(r"[;；]", text) if part.strip()]


def _merge_primary_and_fallback(primary: Any, fallback_list: list[str]) -> Any:
    result: list[str] = []
    if primary:
        if isinstance(primary, str):
            result.append(primary)
        else:
            result.extend(primary)
    for item in fallback_list:
        if item and item not in result:
            result.append(item)
    if len(result) == 1:
        return result[0]
    return result if result else ""


def _load_legacy_module(name: str):
    return importlib.import_module(name)


def _reset_designer_state_for_project(session: ProjectSession) -> None:
    project_id = session.manifest.project_id
    if st.session_state.get(DESIGNER_PROJECT_KEY) == project_id:
        return
    for key in list(st.session_state.keys()):
        if key == "designer_config" or key.startswith("designer_"):
            del st.session_state[key]
    st.session_state[DESIGNER_PROJECT_KEY] = project_id


def _layout_ready(layout: dict[str, Any]) -> tuple[bool, str]:
    missing = []
    for key in ("choice", "judge"):
        value = layout.get(key)
        if not isinstance(value, dict) or not value:
            missing.append(key)
    if missing:
        return False, "当前项目布局尚未声明题型区域: " + ", ".join(missing)
    return True, ""


def render_designer_tab(session: ProjectSession) -> None:
    from exam_project.gui.views.designer import render_designer
    try:
        st.info("同步识别配置后，请点击左侧“保存”写回 .examproj 项目包。")
        render_designer(session.project)
    except Exception as exc:
        st.error(f"答题卡设计器加载失败: {exc}")


def render_calibration_tab(session: ProjectSession) -> None:
    from exam_project.gui.views.calibration import render_calibration_view
    try:
        st.info("保存空白基准后，请点击左侧“保存”写回 .examproj 项目包。")
        render_calibration_view(session.project)
    except Exception as exc:
        st.error(f"空白校对模块加载失败: {exc}")


def render_start_page() -> None:
    st.title("Exam Project")
    st.caption("新建或打开一个考试项目后进入工作区。")

    new_tab, open_tab, import_tab, inspect_tab = st.tabs(
        ["新建项目", "打开项目", "导入旧项目", "检查项目包"]
    )

    with new_tab:
        st.subheader("创建新的空白 .examproj")
        new_package_output = st.text_input("输出项目包", value="demo.examproj", key="new_output")
        new_project_name = st.text_input("项目名称", value="期末考试", key="new_name")
        student_id_digits = st.number_input(
            "学号位数",
            min_value=6,
            max_value=14,
            value=10,
            step=1,
        )

        if st.button("新建并打开", type="primary"):
            try:
                session = create_and_open_project(
                    Path(new_package_output),
                    name=new_project_name,
                    student_id_digits=int(student_id_digits),
                )
            except Exception as exc:
                show_project_error(exc)
            else:
                set_current_session(session)
                st.rerun()

    with open_tab:
        st.subheader("打开已有 .examproj")
        package_path = st.text_input("项目包路径", value="", key="open_package")
        if st.button("打开项目", type="primary"):
            try:
                session = open_project(Path(package_path))
            except Exception as exc:
                show_project_error(exc)
            else:
                set_current_session(session)
                st.rerun()

    with import_tab:
        st.subheader("从旧系统资产创建 .examproj")
        legacy_root = st.text_input("旧项目目录", value="", key="legacy_root")
        package_output = st.text_input("输出项目包", value="imported.examproj", key="legacy_output")
        project_name = st.text_input("项目名称", value="期末考试", key="legacy_name")

        if st.button("导入并打开", type="primary"):
            try:
                session = import_and_open_project(
                    Path(legacy_root),
                    Path(package_output),
                    name=project_name,
                )
            except Exception as exc:
                show_project_error(exc)
            else:
                set_current_session(session)
                st.rerun()

    with inspect_tab:
        st.subheader("检查 .examproj manifest")
        inspect_path = st.text_input("项目包路径", value="", key="inspect_package")
        if st.button("检查项目包", type="primary"):
            try:
                manifest = inspect_package(Path(inspect_path))
            except Exception as exc:
                show_project_error(exc)
            else:
                st.json(manifest)


def render_project_sidebar(session: ProjectSession) -> None:
    with st.sidebar:
        st.header("当前项目")
        st.write(session.manifest.name)
        st.code(str(session.package_path), language=None)
        show_flash_message()

        if st.button("保存", type="primary", use_container_width=True):
            try:
                session = save_project(session)
            except Exception as exc:
                show_project_error(exc)
            else:
                set_current_session(session)
                st.session_state[FLASH_KEY] = "项目已保存"
                st.rerun()

        save_as_path = st.text_input(
            "另存为",
            value=str(session.package_path),
            key="save_as_path",
        )
        if st.button("另存为", use_container_width=True):
            try:
                session = save_project_as(session, Path(save_as_path))
            except Exception as exc:
                show_project_error(exc)
            else:
                set_current_session(session)
                st.session_state[FLASH_KEY] = "项目已另存"
                st.rerun()

        if st.button("关闭项目", use_container_width=True):
            clear_current_session()
            st.rerun()


def render_grading_controls(paths: dict[str, str]) -> dict[str, Any]:
    defaults = _load_legacy_module("modules.defaults")
    essay_recognizer = _load_legacy_module("modules.essay_recognizer")

    with st.sidebar:
        st.divider()
        st.header("阅卷参数")
        threshold = st.slider(
            "填涂阈值",
            0.02,
            0.30,
            0.06,
            0.01,
            help="黑色像素占比超过此值则判定为已填涂",
        )

        st.divider()
        st.header("API Key 配置")
        api_keys_path = paths["api_keys"]
        model_config_path = paths["model_config"]
        model_cfg = load_model_config(paths["model_config"])
        api_cfg = load_model_config(paths["api_keys"])
        saved_api_key = api_cfg.get("api_key", "")
        saved_ocr_key = api_cfg.get("ocr_api_key", "")

        api_key_input = st.text_input(
            "ModelScope API Key",
            value=saved_api_key,
            type="password",
            help="用于 LLM 评分和在线 OCR",
            key="project_api_key",
        )
        with st.expander("备用 API Key（可选）"):
            fallback_api_keys_input = st.text_area(
                "备用 Key 列表（用 ; 或 ； 分隔，限流时自动轮询）",
                value="; ".join(api_cfg.get("api_keys", [])),
                key="project_fallback_api_keys",
                height=80,
            )
        use_same_ocr_key = st.checkbox(
            "在线 OCR 使用同一个 Key",
            value=not str(saved_ocr_key).strip() or saved_ocr_key == saved_api_key,
            key="project_use_same_ocr_key",
        )
        if use_same_ocr_key:
            ocr_key_input = api_key_input
        else:
            ocr_key_input = st.text_input(
                "OCR 专用 API Key",
                value=saved_ocr_key,
                type="password",
                key="project_ocr_api_key",
            )
        if st.button("保存 API Key", type="primary", key="project_save_api_key"):
            fallback_keys = _split_semicolon(fallback_api_keys_input)
            save_json_config(
                api_keys_path,
                {
                    "api_key": api_key_input,
                    "api_keys": fallback_keys,
                    "ocr_api_key": "" if use_same_ocr_key else ocr_key_input,
                },
            )
            st.success("API Key 配置已保存到当前项目")

        api_cfg = load_model_config(api_keys_path)
        model_cfg = load_model_config(model_config_path)
        api_key = api_cfg.get("api_key", "")
        api_key = _merge_primary_and_fallback(api_key, api_cfg.get("api_keys", []))
        ocr_key = api_cfg.get("ocr_api_key", "") or api_key

        st.divider()
        st.header("OCR 引擎")
        available = [
            (engine, f"{engine} {'✓' if essay_recognizer.check_engine_available(engine) else '✗ 未安装'}")
            for engine in essay_recognizer.SUPPORTED_ENGINES
        ]
        labels = [label for _, label in available]
        values = [engine for engine, _ in available]
        default_engine = model_cfg.get("ocr_engine", values[0] if values else "paddleocr")
        default_engine_index = values.index(default_engine) if default_engine in values else 0
        selected = st.selectbox(
            "简答题 OCR 引擎",
            range(len(labels)),
            format_func=lambda index: labels[index],
            index=default_engine_index,
            key="project_ocr_engine",
        )
        ocr_engine = values[selected]
        online_ocr_model = model_cfg.get("ocr_model", defaults.DEFAULT_OCR_MODEL)
        if ocr_engine == "online":
            online_ocr_model = st.text_input(
                "在线 OCR 模型",
                value=online_ocr_model,
                help="视觉模型 ID，需支持 image_url 输入",
                key="project_online_ocr_model",
            )
            has_ocr_key = bool(ocr_key.strip() if isinstance(ocr_key, str) else ocr_key)
            if not has_ocr_key:
                st.warning("在线 OCR 需要配置 API Key")
        if ocr_engine != "online" and not essay_recognizer.check_engine_available(ocr_engine):
            st.warning(f"`{ocr_engine}` 未安装，将回退到 paddleocr")
            ocr_engine = "paddleocr"

        st.divider()
        st.header("模型配置")
        primary_base_url = model_cfg.get("base_url", defaults.DEFAULT_BASE_URL)
        base_url_input = st.text_input(
            "Base URL",
            value=primary_base_url,
            help="在线 OCR 和 LLM 评分使用的 API 端点",
            key="project_base_url",
        )
        with st.expander("备用 Base URL（可选）"):
            fallback_base_urls_input = st.text_area(
                "备用 Base URL 列表（用 ; 或 ； 分隔）",
                value="; ".join(model_cfg.get("fallback_base_urls", [])),
                key="project_fallback_base_urls",
                height=80,
            )

        primary_model = model_cfg.get("llm_model", defaults.DEFAULT_LLM_MODEL)
        if isinstance(primary_model, list):
            primary_model = primary_model[0] if primary_model else defaults.DEFAULT_LLM_MODEL
        llm_model_input = st.text_input(
            "LLM 模型",
            value=primary_model,
            help="用于简答题评分的模型 ID",
            key="project_llm_model",
        )
        with st.expander("备用 LLM 模型（可选）"):
            fallback_models_input = st.text_area(
                "备用模型列表（用 ; 或 ； 分隔，限流时自动降级）",
                value="; ".join(model_cfg.get("llm_models", [])),
                key="project_fallback_llm_models",
                height=80,
            )

        fallback_base_urls = _split_semicolon(fallback_base_urls_input)
        fallback_models = _split_semicolon(fallback_models_input)
        llm_base_url = _merge_primary_and_fallback(base_url_input, fallback_base_urls)
        llm_model = _merge_primary_and_fallback(llm_model_input, fallback_models)
        if st.button("保存模型配置", key="project_save_model_config"):
            save_json_config(
                model_config_path,
                {
                    "base_url": base_url_input,
                    "fallback_base_urls": fallback_base_urls,
                    "llm_model": llm_model_input,
                    "llm_models": fallback_models,
                    "ocr_engine": ocr_engine,
                    "ocr_model": online_ocr_model,
                    "ocr_max_tokens": model_cfg.get("ocr_max_tokens", 1024),
                    "ocr_prompt": model_cfg.get(
                        "ocr_prompt",
                        "请逐行识别图片中的所有文字内容，只输出文字，不要添加解释。",
                    ),
                },
            )
            st.success("模型配置已保存到当前项目")

        st.divider()
        st.header("LLM 评分设置")
        llm_enabled = st.checkbox(
            "启用 LLM 简答题评分",
            value=bool(api_key.strip() if isinstance(api_key, str) else api_key),
            key="project_llm_enabled",
        )

        if llm_enabled and not bool(api_key.strip() if isinstance(api_key, str) else api_key):
            st.warning("未配置 API Key，LLM 评分不会生效")

    return {
        "threshold": threshold,
        "llm_enabled": llm_enabled,
        "llm_api_key": api_key,
        "llm_base_url": llm_base_url,
        "llm_model": llm_model,
        "llm_max_tokens": model_cfg.get("llm_max_tokens", 256),
        "llm_temperature": model_cfg.get("llm_temperature", 0.3),
        "ocr_engine": ocr_engine,
        "ocr_api_config": {
            "api_key": ocr_key,
            "base_url": llm_base_url,
            "ocr_model": online_ocr_model if ocr_engine == "online" else "",
            "ocr_max_tokens": model_cfg.get("ocr_max_tokens", 1024),
            "ocr_prompt": model_cfg.get(
                "ocr_prompt",
                "请逐行识别图片中的所有文字内容，只输出文字，不要添加解释。",
            ),
        },
    }


def render_single_and_batch(session: ProjectSession) -> None:
    from exam_project.gui.views.single import render_single
    from exam_project.gui.views.batch import render_batch
    from exam_project.gui.views.components import project_paths_for_session

    try:
        paths = project_paths_for_session(session.project.workdir)
        controls = render_grading_controls(paths)
        baselines = _load_baseline_for_project(session.project)
    except Exception as exc:
        st.error(f"阅卷界面加载失败: {exc}")
        return

    layout = session.project.load_layout()
    ok, message = _layout_ready(layout)
    single_tab, batch_tab = st.tabs(["单套识别", "批量阅卷"])
    if not ok:
        with single_tab:
            st.warning(message)
            st.info("单套识别用于调试过程和课堂演示。请先完成答题卡设计并同步识别配置。")
        with batch_tab:
            st.warning(message)
            st.info("批量阅卷用于正式批处理。请先完成答题卡设计并同步识别配置。")
        return

    with single_tab:
        render_single(
            project=session.project, paths=paths,
            controls=controls, baseline=baselines,
        )
    with batch_tab:
        render_batch(
            project=session.project, paths=paths,
            controls=controls, baseline=baselines,
        )


def _load_baseline_for_project(project) -> dict:
    """从项目 baseline 资产加载（如果存在）。"""
    from exam_project.recognition.blank_calibrator import (
        get_choice_baseline_dict,
        get_choice_zone_bounds,
        get_judge_baseline_dict,
        get_judge_zone_bounds,
        load_baseline,
    )
    baseline_path = project.baseline_path
    if not baseline_path.is_file():
        return {}
    data = load_baseline(baseline_path)
    if not data:
        return {}
    return {
        "choice_baseline": get_choice_baseline_dict(data),
        "judge_baseline": get_judge_baseline_dict(data),
        "choice_zone_bounds": get_choice_zone_bounds(data),
        "judge_zone_bounds": get_judge_zone_bounds(data),
    }


def render_assets_tab(session: ProjectSession) -> None:
    st.subheader("项目资产")
    col1, col2, col3 = st.columns(3)
    col1.metric("项目名", session.manifest.name)
    col2.metric("学号位数", session.manifest.exam.get("student_id_digits", "-"))
    col3.metric("资产数", len(session.manifest.assets))

    st.caption(str(session.workdir))
    st.json(session.manifest.to_dict())

    with st.expander("布局 JSON", expanded=False):
        try:
            st.json(session.project.load_layout())
        except Exception as exc:
            show_project_error(exc)


def render_workspace(session: ProjectSession) -> None:
    render_project_sidebar(session)
    st.title(session.manifest.name)
    st.caption("项目工作区")

    designer_tab, calibration_tab, grading_tab, assets_tab = st.tabs(
        ["答题卡设计", "空白校对", "阅卷", "项目资产"]
    )
    with designer_tab:
        render_designer_tab(session)
    with calibration_tab:
        render_calibration_tab(session)
    with grading_tab:
        render_single_and_batch(session)
    with assets_tab:
        render_assets_tab(session)


st.set_page_config(page_title="Exam Project", layout="wide")

session = current_session()
if session is None:
    render_start_page()
else:
    render_workspace(session)
