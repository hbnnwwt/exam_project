"""答题卡设计器视图 —— 配置编辑 + 实时预览。"""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
import streamlit.components.v1 as components

from exam_project.answer_sheet.schema import (
    AnswerSheetConfig,
    MetaConfig,
    PageConfig,
    SectionConfig,
    StudentIdConfig,
)
from exam_project.answer_sheet.html_renderer import generate
from exam_project.answer_sheet.config_exporter import export_sheet_layout


@st.cache_data(show_spinner=False)
def _cached_generate(cfg_json: str) -> str:
    """缓存 HTML 生成结果，避免每次 rerender 都重新计算。"""
    cfg_dict = json.loads(cfg_json)
    cfg = AnswerSheetConfig.from_dict(cfg_dict)
    return generate(cfg)


# ── Layout sync helper ─────────────────────────────────────────────


def _sync_layout_config(cfg: AnswerSheetConfig, project) -> bool:
    """将配置自动同步为 sheet_layout.json，返回是否成功。"""
    try:
        layout = export_sheet_layout(cfg)
        layout_path = project.layout_path
        layout_path.parent.mkdir(parents=True, exist_ok=True)
        layout_path.write_text(
            json.dumps(layout, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except Exception:
        return False


# ── Persistence helpers ────────────────────────────────────────────


def _saved_designs_dir(project) -> Path:
    d = project.workdir / "saved_designs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _autosave_path(project) -> Path:
    return _saved_designs_dir(project) / "_autosave.json"


def _design_path(project, name: str) -> Path:
    safe = "".join(c for c in name if c.isalnum() or c in ("-", "_"))
    if not safe:
        safe = "design"
    return _saved_designs_dir(project) / f"{safe}.json"


def save_design(name: str, cfg_dict: dict, project) -> None:
    """保存配置到文件。"""
    path = _design_path(project, name)
    path.write_text(
        json.dumps(cfg_dict, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_design(name: str, project) -> Optional[dict]:
    """从文件加载配置。"""
    path = _design_path(project, name)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_designs(project) -> List[tuple]:
    """返回所有已保存配置的名称和修改时间。"""
    d = _saved_designs_dir(project)
    designs = []
    autosave_name = _autosave_path(project).name
    for p in d.iterdir():
        if p.is_file() and p.suffix == ".json" and p.name != autosave_name and not p.name.startswith("_autosave."):
            mtime = p.stat().st_mtime
            dt = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            designs.append((p.stem, dt))
    # 按修改时间倒序
    designs.sort(key=lambda x: x[1], reverse=True)
    return designs


def delete_design(name: str, project) -> None:
    """删除配置。"""
    path = _design_path(project, name)
    if path.is_file():
        path.unlink()


def _autosave(cfg_dict: dict, project) -> None:
    """静默保存当前配置到 _autosave.json，用于刷新恢复。"""
    try:
        _saved_designs_dir(project)
        _autosave_path(project).write_text(
            json.dumps(cfg_dict, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass  # autosave 失败不应中断用户操作


def _persist_design_asset(cfg_dict: dict, project) -> None:
    """将当前配置保存为项目设计资产 (design/answer_sheet.json)。"""
    try:
        path = project.design_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(cfg_dict, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass  # 静默失败，不中断用户操作


def _load_autosave(project) -> Optional[dict]:
    """尝试从 _autosave.json 恢复配置。"""
    path = _autosave_path(project)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_saved_design_config(name: str, project) -> dict:
    """加载用户命名保存的配置，归一化、校验，并覆盖 autosave。"""
    loaded = load_design(name, project)
    if loaded is None:
        raise FileNotFoundError(f"未找到配置：{name}")

    normalized = _normalize_designer_config(loaded)
    AnswerSheetConfig.from_dict(normalized)
    _autosave(normalized, project)
    return normalized


# ── Constants ──────────────────────────────────────────────────────
_TYPE_LABELS = {
    "student_id": "准考证号",
    "choice": "单选",
    "judge": "判断",
    "essay": "简答",
    "solution": "解答",
}
_TYPE_OPTIONS = ["student_id", "choice", "judge", "essay", "solution"]
_DEFAULT_OPTIONS = {
    "choice": ["A", "B", "C", "D"],
    "judge": ["T", "F"],
    "essay": [],
    "solution": [],
}
_DESIGNER_COLUMN_WEIGHTS = [2, 3]
_TEMPLATE_COLUMNS_PER_ROW = 2
_AUTO_SYNC_DEFAULT = False
_CONFIG_REVISION_KEY = "designer_config_revision"
_DIRTY_SYNC_KEY = "designer_recognition_config_dirty"
_PROTECTED_DESIGNER_STATE_KEYS = {"designer_config", _CONFIG_REVISION_KEY, _DIRTY_SYNC_KEY}
_META_KEYS = {"title", "paper_size", "numbering_mode"}
_STUDENT_ID_KEYS = {"digit_count"}
_SECTION_KEYS = {
    "type",
    "question_start",
    "question_count",
    "title",
    "options",
    "score",
    "scores",
    "lines_per_question",
    "digit_count",
    "instruction",
    "before_gap_mm",
}

_DEFAULT_CONFIG = AnswerSheetConfig(
    meta=MetaConfig(title="标准化考试答题卡", paper_size="A4"),
    student_id=StudentIdConfig(digit_count=10),
    pages=[
        PageConfig(sections=[
            SectionConfig(type="student_id", question_start=0, question_count=0, digit_count=10),
            SectionConfig(
                type="choice",
                question_start=1,
                question_count=20,
                options=["A", "B", "C", "D"],
                score=3,
            ),
        ]),
    ],
)


# ── Quick templates ────────────────────────────────────────────────
_QUICK_TEMPLATES: dict[str, AnswerSheetConfig] = {
    "期中考试": AnswerSheetConfig(
        meta=MetaConfig(title="期中考试答题卡", paper_size="A4"),
        student_id=StudentIdConfig(digit_count=10),
        pages=[
            PageConfig(sections=[
                SectionConfig(type="student_id", question_start=0, question_count=0, digit_count=10),
                SectionConfig(type="choice", question_start=1, question_count=20,
                              options=["A", "B", "C", "D"], score=3),
            ]),
            PageConfig(sections=[
                SectionConfig(type="judge", question_start=21, question_count=10,
                              options=["T", "F"], score=2),
                SectionConfig(type="essay", question_start=31, question_count=2,
                              lines_per_question=8, score=10),
            ]),
        ],
    ),
    "期末考试": AnswerSheetConfig(
        meta=MetaConfig(title="期末考试答题卡", paper_size="A4"),
        student_id=StudentIdConfig(digit_count=10),
        pages=[
            PageConfig(sections=[
                SectionConfig(type="student_id", question_start=0, question_count=0, digit_count=10),
                SectionConfig(type="choice", question_start=1, question_count=30,
                              options=["A", "B", "C", "D"], score=2),
            ]),
            PageConfig(sections=[
                SectionConfig(type="judge", question_start=31, question_count=10,
                              options=["T", "F"], score=1),
                SectionConfig(type="essay", question_start=41, question_count=3,
                              lines_per_question=10, score=10),
            ]),
        ],
    ),
    "小测验": AnswerSheetConfig(
        meta=MetaConfig(title="课堂小测验答题卡", paper_size="A4"),
        student_id=StudentIdConfig(digit_count=10),
        pages=[
            PageConfig(sections=[
                SectionConfig(type="student_id", question_start=0, question_count=0, digit_count=10),
                SectionConfig(type="choice", question_start=1, question_count=10,
                              options=["A", "B", "C", "D"], score=2),
                SectionConfig(type="judge", question_start=11, question_count=5,
                              options=["T", "F"], score=1),
            ]),
        ],
    ),
    "模拟考试": AnswerSheetConfig(
        meta=MetaConfig(title="模拟考试答题卡", paper_size="A4"),
        student_id=StudentIdConfig(digit_count=10),
        pages=[
            PageConfig(sections=[
                SectionConfig(type="student_id", question_start=0, question_count=0, digit_count=10),
                SectionConfig(type="choice", question_start=1, question_count=25,
                              options=["A", "B", "C", "D"], score=2),
            ]),
            PageConfig(sections=[
                SectionConfig(type="judge", question_start=26, question_count=5,
                              options=["T", "F"], score=2),
                SectionConfig(type="essay", question_start=31, question_count=2,
                              lines_per_question=12, score=15),
            ]),
        ],
    ),
    "仅选择题": AnswerSheetConfig(
        meta=MetaConfig(title="选择题答题卡", paper_size="A4"),
        student_id=StudentIdConfig(digit_count=10),
        pages=[
            PageConfig(sections=[
                SectionConfig(type="student_id", question_start=0, question_count=0, digit_count=10),
                SectionConfig(type="choice", question_start=1, question_count=50,
                              options=["A", "B", "C", "D"], score=2),
            ]),
        ],
    ),
}


def _chunked(items: List[Any], chunk_size: int) -> List[List[Any]]:
    """把一维列表切成固定长度的小组，用于避免窄栏中硬塞太多按钮。"""
    if chunk_size < 1:
        raise ValueError("chunk_size 必须 >= 1")
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def _preview_iframe_height(actual_pages: int) -> int:
    """返回设计器预览 iframe 高度。

    单页给足接近 A4 的可视空间；多页允许更高，但封顶，避免页面失控。
    """
    pages = max(1, int(actual_pages))
    return min(1200, max(900, pages * 600))


def _render_preview_html(html_content: str, actual_pages: int) -> None:
    components.html(
        html_content,
        height=_preview_iframe_height(actual_pages),
        scrolling=True,
    )


def _template_summary(cfg: AnswerSheetConfig) -> dict:
    """生成模板摘要。"""
    total_q = sum(s.question_count for p in cfg.pages for s in p.sections)
    total_s = 0.0
    for p in cfg.pages:
        for s in p.sections:
            total_s += (sum(s.scores) if s.scores else (s.score or 0) * s.question_count)
    desc_parts = []
    for p in cfg.pages:
        for s in p.sections:
            label = _TYPE_LABELS.get(s.type, s.type)
            if s.type == "student_id":
                desc_parts.append(label)
            else:
                desc_parts.append(label + f"{s.question_count}题")
    desc = " / ".join(desc_parts)
    return {"pages": len(cfg.pages), "questions": total_q, "score": total_s, "desc": desc}


# ── Session-state helpers ──────────────────────────────────────────
def _get_config(project) -> AnswerSheetConfig:
    """从 session_state 读取当前配置，首次加载用默认值。"""
    if "designer_config" not in st.session_state:
        st.session_state.designer_config = _dict_from_config(_DEFAULT_CONFIG)
    return _config_from_dict(st.session_state.designer_config)


def _set_config(cfg: AnswerSheetConfig) -> None:
    st.session_state.designer_config = _dict_from_config(cfg)


def _config_from_dict(d: dict) -> AnswerSheetConfig:
    return AnswerSheetConfig.from_dict(d)


def _dict_from_config(cfg: AnswerSheetConfig) -> dict:
    return cfg.to_dict()


def _normalize_designer_config(cfg_dict: dict) -> dict:
    """设计器只维护题型流，实际分页统一交给 paginate()。"""
    normalized = copy.deepcopy(cfg_dict)
    normalized["meta"] = {
        k: v for k, v in normalized.get("meta", {}).items() if k in _META_KEYS
    }
    normalized["student_id"] = {
        k: v
        for k, v in normalized.get("student_id", {}).items()
        if k in _STUDENT_ID_KEYS
    }

    all_sections: List[dict] = []
    for page in normalized.get("pages", []):
        for sec in page.get("sections", []):
            all_sections.append({
                k: v for k, v in copy.deepcopy(sec).items() if k in _SECTION_KEYS
            })

    if not all_sections:
        all_sections = [{
            "type": "choice",
            "question_start": 1,
            "question_count": 5,
            "options": ["A", "B", "C", "D"],
            "score": 2,
        }]

    normalized["pages"] = [{"sections": all_sections}]
    _recompute_starts(normalized)
    return normalized


# ── Helpers ────────────────────────────────────────────────────────
def _clear_designer_widget_state() -> None:
    """清除所有设计器 widget 的 session_state，使新配置能正确生效。"""
    for key in list(st.session_state.keys()):
        if key.startswith("designer_") and key not in _PROTECTED_DESIGNER_STATE_KEYS:
            del st.session_state[key]


def _bump_designer_config_revision() -> int:
    """递增配置版本号，让配置驱动的 widget key 不复用旧配置状态。"""
    revision = int(st.session_state.get(_CONFIG_REVISION_KEY, 0)) + 1
    st.session_state[_CONFIG_REVISION_KEY] = revision
    return revision


def _section_key_prefix(page_idx: int, sec_idx: int, config_revision: int) -> str:
    return f"designer_r{config_revision}_p{page_idx}_s{sec_idx}"


def _recompute_starts(cfg_dict: dict) -> None:
    """根据编号模式重新计算所有起始题号。"""
    mode = cfg_dict.get("meta", {}).get("numbering_mode", "continuous")
    if mode == "continuous":
        next_start = 1
        for page in cfg_dict.get("pages", []):
            for sec in page.get("sections", []):
                if sec.get("type") == "student_id":
                    sec["question_start"] = 0
                    sec["question_count"] = 0
                    continue
                sec["question_start"] = next_start
                next_start = sec["question_start"] + sec.get("question_count", 1)
    else:  # per_section
        for page in cfg_dict.get("pages", []):
            for sec in page.get("sections", []):
                if sec.get("type") == "student_id":
                    sec["question_start"] = 0
                    sec["question_count"] = 0
                    continue
                sec["question_start"] = 1


# ── Section editor widget ──────────────────────────────────────────
def _edit_section(
    sec_dict: dict,
    page_idx: int,
    sec_idx: int,
    numbering_mode: str = "continuous",
    config_revision: int = 0,
) -> dict:
    """渲染单个 section 的编辑表单，返回修改后的字典。"""
    key_prefix = _section_key_prefix(page_idx, sec_idx, config_revision)

    old_type = sec_dict.get("type", "choice")
    sec_type = st.selectbox(
        "题型",
        options=_TYPE_OPTIONS,
        format_func=lambda x: _TYPE_LABELS.get(x, x),
        index=_TYPE_OPTIONS.index(old_type),
        key=f"{key_prefix}_type",
    )
    sec_dict["type"] = sec_type

    # 类型切换时：清除该 section 所有下游 widget key，让 widget 从 value 参数重新读取
    if sec_type != old_type:
        type_key = f"{key_prefix}_type"
        for k in list(st.session_state.keys()):
            if k.startswith(key_prefix) and k != type_key:
                del st.session_state[k]
        # 重置类型相关字段为默认值
        if sec_type in ("choice", "judge"):
            sec_dict["options"] = list(_DEFAULT_OPTIONS[sec_type])
        else:
            sec_dict.pop("options", None)
        if sec_type in ("essay", "solution"):
            sec_dict["lines_per_question"] = 10
        else:
            sec_dict.pop("lines_per_question", None)
        if sec_type == "student_id":
            sec_dict["question_start"] = 0
            sec_dict["question_count"] = 0
            sec_dict["digit_count"] = 10
            sec_dict.pop("score", None)
            sec_dict.pop("scores", None)
            sec_dict.pop("instruction", None)
        else:
            sec_dict.pop("digit_count", None)

    sec_dict["before_gap_mm"] = st.number_input(
        "题前间距（mm）",
        min_value=0.0,
        max_value=30.0,
        value=float(sec_dict.get("before_gap_mm", 0.0) or 0.0),
        step=0.5,
        key=f"{key_prefix}_before_gap_mm",
        help="在该题型模块之前额外留出的空白距离，用于微调分页和版面。",
    )

    if sec_type == "student_id":
        sec_dict["question_start"] = 0
        sec_dict["question_count"] = 0
        sec_dict["digit_count"] = st.number_input(
            "准考证号位数",
            min_value=6,
            max_value=14,
            value=int(sec_dict.get("digit_count", 10)),
            step=1,
            key=f"{key_prefix}_digit_count",
        )
        sec_dict.pop("title", None)
        sec_dict.pop("options", None)
        sec_dict.pop("score", None)
        sec_dict.pop("scores", None)
        sec_dict.pop("lines_per_question", None)
        sec_dict.pop("instruction", None)
        return sec_dict

    # Custom title (optional)
    custom_title = st.text_input(
        "题型标题（可选，留空用默认）",
        value=sec_dict.get("title", ""),
        key=f"{key_prefix}_title",
    )
    if custom_title.strip():
        sec_dict["title"] = custom_title.strip()
    else:
        sec_dict.pop("title", None)

    # 题型说明（None=默认；非空=覆盖；需要隐藏请手动改 JSON 设为空字符串）
    custom_instruction = st.text_input(
        "题型说明（留空用默认；输入「NONE」彻底隐藏）",
        value="" if sec_dict.get("instruction") is None else sec_dict.get("instruction", ""),
        key=f"{key_prefix}_instruction",
        help="默认文本已按题型内置（选择题=请将正确答案涂黑 等）。留空使用默认；填入文本覆盖；如需不显示说明，在保存的 JSON 里把该字段设为空字符串。",
    )
    stripped = custom_instruction.strip()
    if not stripped:
        sec_dict.pop("instruction", None)
    elif stripped == "NONE":
        sec_dict["instruction"] = ""
    else:
        sec_dict["instruction"] = stripped

    c1, c2 = st.columns(2)
    with c1:
        # 两种模式下起始题号均由系统决定，用户无需手动设置
        label = "自动" if numbering_mode == "continuous" else "固定为1"
        st.markdown(
            f"**起始题号：{int(sec_dict.get('question_start', 1))}**（{label}）"
        )
    with c2:
        sec_dict["question_count"] = st.number_input(
            "题目数量",
            min_value=1,
            value=int(sec_dict.get("question_count", 1)),
            step=1,
            key=f"{key_prefix}_count",
        )

    # Options (choice / judge)
    if sec_type in ("choice", "judge"):
        current_opts = sec_dict.get("options") or _DEFAULT_OPTIONS[sec_type]
        opts_str = st.text_input(
            "选项（用逗号分隔）",
            value=", ".join(current_opts),
            key=f"{key_prefix}_opts",
        )
        sec_dict["options"] = [o.strip() for o in opts_str.split(",") if o.strip()]
    else:
        sec_dict.pop("options", None)

    # Lines per question (written answer types)
    if sec_type in ("essay", "solution"):
        sec_dict["lines_per_question"] = st.number_input(
            "每题行数",
            min_value=1,
            value=int(sec_dict.get("lines_per_question", 10)),
            step=1,
            key=f"{key_prefix}_lines",
        )
    else:
        sec_dict.pop("lines_per_question", None)

    # 旧配置里可能残留 gap 字段（leading_gap/trailing_gap/margin_top/margin_bottom）。
    # 新设计不再使用这些字段，由 CSS 控制间距。
    for k in ("leading_gap", "trailing_gap", "margin_top", "margin_bottom"):
        sec_dict.pop(k, None)

    # Score
    use_individual_scores = st.checkbox(
        "逐题赋分（高级）",
        value="scores" in sec_dict,
        key=f"{key_prefix}_use_scores",
    )
    if use_individual_scores:
        count = int(sec_dict.get("question_count", 1))
        current_scores = sec_dict.get("scores")
        if current_scores is None or len(current_scores) != count:
            base_score = sec_dict.get("score", 1)
            current_scores = [base_score] * count
        scores_str = st.text_input(
            "各题分值（逗号分隔）",
            value=", ".join(str(s) for s in current_scores),
            key=f"{key_prefix}_scores",
        )
        try:
            parsed = [float(s.strip()) for s in scores_str.split(",") if s.strip()]
            if len(parsed) == count:
                sec_dict["scores"] = parsed
                sec_dict.pop("score", None)
            else:
                st.warning(f"分值数量应为 {count}，当前为 {len(parsed)}")
        except ValueError:
            st.warning("分值必须为数字")
    else:
        sec_dict["score"] = st.number_input(
            "每题分值",
            min_value=0.0,
            value=float(sec_dict.get("score", 1)),
            step=0.5,
            key=f"{key_prefix}_score",
        )
        sec_dict.pop("scores", None)

    return sec_dict


def _section_summary(sec_dict: dict) -> str:
    """生成 section 的摘要文本。"""
    t = sec_dict.get("type", "choice")
    try:
        before_gap = float(sec_dict.get("before_gap_mm", 0.0) or 0.0)
    except (TypeError, ValueError):
        before_gap = 0.0
    gap_suffix = f" · 前距{before_gap:g}mm" if before_gap else ""
    if t == "student_id":
        return f"{_TYPE_LABELS.get(t, t)}（{int(sec_dict.get('digit_count', 10))}位）{gap_suffix}"
    start = sec_dict.get("question_start", 1)
    count = sec_dict.get("question_count", 1)
    label = _TYPE_LABELS.get(t, t)
    end = start + count - 1
    return f"{label}  {start}-{end}题（共{count}题）{gap_suffix}"


def _config_summary(cfg_dict: dict) -> tuple[int, int, float, int]:
    """计算配置摘要：配置页数、总题数、预估总分、实际分页数。"""
    pages = cfg_dict.get("pages", [])
    total_questions = 0
    total_score = 0.0
    for page in pages:
        for sec in page.get("sections", []):
            if sec.get("type") == "student_id":
                continue
            count = sec.get("question_count", 0)
            total_questions += count
            scores = sec.get("scores")
            if scores is not None:
                total_score += sum(scores)
            else:
                total_score += sec.get("score", 0) * count

    # 计算实际分页数（考虑间距配置）
    actual_pages = len(pages)
    try:
        from exam_project.answer_sheet.layout_engine import paginate
        _tmp_cfg = AnswerSheetConfig.from_dict(cfg_dict)
        _paginated = paginate(_tmp_cfg)
        actual_pages = len(_paginated)
    except Exception:
        pass

    return len(pages), total_questions, total_score, actual_pages


# ── Validation ─────────────────────────────────────────────────────
def _validate_config(cfg_dict: dict) -> Optional[str]:
    """尝试从字典构造配置并验证业务规则，返回错误信息或 None。"""
    try:
        cfg = AnswerSheetConfig.from_dict(cfg_dict)
        return cfg.validate()
    except ValueError as e:
        return str(e)
    except Exception as e:
        return f"配置错误: {e}"


# ── Export helpers ─────────────────────────────────────────────────
def _export_json(cfg: AnswerSheetConfig) -> str:
    return json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2)


def _export_sheet_layout_json(cfg: AnswerSheetConfig) -> str:
    layout = export_sheet_layout(cfg)
    return json.dumps(layout, ensure_ascii=False, indent=2)


# ── Main render function ───────────────────────────────────────────
def render_designer(project, legacy_root=None) -> None:
    st.subheader("答题卡设计器")
    st.caption("配置答题卡结构，实时预览并导出")

    cfg_dict = st.session_state.get("designer_config")
    if cfg_dict is None:
        # 优先从 autosave 恢复，否则用默认配置
        cfg_dict = _load_autosave(project) or _dict_from_config(_DEFAULT_CONFIG)
    else:
        # 深拷贝避免修改 session_state 中的原始对象
        cfg_dict = copy.deepcopy(cfg_dict)
    cfg_dict = _normalize_designer_config(cfg_dict)
    st.session_state.designer_config = cfg_dict
    config_revision = int(st.session_state.get(_CONFIG_REVISION_KEY, 0))

    # 配置摘要
    total_pages, total_questions, total_score, actual_pages = _config_summary(cfg_dict)
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.metric("总题数", f"{total_questions} 题")
    with s2:
        st.metric("预估总分", f"{total_score:.1f} 分")
    with s3:
        st.metric("实际分页", f"{actual_pages} 页")
    with s4:
        paper_size = cfg_dict.get("meta", {}).get("paper_size", "A4")
        st.metric("纸张尺寸", paper_size)

    st.divider()

    left_col, right_col = st.columns(_DESIGNER_COLUMN_WEIGHTS)

    # ═══════════════════════════════════════════════════════════════
    # Left column: config editor
    # ═══════════════════════════════════════════════════════════════
    with left_col:
        st.markdown("#### 基本信息")
        meta = cfg_dict.get("meta", {})
        meta["title"] = st.text_input(
            "答题卡标题",
            value=meta.get("title", "标准化考试答题卡"),
            key=f"designer_r{config_revision}_title",
        )
        meta["paper_size"] = st.selectbox(
            "纸张尺寸",
            options=["A4", "B5"],
            index=["A4", "B5"].index(meta.get("paper_size", "A4")),
            key=f"designer_r{config_revision}_paper_size",
        )
        numbering_mode_options = {
            "continuous": "全局连续编号（默认）",
            "per_section": "每道大题独立编号",
        }
        current_mode = meta.get("numbering_mode", "continuous")
        if current_mode not in numbering_mode_options:
            current_mode = "continuous"
        meta["numbering_mode"] = st.selectbox(
            "题号编号方式",
            options=list(numbering_mode_options.keys()),
            format_func=lambda x: numbering_mode_options[x],
            index=list(numbering_mode_options.keys()).index(current_mode),
            key=f"designer_r{config_revision}_numbering_mode",
        )
        cfg_dict["meta"] = meta

        cfg_dict["meta"] = meta

        st.divider()
        st.markdown("#### 题型配置")

        pages: List[dict] = cfg_dict.get("pages", [])
        if not pages:
            pages = [{"sections": []}]
            cfg_dict["pages"] = pages

        # 所有 sections 放在第一页，由分页引擎自动排布
        page_dict = pages[0]
        sections: List[dict] = page_dict.get("sections", [])
        if not sections:
            # 确保至少有一个默认 section，避免解析失败
            sections.append({
                "type": "choice",
                "question_start": 1,
                "question_count": 5,
                "options": ["A", "B", "C", "D"],
                "score": 2,
            })
            page_dict["sections"] = sections
        numbering_mode = meta.get("numbering_mode", "continuous")

        for sec_idx, sec_dict in enumerate(sections):
            expander_label = _section_summary(sec_dict)
            with st.expander(expander_label, expanded=False):
                sections[sec_idx] = _edit_section(
                    sec_dict, 0, sec_idx, numbering_mode, config_revision
                )
                col_del, _ = st.columns([1, 4])
                with col_del:
                    if st.button(
                        "删除此题型",
                        key=f"del_sec_{sec_idx}",
                        type="secondary",
                    ):
                        sections.pop(sec_idx)
                        page_dict["sections"] = sections
                        st.rerun()

        page_dict["sections"] = sections

        if st.button("添加题型", key="add_sec", type="secondary"):
            if numbering_mode == "continuous":
                next_start = 1
                for s in sections:
                    if s.get("type") == "student_id":
                        continue
                    s_end = s.get("question_start", 1) + s.get("question_count", 1) - 1
                    if s_end >= next_start:
                        next_start = s_end + 1
            else:
                next_start = 1
            sections.append({
                "type": "choice",
                "question_start": next_start,
                "question_count": 5,
                "options": ["A", "B", "C", "D"],
                "score": 2,
            })
            page_dict["sections"] = sections
            st.rerun()

        cfg_dict["pages"] = pages
        _recompute_starts(cfg_dict)

        st.divider()
        st.markdown("#### 快速模板")
        template_items = list(_QUICK_TEMPLATES.items())
        for row_idx, row_items in enumerate(_chunked(template_items, _TEMPLATE_COLUMNS_PER_ROW)):
            tpl_cols = st.columns(len(row_items))
            for col, (name, tpl_cfg) in zip(tpl_cols, row_items):
                with col:
                    summary = _template_summary(tpl_cfg)
                    st.caption(f"{summary['desc']}")
                    st.caption(f"{summary['pages']}页 · {summary['questions']}题 · {summary['score']:.0f}分")
                    if st.button(name, key=f"quick_tpl_{row_idx}_{name}", type="secondary"):
                        _clear_designer_widget_state()
                        cfg_dict = _normalize_designer_config(tpl_cfg.to_dict())
                        st.session_state["designer_config"] = cfg_dict
                        st.session_state[_DIRTY_SYNC_KEY] = True
                        _bump_designer_config_revision()
                        _autosave(cfg_dict, project)
                        st.toast(f"已加载模板：{name}")
                        st.rerun()
                        return

        st.divider()
        st.markdown("#### 配置管理")

        # ── Import from file ──
        uploaded = st.file_uploader("导入配置 (JSON)", type=["json"], key="designer_import")
        if uploaded is not None:
            try:
                imported = json.loads(uploaded.read().decode("utf-8"))
                # Validate by trying to construct the config
                _ = AnswerSheetConfig.from_dict(imported)
                cfg_dict = _normalize_designer_config(imported)
                AnswerSheetConfig.from_dict(cfg_dict)
                _clear_designer_widget_state()
                st.session_state.designer_config = cfg_dict
                st.session_state[_DIRTY_SYNC_KEY] = True
                _bump_designer_config_revision()
                _autosave(cfg_dict, project)
                st.success(f"已导入：{uploaded.name}")
                st.rerun()
                return
            except Exception as e:
                st.error(f"导入失败：{e}")

        # ── Save current design ──
        save_col1, save_col2 = st.columns([3, 1])
        with save_col1:
            save_name = st.text_input(
                "保存当前配置",
                placeholder="输入配置名称",
                key="designer_save_name",
            )
        with save_col2:
            st.write("")
            st.write("")
            if st.button("保存", type="primary", key="designer_save_btn"):
                if save_name.strip():
                    save_design(save_name.strip(), cfg_dict, project)
                    st.success(f"已保存：{save_name.strip()}")
                else:
                    st.warning("请输入配置名称")

        # ── Load saved design ──
        designs = list_designs(project)
        if designs:
            st.markdown("**已保存的配置**")
            for dname, dtime in designs:
                c1, c2, c3 = st.columns([3, 1, 1])
                with c1:
                    st.caption(f"{dname}  ·  {dtime}")
                with c2:
                    if st.button("加载", key=f"load_{dname}"):
                        try:
                            loaded = _load_saved_design_config(dname, project)
                            _clear_designer_widget_state()
                            cfg_dict = loaded
                            st.session_state.designer_config = cfg_dict
                            st.session_state[_DIRTY_SYNC_KEY] = True
                            _bump_designer_config_revision()
                            _autosave(cfg_dict, project)
                            st.toast(f"已加载：{dname}，请同步识别配置")
                            st.rerun()
                            return
                        except Exception as e:
                            st.error(f"加载失败：{e}")
                with c3:
                    _del_confirm_key = f"confirm_del_design_{dname}"
                    if st.session_state.get(_del_confirm_key):
                        c_yes, c_no = st.columns(2)
                        with c_yes:
                            if st.button("确认", key=f"del_yes_{dname}", type="primary"):
                                delete_design(dname, project)
                                st.session_state[_del_confirm_key] = False
                                st.toast(f"已删除：{dname}")
                                st.rerun()
                        with c_no:
                            if st.button("取消", key=f"del_no_{dname}"):
                                st.session_state[_del_confirm_key] = False
                                st.rerun()
                    else:
                        if st.button("删除", key=f"del_{dname}", type="secondary"):
                            st.session_state[_del_confirm_key] = True
                            st.rerun()
        else:
            st.caption("暂无已保存的配置")

        st.divider()
        st.markdown("#### 导出")

        error_msg = _validate_config(cfg_dict)
        cfg_obj: Optional[AnswerSheetConfig] = None
        parse_error = ""
        try:
            cfg_obj = AnswerSheetConfig.from_dict(cfg_dict)
        except Exception as e:
            cfg_obj = None
            parse_error = str(e)

        export_disabled = cfg_obj is None or error_msg is not None

        # ── Sync layout config ──
        sync_col1, sync_col2 = st.columns([1, 2])
        with sync_col1:
            sync_clicked = st.button(
                "同步到识别配置",
                key="designer_sync_layout_btn",
                disabled=export_disabled,
            )
        with sync_col2:
            auto_sync = st.toggle(
                "自动同步识别配置",
                value=_AUTO_SYNC_DEFAULT,
                help="开启后，配置变更会持续改写识别流程使用的版面配置",
                key="designer_auto_sync",
            )
        if (sync_clicked or auto_sync) and cfg_obj and not error_msg:
            if _sync_layout_config(cfg_obj, project):
                st.session_state[_DIRTY_SYNC_KEY] = False
                rel_path = os.path.relpath(project.layout_path, project.workdir)
                st.caption(f":green[识别配置已同步]  ({rel_path})")
            else:
                st.caption(":red[识别配置同步失败]")
        elif st.session_state.get(_DIRTY_SYNC_KEY):
            st.caption(":orange[当前设计配置已加载，但尚未同步到识别配置]")

        c1, c2, c3 = st.columns(3)
        with c1:
            st.download_button(
                "配置 JSON",
                data=_export_json(cfg_obj) if cfg_obj else "{}",
                file_name="answer_sheet_config.json",
                mime="application/json",
                disabled=export_disabled,
                key="dl_json",
            )
        with c2:
            if cfg_obj and not error_msg:
                try:
                    html_content = _cached_generate(json.dumps(cfg_dict, ensure_ascii=False))
                    st.download_button(
                        "答题卡 HTML",
                        data=html_content,
                        file_name="answer_sheet.html",
                        mime="text/html",
                        key="dl_html",
                    )
                except Exception:
                    st.download_button(
                        "答题卡 HTML",
                        data="",
                        file_name="answer_sheet.html",
                        mime="text/html",
                        disabled=True,
                        key="dl_html",
                    )
            else:
                st.download_button(
                    "答题卡 HTML",
                    data="",
                    file_name="answer_sheet.html",
                    mime="text/html",
                    disabled=True,
                    key="dl_html",
                )
        with c3:
            st.download_button(
                "识别配置 JSON",
                data=_export_sheet_layout_json(cfg_obj) if cfg_obj else "{}",
                file_name="sheet_layout.json",
                mime="application/json",
                disabled=export_disabled,
                key="dl_layout",
            )

    # ═══════════════════════════════════════════════════════════════
    # Right column: live preview
    # ═══════════════════════════════════════════════════════════════
    with right_col:
        st.markdown("#### 实时预览")

        if cfg_obj is None:
            st.error(f"配置解析失败，请检查参数：{parse_error}")
        elif error_msg:
            st.warning(f"配置警告：\n\n{error_msg}")
            try:
                html_content = _cached_generate(json.dumps(cfg_dict, ensure_ascii=False))
                _render_preview_html(html_content, actual_pages)
            except Exception as e:
                st.error(f"HTML 生成失败: {e}")
        else:
            st.success("配置有效")
            try:
                html_content = _cached_generate(json.dumps(cfg_dict, ensure_ascii=False))
                _render_preview_html(html_content, actual_pages)
            except Exception as e:
                st.error(f"HTML 生成失败: {e}")

    # Persist back to session state + autosave（仅在配置变化时写入）
    previous_cfg = st.session_state.get("designer_config")
    # 深拷贝一份用于比较（避免 cfg_dict 和 session_state 是同一引用）
    previous_cfg_copy = copy.deepcopy(previous_cfg) if previous_cfg is not None else None
    st.session_state.designer_config = cfg_dict

    changed = False
    if previous_cfg_copy is not None:
        changed = json.dumps(previous_cfg_copy, sort_keys=True) != json.dumps(
            cfg_dict, sort_keys=True
        )
    if changed:
        _autosave(cfg_dict, project)
        _persist_design_asset(cfg_dict, project)
        st.toast("配置已自动保存", icon="💾")
    return changed
