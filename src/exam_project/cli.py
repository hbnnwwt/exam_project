from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from exam_project.core.errors import ProjectError
from exam_project.core.legacy_import import import_legacy_project
from exam_project.core.package import ExamProjectPackage


def _cmd_import_legacy(args: argparse.Namespace) -> int:
    import_legacy_project(Path(args.legacy_root), Path(args.output), name=args.name)
    print(f"已创建考试项目: {args.output}")
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory(prefix="exam_project_inspect_") as temp:
        project = ExamProjectPackage.open(Path(args.package), Path(temp) / "opened")
        print(json.dumps(project.manifest.to_dict(), ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="exam-project", description="考试项目包工具")
    sub = parser.add_subparsers(dest="command", required=True)

    import_parser = sub.add_parser("import-legacy", help="从旧系统资产创建 .examproj")
    import_parser.add_argument("legacy_root")
    import_parser.add_argument("output")
    import_parser.add_argument("--name", required=True)
    import_parser.set_defaults(func=_cmd_import_legacy)

    inspect_parser = sub.add_parser("inspect", help="检查 .examproj 并输出 manifest")
    inspect_parser.add_argument("package")
    inspect_parser.set_defaults(func=_cmd_inspect)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ProjectError as exc:
        parser.exit(2, exc.user_message + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
