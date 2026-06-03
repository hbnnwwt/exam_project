"""答题卡设计器视图。

UI 流程：
1. 配置元信息（标题、纸张、编号模式）
2. 配置页与 section（type / question_start / question_count / options / score）
3. 实时 HTML 预览
4. 同步到当前项目的 layout 资产
5. 另存为命名设计

完全基于 exam_project 自有的 answer_sheet 模块。
"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import streamlit as st

from exam_project.answer_sheet.config_exporter import export_sheet_layout
from exam_project.answer_sheet.html_renderer import render_html
from exam_project.answer_sheet.layout_engine import paginate
from exam_project.answer_sheet.schema import (
    AnswerSheetConfig,
    MetaConfig,
    PageConfig,
    SectionConfig,
    StudentIdConfig,
)


# 命名设计的存储目录（相对项目 workdir）
SAVED_DESIGNS_SUBDIR = "saved_designs"
AUTOSAVE_NAME = "_autosave.json"


# ============================================================================
# 持久化辅助
# ============================================================================


def _saved_designs_dir(project_workdir: Path) -> Path:
    """当前项目 workdir 下的命名设计目录。"""
    d = project_workdir / SAVED_DESIGNS_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _autosave_path(project_workdir: Path) -> Path:
    return _saved_designs_dir(project_workdir) / AUTOSAVE_NAME


def _design_path(project_workdir: Path, name: str) -> Path:
    safe = "".join(c for c in name if c.isalnum() or c in ("-", "_"))
    if not safe:
        safe = "design"
    return _saved_designs_dir(project_workdir) / f"{safe}.json"


def save_design(cfg: AnswerSheetConfig, project_workdir: Path, name: str) -> Path:
    """保存命名设计。"""
    path = _design_path(project_workdir, name)
    cfg.save(path)
    return path


def load_design(path: Path) -> Optional[AnswerSheetConfig]:
    if not path.is_file():
        return None
    try:
        return AnswerSheetConfig.load(path)
    except Exception:
        return None


def list_designs(project_workdir: Path) -> list[str]:
    """列出已保存的设计名（不含 _autosave）。"""
    d = _saved_designs_dir(project_workdir)
    names: list[str] = []
    for p in d.iterdir():
        if p.is_file() and p.suffix == ".json" and p.name != AUTOSAVE_NAME:
            names.append(p.stem)
    return sorted(names)


# ============================================================================
# 配置 → 项目 layout 同步
# ============================================================================


def sync_to_project_layout(cfg: AnswerSheetConfig, project) -> bool:
    """导出 sheet_layout.json 格式并写入项目的 layout 资产。

    Returns: True 成功，False 失败
    """
    try:
        layout_data = export_sheet_layout(cfg)
        # 写入项目 manifest 的 layout 资产
        layout_path = project.layout_path
        layout_path.parent.mkdir(parents=True, exist_ok=True)
        layout_path.write_text(
            json.dumps(layout_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except Exception:
        return False


# ============================================================================
# UI 部分
# ============================================================================


def _render_meta_editor(cfg: AnswerSheetConfig) -> MetaConfig:
    """元信息编辑器。返回更新后的 MetaConfig。"""
    st.markdown("#### 元信息")
    c1, c2, c3 = st.columns(3)
    with c1:
        title = st.text_input("标题", value=cfg.meta.title, key="designer_title")
    with c2:
        paper = st.selectbox(
            "纸张", ["A4", "B5"],
            index=0 if cfg.meta.paper_size == "A4" else 1,
            key="designer_paper",
        )
    with c3:
        numbering = st.selectbox(
            "编号模式", ["continuous", "per_section"],
            index=0 if cfg.meta.numbering_mode == "continuous" else 1,
            key="designer_numbering",
        )
    return MetaConfig(
        title=title, paper_size=paper, numbering_mode=numbering,
    )


def _render_student_id_editor(cfg: AnswerSheetConfig) -> StudentIdConfig:
    st.markdown("#### 学号配置")
    digit = st.number_input(
        "学号位数", min_value=6, max_value=14,
        value=cfg.student_id.digit_count,
        key="designer_digit",
    )
    return StudentIdConfig(digit_count=int(digit))


def _render_section_editor(
    section: SectionConfig,
    index: tuple[int, int],
) -> SectionConfig:
    """单个 section 编辑器。返回更新后的 SectionConfig。"""
    page_idx, sec_idx = index
    st.markdown(f"**第 {page_idx + 1} 页 / Section {sec_idx + 1}**")
    cols = st.columns(4)
    with cols[0]:
        sec_type = st.selectbox(
            "类型", ["choice", "judge", "essay", "solution", "student_id"],
            index=["choice", "judge", "essay", "solution", "student_id"].index(
                section.type if section.type in ["choice", "judge", "essay", "solution", "student_id"] else "choice"
            ),
            key=f"sec_type_{page_idx}_{sec_idx}",
        )
    with cols[1]:
        q_start = st.number_input(
            "起始题号", min_value=1,
            value=section.question_start,
            key=f"sec_qstart_{page_idx}_{sec_idx}",
        )
    with cols[2]:
        q_count = st.number_input(
            "题数", min_value=1,
            value=section.question_count,
            key=f"sec_qcount_{page_idx}_{sec_idx}",
        )
    with cols[3]:
        score = st.number_input(
            "每题分值", min_value=0.0,
            value=section.score or 0.0,
            key=f"sec_score_{page_idx}_{sec_idx}",
        )

    options: Optional[list[str]] = None
    if sec_type in ("choice", "judge"):
        opts_str = st.text_input(
            "选项（逗号分隔）",
            value=",".join(section.options or ["A", "B", "C", "D"]),
            key=f"sec_opts_{page_idx}_{sec_idx}",
        )
        options = [o.strip() for o in opts_str.split(",") if o.strip()]

    lines_per_question: Optional[int] = None
    if sec_type in ("essay", "solution"):
        lines_per_question = st.number_input(
            "每题行数", min_value=1,
            value=section.lines_per_question or 3,
            key=f"sec_lines_{page_idx}_{sec_idx}",
        )

    digit_count: Optional[int] = None
    if sec_type == "student_id":
        digit_count = int(q_count) if q_count else None

    return SectionConfig(
        type=sec_type,
        question_start=int(q_start) if sec_type != "student_id" else 0,
        question_count=int(q_count) if sec_type != "student_id" else 0,
        options=options,
        score=float(score) if sec_type != "student_id" else None,
        lines_per_question=lines_per_question,
        digit_count=digit_count,
    )


def _render_pages_editor(cfg: AnswerSheetConfig) -> list[PageConfig]:
    """页与 section 编辑器。"""
    st.markdown("#### 页面与 Section")
    pages: list[PageConfig] = []
    for page_idx, page in enumerate(cfg.pages):
        with st.expander(f"第 {page_idx + 1} 页", expanded=True):
            new_sections: list[SectionConfig] = []
            for sec_idx, sec in enumerate(page.sections):
                new_sections.append(_render_section_editor(sec, (page_idx, sec_idx)))
            c1, c2, c3 = st.columns(3)
            if c1.button("删除此页", key=f"del_page_{page_idx}"):
                continue
            if c2.button("新增 Section", key=f"add_sec_{page_idx}"):
                new_sections.append(SectionConfig(
                    type="choice", question_start=1, question_count=5,
                    options=["A", "B", "C", "D"], score=3,
                ))
            pages.append(PageConfig(sections=new_sections, title=page.title))

    if st.button("新增一页"):
        pages.append(PageConfig(sections=[
            SectionConfig(
                type="choice", question_start=1, question_count=10,
                options=["A", "B", "C", "D"], score=3,
            ),
        ]))
    return pages


def _collect_config(current: AnswerSheetConfig) -> AnswerSheetConfig:
    """从 session_state / 编辑器收集新配置。"""
    try:
        return AnswerSheetConfig(
            meta=st.session_state.get("designer_meta", current.meta),
            student_id=st.session_state.get("designer_sid", current.student_id),
            pages=st.session_state.get("designer_pages", current.pages),
        )
    except Exception:
        return current


def render_designer(project, legacy_root=None) -> None:
    """答题卡设计器主入口。"""
    st.markdown("### 答题卡设计器")
    st.info("设计完成后点击 **同步到项目**，设计会写入项目的 layout 资产；"
            "点击 **另存为设计**可保存到命名设计库。")

    # 初始化：尝试从项目 layout 资产加载
    if "designer_cfg" not in st.session_state:
        initial_cfg = _load_initial_cfg(project)
        st.session_state["designer_cfg"] = initial_cfg
    cfg: AnswerSheetConfig = st.session_state["designer_cfg"]

    # 编辑器
    new_meta = _render_meta_editor(cfg)
    new_sid = _render_student_id_editor(cfg)
    new_pages = _render_pages_editor(cfg)
    new_cfg = AnswerSheetConfig(meta=new_meta, student_id=new_sid, pages=new_pages)

    # 验证
    err = new_cfg.validate()
    if err is not None:
        st.error(f"配置无效: {err}")
    else:
        st.success("配置有效")

    # 预览
    with st.expander("HTML 预览", expanded=False):
        try:
            pages = paginate(new_cfg)
            html = render_html(new_cfg, pages)
            st.components.v1.html(html, height=400, scrolling=True)
        except Exception as exc:
            st.warning(f"预览失败: {exc}")

    # 操作按钮
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if st.button("同步到项目", type="primary"):
            if sync_to_project_layout(new_cfg, project):
                st.success("已写入项目 layout 资产。")
            else:
                st.error("同步失败。")
    with c2:
        name = st.text_input("设计名", value="", key="designer_save_name")
        if st.button("另存为设计"):
            if not name.strip():
                st.warning("请先填写设计名。")
            else:
                path = save_design(new_cfg, project.workdir, name)
                st.success(f"已保存到 {path}")
    with c3:
        designs = list_designs(project.workdir)
        if designs:
            chosen = st.selectbox("加载已保存设计", ["（选择）"] + designs, key="designer_load")
            if chosen != "（选择）" and st.button("加载"):
                loaded = load_design(_design_path(project.workdir, chosen))
                if loaded is not None:
                    st.session_state["designer_cfg"] = loaded
                    st.rerun()
                else:
                    st.error("加载失败。")
    with c4:
        st.write("")  # 占位


def _load_initial_cfg(project) -> AnswerSheetConfig:
    """从项目 layout 资产加载初始配置；缺失则返回默认。"""
    layout_path = project.layout_path
    if not layout_path.is_file():
        return _default_cfg()
    try:
        data = json.loads(layout_path.read_text(encoding="utf-8"))
    except Exception:
        return _default_cfg()

    # 从 layout 字典反向构造 SectionConfig（最小可用）
    pages_config = data.get("_pages")
    if not pages_config:
        return _default_cfg()

    pages: list[PageConfig] = []
    for page_spec in pages_config:
        if not isinstance(page_spec, dict):
            continue
        sections: list[SectionConfig] = []
        for sec in page_spec.get("sections", []):
            if not isinstance(sec, dict):
                continue
            sec_type = sec.get("type", "choice")
            if sec_type == "student_id":
                sections.append(SectionConfig(
                    type="student_id", question_start=0, question_count=0,
                    digit_count=sec.get("digit_count", 10),
                ))
            else:
                options = sec.get("options")
                if sec_type == "judge" and options != ["T", "F"]:
                    options = ["T", "F"]
                sections.append(SectionConfig(
                    type=sec_type,
                    question_start=sec.get("question_start", 1),
                    question_count=sec.get("question_count", 5),
                    options=options,
                    score=3.0,
                    lines_per_question=sec.get("lines_per_question", 3) if sec_type in ("essay", "solution") else None,
                ))
        pages.append(PageConfig(sections=sections))
    if not pages:
        return _default_cfg()
    return AnswerSheetConfig(
        meta=MetaConfig(
            title=data.get("title", "标准化考试答题卡"),
            paper_size="A4",
            numbering_mode="continuous",
        ),
        student_id=StudentIdConfig(digit_count=10),
        pages=pages,
    )


def _default_cfg() -> AnswerSheetConfig:
    """默认空白配置。"""
    return AnswerSheetConfig(
        meta=MetaConfig(),
        student_id=StudentIdConfig(),
        pages=[PageConfig(sections=[
            SectionConfig(
                type="choice", question_start=1, question_count=20,
                options=["A", "B", "C", "D"], score=3,
            ),
            SectionConfig(
                type="judge", question_start=21, question_count=10,
                options=["T", "F"], score=2,
            ),
        ])],
    )
