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
- design an answer sheet inside the current project workspace
- edit project-level API Key, online OCR, and LLM model settings
- calibrate a blank answer sheet inside the current project workspace
- enter a grading workspace with both single-sheet and batch grading tabs

The current designer and grading tabs reuse the old `auto_grading_system`
Streamlit views through project adapters. They read and write the open
project's design, layout, reference-answer, and output assets instead of the old
global `config/sheet_layout.json`, `saved_designs`, and `参考答案.xlsx`.
The online OCR and LLM settings are stored in the open project's
`config/api_keys.json` and `config/model_config.json`; they are not written back
to the old system root. Blank calibration writes `config/blank_baseline.json` in
the current project workspace. Click the project `保存` button to refresh
manifest checksums and package those changes into the `.examproj` file.

The single-sheet view is kept for process debugging and classroom
demonstration. The batch view is kept for batch grading.

## Package Contract

`.examproj` is a ZIP container with `project.json` at the root. Paths in the manifest are POSIX-style relative paths and are rejected if they are absolute, non-canonical, use backslashes, contain `..`, or name directories.

Required assets:

- `design`: answer sheet design JSON
- `layout`: recognition layout JSON
- `answers`: reference answers workbook

Optional asset:

- `baseline`: blank-sheet calibration JSON

Opening a package validates the manifest, required assets, declared checksums, layout JSON, and reference-answer workbook before replacing the target workdir. Invalid packages do not replace existing project directories.
