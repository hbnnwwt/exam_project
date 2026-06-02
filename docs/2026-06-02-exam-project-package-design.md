# 考试项目包架构设计

> 状态：已确认设计方向  
> 日期：2026-06-02  
> 目标仓库：`hbnnwwt/exam_project`  
> 本地目录：`E:\授课\计算机视觉（微）\kejian\cv_wei\docs\exam_project`

## 1. 核心判断

现有 `auto_grading_system` 的核心问题不是某个测试太严格，而是数据结构错了：答题卡布局、参考答案、空白标定和输出结果散落在全局路径里，用户一旦换考试或换答题卡，旧数据就容易被覆盖或错配。

新项目应采用“考试项目包”模型：用户创建或打开一个 `.examproj` 文件，系统围绕当前项目完成答题卡设计、参考答案管理、空白标定、识别、评分和结果导出。旧系统是迁移来源，不应继续在旧全局路径上堆新功能。

## 2. 设计目标

1. 用户可以像打开 VSCode 项目一样打开一个考试项目。
2. 一个考试项目包含专属答题卡设计、识别布局、参考答案、空白标定、识别输出和评分结果。
3. 项目以单文件 `.examproj` 保存，普通用户不可直接编辑内部资产，不容易误删或破坏。
4. 项目打开时做完整校验，布局和参考答案不一致时立即报错。
5. 新仓库从干净架构开始，只迁移旧系统中可复用的能力，不复制旧全局状态。

## 3. 不做事项

第一阶段不做以下内容：

- 不做连线题识别或评分。
- 不做任意题型插件系统。
- 不做项目加密。`.examproj` 是受控 ZIP 容器，不是安全容器。
- 不做多人协作或云同步。
- 不保证旧 Streamlit UI 原样迁移。
- 不自动把所有历史输出塞入项目包，避免项目文件无限膨胀。

## 4. 项目包格式

`.examproj` 使用 ZIP 容器，扩展名隐藏内部结构。应用只通过“新建、打开、保存、另存为”修改它。

包内建议结构：

```text
project.json
design/
  answer_sheet.json
config/
  sheet_layout.json
  blank_baseline.json
answers/
  reference_answers.xlsx
outputs/
  results.xlsx
  processed/
logs/
```

`project.json` 是 manifest，负责描述项目元信息、资产路径和校验值。

```json
{
  "schema_version": 1,
  "project_id": "uuid",
  "name": "2026春-计算机视觉期末",
  "created_at": "2026-06-02T20:00:00+08:00",
  "updated_at": "2026-06-02T20:30:00+08:00",
  "assets": {
    "design": "design/answer_sheet.json",
    "layout": "config/sheet_layout.json",
    "baseline": "config/blank_baseline.json",
    "answers": "answers/reference_answers.xlsx"
  },
  "exam": {
    "student_id_digits": 10,
    "question_types": ["choice", "judge", "essay"]
  },
  "checksums": {
    "design/answer_sheet.json": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
    "config/sheet_layout.json": "sha256:2222222222222222222222222222222222222222222222222222222222222222",
    "config/blank_baseline.json": "sha256:3333333333333333333333333333333333333333333333333333333333333333",
    "answers/reference_answers.xlsx": "sha256:4444444444444444444444444444444444444444444444444444444444444444"
  }
}
```

## 5. 校验规则

打开项目时分三层校验。

第一层是容器校验：

- 文件必须是合法 ZIP。
- 必须包含 `project.json`。
- 包内路径不能包含 `../`、绝对路径或非法路径分隔，防止解包写出工作目录。

第二层是资产校验：

- manifest 声明的必需资产必须存在。
- checksum 必须匹配。
- `blank_baseline.json` 可以缺失，但状态应显示“未完成空白标定”，不能静默当成正常项目。

第三层是业务一致性校验：

- `reference_answers.xlsx` 的题号必须落在 `sheet_layout.json` 声明的题型范围内。
- 选择题答案必须属于该题型 options，例如 `A/B/C/D`。
- 判断题答案必须属于该题型 options，例如 `T/F`。
- 不一致时，项目打开失败，错误信息面向老师，而不是 Python traceback。

示例错误：

```text
项目无法打开：参考答案与答题卡布局不一致。
第 26 题答案为 T，但布局将第 26 题声明为选择题，允许答案为 A/B/C/D。
请检查该项目的参考答案或答题卡设计。
```

保存项目时采用原子写：

```text
写入 xxx.examproj.tmp
重新打开 tmp 并校验
校验通过后替换原文件
保留 xxx.examproj.bak
```

## 6. 新仓库架构

目标目录当前为空，应作为独立项目干净启动。建议目录：

```text
exam_project/
  pyproject.toml
  README.md
  src/exam_project/
    app/
      streamlit_app.py
      views/
    core/
      project.py
      project_package.py
      project_validation.py
      paths.py
    grading/
    recognition/
    answer_sheet/
    calibration/
  tests/
  docs/
```

核心边界：

- `core/` 负责 `.examproj` 打包、解包、保存、校验、当前项目上下文。
- `answer_sheet/` 迁移旧 `answer_sheet_generator`，输出项目内 `design/answer_sheet.json` 和 `config/sheet_layout.json`。
- `recognition/` 迁移旧识别模块，但算法只接受显式 `layout` 和 `baseline`，不知道 `.examproj`。
- `grading/` 迁移旧评分模块，`from_xlsx(path, layout=layout_dict)` 是一等接口。
- `app/` 是轻量 Streamlit 壳，围绕当前项目调用底层能力。

## 7. 运行期对象

新增三个核心对象。

`ExamProjectPackage`：

- 负责打开 `.examproj`。
- 负责解包到临时工作目录。
- 负责保存回 `.examproj`。
- 负责 checksum 计算和原子替换。

