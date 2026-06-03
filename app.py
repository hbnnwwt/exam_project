from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from exam_project.core.errors import ProjectError
from exam_project.core.legacy_import import import_legacy_project
from exam_project.core.package import ExamProjectPackage


def inspect_package(package_path: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="exam_project_gui_inspect_") as temp:
        project = ExamProjectPackage.open(package_path, Path(temp) / "opened")
        return project.manifest.to_dict()


def show_project_error(error: Exception) -> None:
    if isinstance(error, ProjectError):
        st.error(error.user_message)
    else:
        st.error(str(error))


st.set_page_config(page_title="Exam Project", layout="wide")
st.title("Exam Project")

import_tab, inspect_tab = st.tabs(["导入旧项目", "检查项目包"])

with import_tab:
    st.subheader("从旧系统资产创建 .examproj")
    legacy_root = st.text_input("旧项目目录", value="")
    package_output = st.text_input("输出项目包", value="demo.examproj")
    project_name = st.text_input("项目名称", value="期末考试")

    if st.button("创建项目包", type="primary"):
        try:
            output_path = Path(package_output)
            import_legacy_project(Path(legacy_root), output_path, name=project_name)
        except Exception as exc:
            show_project_error(exc)
        else:
            st.success(f"已创建考试项目: `{output_path}`")

with inspect_tab:
    st.subheader("检查 .examproj manifest")
    package_path = st.text_input("项目包路径", value="")

    if st.button("检查项目包", type="primary"):
        try:
            manifest = inspect_package(Path(package_path))
        except Exception as exc:
            show_project_error(exc)
        else:
            st.json(manifest)
