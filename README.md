# exam_project

`exam_project` manages single-file `.examproj` exam packages.

An exam project can contain:

- answer sheet design
- recognition layout
- reference answers
- blank-sheet calibration
- recognition and grading outputs

This foundation milestone provides the core package format, manifest validation, checksum validation, safe ZIP packaging, project runtime objects, business validation, legacy asset import, and a small CLI.

## Development

Install in editable mode:

```bash
python -m pip install -e .[dev]
```

Install the GUI extra if you want to use `run_gui.bat`:

```bash
python -m pip install -e .[gui]
```

Run tests:

```bash
python -m pytest
```

On Windows, use `py` if `python` points to the Microsoft Store launcher:

```powershell
py -m pytest
```

## CLI

Create a new blank project package:

```bash
python -m exam_project.cli new demo.examproj --name "Final Exam"
```

Import assets from the old project layout:

```bash
python -m exam_project.cli import-legacy E:\path\to\auto_grading_system demo.examproj --name "Final Exam"
```

Inspect a project package:

```bash
python -m exam_project.cli inspect demo.examproj
```

After installation, the console script is also available:

```bash
exam-project inspect demo.examproj
```

## GUI

On Windows, double-click:

```text
run_gui.bat
```

The GUI is a thin Streamlit front end for the current foundation features:

- create a new blank `.examproj` and open it as the current project
- open an existing `.examproj`
- save and save-as the current project package
- import old project assets into `.examproj`
- inspect an existing `.examproj` manifest
- enter a project workspace with single-sheet and batch grading tabs

The current grading tabs reuse the old `auto_grading_system` single and batch
views through a project adapter. They read the open project's layout and
reference-answer assets instead of the old global `config/sheet_layout.json`
and `参考答案.xlsx`.

Answer-sheet designer and blank calibration workflows are not migrated yet.

## Package Contract

`.examproj` is a ZIP container with `project.json` at the root. Paths in the manifest are POSIX-style relative paths and are rejected if they are absolute, non-canonical, use backslashes, contain `..`, or name directories.

Required assets:

- `design`: answer sheet design JSON
- `layout`: recognition layout JSON
- `answers`: reference answers workbook

Optional asset:

- `baseline`: blank-sheet calibration JSON

Opening a package validates the manifest, required assets, declared checksums, layout JSON, and reference-answer workbook before replacing the target workdir. Invalid packages do not replace existing project directories.