`ExamProject`：

- 表示运行期项目。
- 持有工作目录、manifest、layout 路径、baseline 路径、answers 路径、outputs 路径。
- 提供 `load_layout()`、`answer_key_path`、`baseline_path` 等简单接口。

`ProjectContext`：

- 表示当前打开项目。
- Streamlit 和 CLI 从这里获取当前项目。
- 不把 `.examproj` 概念传给识别和评分算法。

底层算法模块只看显式数据，不看全局路径：

```python
GradingService.from_xlsx(path, layout=layout)
LayoutAnalyzer(layout=layout)
recognize_choices(image, regions, threshold, layout=layout, blank_baseline=baseline)
recognize_judges(image, regions, threshold, layout=layout, blank_baseline=baseline)
```

## 8. 用户工作流

Streamlit 侧边栏顶部提供“考试项目”区域：

```text
考试项目
当前：2026春-计算机视觉期末.examproj

[新建项目] [打开项目] [保存项目] [另存为]

状态
✓ 答题卡设计
✓ 识别配置
✓ 参考答案
! 空白标定未完成
✓ 一致性校验通过
```

新建项目流程：

1. 输入项目名。
2. 选择内置模板或从空白答题卡设计开始。
3. 导入参考答案 xlsx，允许先跳过。
4. 保存为 `.examproj`。
5. 项目状态提示下一步：完成空白标定。

打开项目流程：

1. 选择 `.examproj`。
2. 校验容器、manifest、checksum 和业务一致性。
3. 校验通过后切换当前项目。
4. 校验失败时不切换项目，展示清晰错误。

设计器流程：

- 保存项目内 `design/answer_sheet.json`。
- 同步导出项目内 `config/sheet_layout.json`。
- 更新 manifest checksum。

空白标定流程：

- 根据当前项目 layout 推断页数和题型。
- 计算并保存项目内 `config/blank_baseline.json`。
- 更新 manifest checksum。

识别评分流程：

- 单套识别和批量识别都使用当前项目资产。
- 输出写入工作目录 `outputs/`。
- 用户保存项目后，输出进入 `.examproj`。
- 成绩 xlsx 始终可单独导出。

## 9. 迁移策略

推荐迁移方式：新仓库干净启动，按模块迁移。

不推荐把旧 `auto_grading_system` 整个复制过去。旧系统里有大量全局路径和 import-time 状态，复制后再重构会把问题带进新项目。

迁移顺序：

1. 初始化 `exam_project` 独立仓库并连接 `hbnnwwt/exam_project`。
2. 建立 `core/` 项目包能力。
3. 迁移 `answer_sheet_generator` 到 `answer_sheet/`。
4. 迁移评分模块到 `grading/`，先完成 layout/answers 一致性校验。
5. 迁移识别模块到 `recognition/`，删除全局 layout 依赖。
6. 迁移空白标定到 `calibration/`，保存到项目资产。
7. 新写 Streamlit 壳和视图，不原样搬旧大文件。
8. 提供“从旧系统创建项目”导入工具。

旧系统导入来源：

- `config/sheet_layout.json`
- `参考答案.xlsx`
- `config/blank_baseline.json`
- 可选 `saved_designs/*.json`

导入后立即执行项目校验。如果旧 layout 和旧参考答案不一致，导入失败并说明具体题号。

## 10. 第一阶段 MVP

第一阶段必须完成：

1. 新建 `.examproj`。
2. 打开 `.examproj` 并校验。
3. 保存和另存为 `.examproj`。
4. 项目内答题卡设计和 `sheet_layout.json` 同步。
5. 项目内参考答案导入和一致性校验。
6. 项目内空白标定。
7. 使用项目资产完成选择题、判断题、简答题识别与评分。
8. 导出成绩 xlsx。
9. 从旧系统资产创建项目。

成功标准：

老师可以新建一个考试项目，设计答题卡，导入参考答案，完成空白标定，识别一批试卷，导出成绩，保存并关闭应用。下次打开同一个 `.examproj`，所有资产仍在，校验通过，能继续识别和评分。

## 11. 测试策略

核心测试：

- 创建项目包后能重新打开。
- manifest 缺失时打开失败。
- checksum 不匹配时打开失败。
- ZIP 路径穿越被拒绝。
- 缺 baseline 时打开成功但状态为 warning。
- 参考答案与 layout 错配时打开失败，错误包含题号和原因。
- `.examproj.tmp` 校验失败时不替换原项目。
- `.examproj.bak` 在保存成功后存在。
- 旧系统资产导入成功生成项目。
- 旧系统资产错配时导入失败。

业务测试：

- 选择题、判断题、简答题评分使用项目 layout 的分值。
- 识别使用项目 blank baseline。
- 项目切换后，不复用上一项目的 layout、baseline 或答案。

## 12. 风险和约束

最大风险是把 `.examproj` 概念泄漏到底层算法里。底层算法只应接受显式数据：layout dict、baseline dict、xlsx path、图片路径。

第二个风险是项目包膨胀。第一阶段只把必要输出写入包，成绩 xlsx 支持导出，不强制保存所有中间图片。

第三个风险是旧系统迁移诱惑太大。旧 UI 可以参考，但不应原样复制。新项目要先立干净边界，再迁移能力。

## 13. 设计结论

采用 `.examproj` ZIP 容器 + manifest + checksum 是当前最合适的设计。它满足用户单文件管理的需求，也保留了工程上的可测试、可迁移和可恢复性。

新项目的核心不是“多课程下拉框”，而是“考试项目工作区”。只要项目包、项目上下文和显式资产依赖这三件事做对，后续再加新题型、三页动态流程、题型模板都会自然得多。
