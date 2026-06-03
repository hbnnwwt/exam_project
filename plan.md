# 考试项目包基础实施计划

## 当前目标

先实现 `.examproj` 项目包基础能力：manifest、checksum、安全解包、保存备份、运行期项目对象、业务校验和旧系统资产导入。

详细实施计划见：

`docs/superpowers/plans/2026-06-02-exam-project-foundation.md`

## 检查清单

- [x] 明确第一阶段不一次性迁移 UI、识别、评分和标定全量功能
- [x] 将实施范围收敛到项目包 foundation
- [x] 写出可按任务执行的测试驱动实施计划
- [x] 用户确认实施方式

## 执行进度

- [x] Task 1：项目骨架
- [x] Task 2：领域错误类型
- [x] Task 3：Manifest 模型与安全资产路径
- [x] Task 4：Checksum 工具
- [x] Task 5：项目包打开与保存
- [x] Task 6：运行期项目对象与上下文
- [x] Task 7：资产与业务校验
- [x] Task 8：打开项目包时做完整项目验证
- [x] Task 9：旧系统资产导入
- [x] Task 10：CLI Inspect 与 Legacy Import
- [x] Task 11：README 更新
- [x] Task 12：最终验证
- [x] Task 13：补充 GUI 启动入口
- [x] Task 14：支持新建空白考试项目
- [x] Task 15：项目工作区、打开/保存与阅卷视图复用
- [x] Task 16：项目工作区接入答题卡设计器
- [x] Task 17：恢复在线 OCR 配置并接入空白试卷校对

## 审查记录

- Task 3 已完成规格审查和代码质量审查；manifest 输入边界收紧为严格 JSON dict/list，资产路径和资产键均拒绝空白边界。
- Task 4 已完成规格审查和代码质量审查；checksum 使用 SHA-256 分块读取，资产路径复用 manifest 安全校验。
- Task 5 已完成规格审查和代码质量审查；ZIP 解包拒绝路径逃逸、重复条目、raw 反斜杠和 Windows 大小写碰撞，保存流程先验证临时包再替换原包。
- Task 6 已完成规格审查和代码质量审查；运行期对象保持轻量，只解析资产路径和 layout JSON，不提前塞入业务校验。
- Task 7 已完成规格审查和代码质量审查；参考答案校验拒绝未知题号、半空列、无效选项和非法工作簿，错误消息使用中文 UI 文案。
- Task 8 已完成规格审查和代码质量审查；打开项目包时在 staging 目录解析 manifest 后执行完整项目校验，验证失败不会替换已有目标目录，checksum 声明缺失资产会失败，缺失 baseline 仍允许。
- Task 9 已完成规格审查和代码质量审查；旧系统导入只迁移 layout、参考答案、可选 baseline 和设计占位资产，先完整校验再保存，坏旧资产不会覆盖已有项目包。
- Task 10 已完成规格审查和代码质量审查；CLI 只暴露 import-legacy 和 inspect，inspect 使用临时子目录避免 `.old-*` 残留，项目错误以退出码 2 和用户可读 stderr 返回。
- Task 11 已完成文档审查；README 记录 foundation 范围、开发命令、CLI 用法和 `.examproj` 包契约，避免承诺尚未迁移的 UI、识别和评分工作流。
- Task 12 已完成最终验证；全量测试 `163 passed, 1 skipped`，手工 CLI import/inspect 烟测通过，GitHub 分支已按里程碑推送。
- Task 13 计划：补一个 Streamlit 薄 GUI，只暴露旧项目导入和项目包检查；新增 `run_gui.bat` 复用旧系统的 Python 检测和端口切换逻辑；README 说明 CLI 与 GUI 两种运行方式。
- Task 13 已完成验证；`run_gui.bat` 可启动 Streamlit GUI，浏览器实测导入旧项目夹具并检查 manifest 通过，全量测试仍为 `163 passed, 1 skipped`。
- Task 14 计划：新增空白考试项目创建能力，把 GUI 主入口调整为“新建项目”，旧项目导入保留为迁移辅助功能；CLI 增加 `new` 命令并补测试。
- Task 14 已完成验证；核心 `create_exam_project()` 生成最小合法空白项目包，CLI `new` 和 GUI 新建入口均可创建后再 inspect，全量测试 `171 passed, 1 skipped`。
- Task 15 计划：把 `.examproj` 变成真正的项目工作区，而不是只做压缩包管理。新建或打开项目后，GUI 必须进入当前项目工作区，并显示单套识别和批量阅卷入口；保存按钮把当前工作区校验后写回 `.examproj`，另存为生成新项目包。旧项目导入继续保留为迁移辅助功能，但不是主流程。
- Task 15 已完成验证；新增 GUI 项目会话层，支持新建并打开、打开已有项目、保存、另存为和关闭；工作区接入旧系统 single/batch 阅卷视图适配层，显式把当前项目的 layout、参考答案、输出目录和上传答案路径传给旧视图，避免继续读取旧系统全局资产。全量测试 `178 passed, 1 skipped`，浏览器烟测通过新建进入工作区、打开已有项目、保存、另存为和空白布局前置拦截。
- Task 16 计划：在项目工作区加入答题卡设计器 tab。设计器复用旧系统 `views.designer_view.render_designer()`，但通过适配层把 `_LAYOUT_PATH`、`_SAVED_DESIGNS_DIR`、`_AUTOSAVE_PATH` 指向当前 `.examproj` 解包工作区；设计 JSON 写入项目声明的 `design` 资产，识别 layout 写入项目声明的 `layout` 资产。用户同步识别配置后，再点项目保存即可刷新 manifest checksum 并写回 `.examproj`。
- Task 16 补充约束：答题卡设计器只新增设计入口，不替代阅卷入口。工作区必须继续保留 `阅卷` tab，且 `阅卷` tab 内必须同时保留 `单套识别` 和 `批量阅卷`；单套识别用于调试过程和课堂演示，批量阅卷用于正式批处理。
- Task 16 已完成验证；工作区新增 `答题卡设计` tab，复用旧设计器但通过 `configure_project_designer()` 上下文管理器临时指向当前项目资产，退出时还原旧模块全局路径。`阅卷` tab 内继续保留 `单套识别` 和 `批量阅卷` 两个子 tab；空白 layout 时两个入口仍显示前置提示。全量测试 `183 passed, 1 skipped`，浏览器烟测通过设计器渲染、阅卷子 tab 保留和批量 tab 切换。
- Task 17 计划：恢复项目级 online OCR / LLM 配置入口，并接入空白试卷校对模块。配置写入当前项目的 `config/api_keys.json` 与 `config/model_config.json`，不再写旧系统根目录；空白校对复用旧系统 `views.calibration_view.render_calibration()`，但用上下文管理器把 `_LAYOUT_PATH` 和 `_BASELINE_PATH` 指向当前项目的 layout 与 baseline 资产。保存项目时现有 checksum 刷新会把 baseline 打进 `.examproj`。
- Task 17 已完成验证；侧边栏恢复 `ModelScope API Key`、备用 Key、OCR 专用 Key、在线 OCR 模型、Base URL、LLM 模型和保存按钮，写入当前项目 `config/api_keys.json` 与 `config/model_config.json`。工作区新增 `空白校对` tab，复用旧空白校对 view 但通过 `configure_project_calibration()` 指向当前项目 layout、baseline 和 workdir。全量测试 `188 passed, 1 skipped`，浏览器烟测通过新建项目、online OCR 字段显示、空白校对渲染、`单套识别`/`批量阅卷` 保留。

### Task 15 详细计划：项目工作区、打开/保存与阅卷视图复用

#### 需求理解

当前需求不是“再加一个导入按钮”。真正需求是：用户可以像 VS Code 打开文件夹一样打开一个考试项目，进入该项目的工作区，编辑和阅卷都围绕当前项目发生。新建项目和打开已有项目只是进入工作区的两种方式。旧项目导入只是迁移工具，不应该是主入口。

#### Linus 五层拆解

1. 数据结构：增加 GUI 会话层的 `current_project`，包含 `package_path`、`workdir`、`manifest`、`dirty`。`workdir` 是所有可编辑资产的唯一真实源，保存时打包回 `package_path`。
2. 特殊情况：新建、打开、导入三条入口最终都调用同一个 `set_current_project()`，进入同一个工作区，不给 UI 留三套状态分支。
3. 复杂度：本阶段只做工作区壳、打开、保存、另存为、关闭、单套识别、批量阅卷。答题卡设计器和空白标定后续迁移，避免一次吞掉全系统。
4. 破坏分析：不能让旧阅卷界面继续偷偷读取旧仓库根目录的 `config/sheet_layout.json` 和 `参考答案.xlsx`。single/batch 必须使用当前 `.examproj` 解包后的 `layout` 和 `answers`。
5. 实用性：这是生产路径的基础能力。没有它，`.examproj` 只是包格式，不是应用。

#### 核心判断

Worth doing：必须做。否则用户创建项目后无法继续阅卷，项目包模型没有闭环。

#### 设计方案

1. 新增 GUI 项目会话模块
   - 新建 `src/exam_project/gui/session.py` 或等价小模块。
   - 提供 `open_project(package_path)`、`create_and_open_project(...)`、`save_project()`、`save_project_as(path)`、`close_project()`。
   - 打开项目时解包到稳定工作目录，例如 `.exam_project_workspace/<project_id>`，而不是每次临时目录即丢。
   - 会话状态存在 `st.session_state`，但业务打开/保存逻辑放在普通函数里，方便测试。

2. 调整 Streamlit 主界面
   - 左侧或顶部提供“新建项目 / 打开项目 / 保存 / 另存为 / 关闭”。
   - 没有当前项目时显示启动页：新建项目、打开项目、导入旧项目。
   - 新建或打开成功后设置当前项目，并自动进入“项目工作区”。
   - 工作区显示项目名、项目包路径、保存状态和资产检查摘要。

3. 复用阅卷界面
   - 从旧系统迁移或适配 `views.single_view.render_single()` 与 `views.batch_view.render_batch()`。
   - 先只接入“单套识别”和“批量阅卷”两个 tab。
   - 构造项目级 `PATHS`：`answer_key` 指向当前项目的参考答案，`output_dir`、`processed_dir`、`batch_checkpoint` 指向当前项目 workdir 下的数据目录。
   - 最关键的坏味道：旧 `modules.pipeline.LAYOUT` 和 `modules.layout._LAYOUT` 是 import-time 全局配置。本阶段必须给阅卷适配层提供显式 layout，或者在迁移模块中删除全局 layout 依赖。不能用“临时复制 layout 到旧仓库 config”这种脏办法。

4. 保存策略
   - 保存前重新生成或更新 manifest 的 `updated_at` 与 checksum。
   - 调用现有 `ExamProjectPackage.save(workdir, package_path)` 做原子保存和备份。
   - 保存失败不替换原包，沿用现有 package 层保证。
   - 另存为成功后，当前项目的 `package_path` 切换到新路径。

5. 测试与验证
   - 单元测试：新建后自动打开；打开已有项目；保存生成备份；另存为切换路径；坏项目打开不污染当前会话。
   - GUI 烟测：启动 GUI，新建项目后看到工作区；打开已有项目后看到 single/batch tab；保存按钮成功。
   - 全量测试：`py -m pytest -p no:cacheprovider`。

#### 里程碑拆分

1. 先做项目会话和打开/保存 GUI，不接入阅卷算法。
2. 再接入 single/batch 的项目路径适配。
3. 最后处理旧全局 layout 依赖，保证阅卷真正读当前项目资产。
4. 验证后提交 GitHub。若网络仍失败，保留本地 commit 并报告 ahead 状态。

### Task 16 详细计划：项目工作区接入答题卡设计器

#### 需求理解

当前需求是让新建或打开的考试项目包含答题卡设计器模块。它不是一个独立模板工具，而是当前项目的一部分：用户编辑的是当前 `.examproj` 的答题卡设计资产；同步后生成当前项目的识别布局；保存项目后这些资产被打进单文件项目包。

#### Linus 五层拆解

1. 数据结构：设计器源数据是 `design/answer_sheet.json`，识别派生产物是 `config/sheet_layout.json`。二者都已经在 manifest 中声明，不需要再发明一套“设计器状态文件”。
2. 特殊情况：新建空白项目当前写入的是占位 JSON，旧设计器不认识。应改成设计器原生 `AnswerSheetConfig` 格式，或者在适配层检测并升级；不要让设计器靠旧全局 autosave 恢复。
3. 复杂度：先复用旧设计器 UI，不完整迁移 `answer_sheet_generator/` 包。本阶段只做路径适配和工作区集成。
4. 破坏分析：不能让设计器继续写旧系统根目录的 `config/sheet_layout.json` 和 `saved_designs/`，否则当前 `.examproj` 看起来被编辑了，实际包里没变。
5. 实用性：这是空白项目进入可阅卷状态的必要流程。没有它，Task 15 的阅卷前置检查会一直拦住新项目。

#### 核心判断

Worth doing：必须做。答题卡设计是 `.examproj` 的核心资产，不接入设计器，项目工作流不闭合。

#### 方案选择

推荐 A：适配旧设计器并嵌入当前工作区。

- A：复用 `render_designer()`，调用前把旧模块的路径变量指向当前项目。成本最低，能快速闭合“新建项目 -> 设计 -> 同步 layout -> 保存 -> 阅卷”。
- B：完整迁移 `answer_sheet_generator/` 和 `designer_view.py` 到 `exam_project`。长期正确，但会扩大本次改动范围。
- C：重写一个简化设计器。没有必要，旧设计器已经有模板、预览、导出和 layout 同步。

#### 实施步骤

1. 新增设计器适配函数
   - 在 `src/exam_project/gui/grading_adapter.py` 或新模块中增加 `configure_project_designer(project)` 上下文管理器。
   - 导入旧 `views.designer_view`，设置：
     - `_LAYOUT_PATH = project.layout_path`
     - `_SAVED_DESIGNS_DIR = project.workdir / "design" / "saved_designs"`
     - `_AUTOSAVE_PATH = project.asset_path("design")`
   - 使用 `try/finally` 在退出时还原旧模块全局变量，避免污染后续测试或其他项目会话。
   - 保证目录存在。

2. 新建项目写入设计器原生配置
   - 修改 `create_exam_project()`，让 `design/answer_sheet.json` 使用旧 `AnswerSheetConfig` 兼容结构：`meta`、`student_id`、`pages`。
   - 默认配置要和当前空白 layout 保持不冲突；可以含默认选择/判断/简答，也可以只含最小选择题模板。若含题型，参考答案仍为空会导致业务校验失败，因此新项目初始仍应保持 layout 空，设计器同步后再要求参考答案匹配。

3. 工作区 UI 接入
   - `render_workspace()` 增加 tab：`答题卡设计`、`阅卷`、`项目资产`。
   - `阅卷` tab 内继续保留 `单套识别` 和 `批量阅卷` 两个子 tab；不能为了接入设计器删掉任一视图。
   - `答题卡设计` tab 调用旧 `designer_view.render_designer()`。
   - 在 tab 顶部提示：同步识别配置后，需要点击左侧“保存”写回项目包。

4. 保存与校验策略
   - 用户点设计器“同步到识别配置”后，只更新工作区文件。
   - 用户点项目“保存”时，现有 `save_project()` 统一刷新 checksum 并打包。
   - 若 layout 同步后参考答案不匹配，保存会失败并显示校验错误。这是正确行为：不能保存一个布局和答案错配的项目。

5. 测试与验证
   - 单元测试：新建项目的 `design/answer_sheet.json` 是设计器可读结构。
   - 单元测试：`configure_project_designer()` 把旧设计器路径指向当前项目。
   - GUI 烟测：打开项目后出现“答题卡设计”tab，设计器能渲染；点击“同步到识别配置”会写当前项目 layout；项目保存能刷新包。
   - 全量测试：`py -m pytest -p no:cacheprovider`。

#### 风险

- 旧设计器仍依赖同级 `auto_grading_system` 源码和 `answer_sheet_generator` 包。本阶段接受这个依赖，但不能扩大到写旧项目资产。
- 设计器同步 layout 后，如果参考答案没有同步更新，项目保存会被业务校验拒绝。这不是 bug，是防止错配项目包的必要保护。

#### 迁移退出条件

- Task 17 规划前必须明确旧模块迁移路线，不再让“逐步迁移”裸奔。
- Task 17 起，新功能优先落在 `exam_project` 自有模块；若继续复用同级 `auto_grading_system` 运行时模块，必须在计划中写明延期理由和退出任务编号。
- 识别、评分、设计器、阅卷视图最终不得依赖同级目录 import 作为长期架构。

### Task 17 详细计划：恢复在线 OCR 配置并接入空白试卷校对

#### 需求理解

当前 GUI 把旧系统的 online OCR 配置入口删薄了，只剩 OCR 引擎选择。这会直接破坏在线 OCR 使用路径：用户无法填写 ModelScope API Key、OCR 专用 Key、在线 OCR 模型，也无法保存 Base URL 和模型配置。另一个缺口是空白试卷校对/标定模块还没有进入项目工作区，导致当前 `.examproj` 无法生成 `config/blank_baseline.json`。

#### Linus 五层拆解

1. 数据结构：API Key 是项目级配置，落在 `config/api_keys.json`；模型配置落在 `config/model_config.json`；空白基准落在 manifest optional asset `config/blank_baseline.json`。
2. 特殊情况：online OCR 与 LLM 评分可以共用主 Key，也可以使用 OCR 专用 Key。不要把它硬编码成一个 Key，否则用户无法处理限流和权限拆分。
3. 复杂度：恢复旧侧边栏配置块，不重写 OCR/LLM 模块；空白校对复用旧 view，但路径 patch 必须用上下文管理器。
4. 破坏分析：不能写旧系统根目录的 `config/api_keys.json`、`config/model_config.json` 或 `config/blank_baseline.json`。所有写入必须发生在当前项目 workdir。
5. 实用性：online OCR 配置是简答题 OCR 的必要入口；空白校对是生成 baseline、提升填涂识别稳定性的必要工作流。

#### 核心判断

Worth doing：必须做。否则项目工作区缺少在线 OCR 配置入口，也缺少空白基准生成路径。

#### 实施步骤

1. 恢复项目级 API/OCR/LLM 配置 UI
   - 在 `render_grading_controls()` 中恢复旧系统的：
     - `ModelScope API Key`
     - 备用 API Key 列表
     - `在线 OCR 使用同一个 Key`
     - `OCR 专用 API Key`
     - `在线 OCR 模型`
     - `Base URL`
     - LLM 模型和备用模型
     - 保存 API Key / 保存模型配置按钮
   - 使用当前项目的 `paths["api_keys"]` 和 `paths["model_config"]`。
   - 返回给 single/batch 的 `ocr_api_config` 必须包含在线 OCR 所需 `api_key`、`base_url`、`ocr_model`、`ocr_max_tokens`、`ocr_prompt`。

2. 接入空白试卷校对 tab
   - 工作区 tab 调整为：`答题卡设计`、`空白校对`、`阅卷`、`项目资产`。
   - 新增 `configure_project_calibration(project)` 上下文管理器。
   - 调用旧 `views.calibration_view.render_calibration()` 前，设置：
     - `_LAYOUT_PATH = project.layout_path`
     - `_BASELINE_PATH = project.baseline_path`
     - `_BASE_DIR = project.workdir`
   - 进入校对前调用 `apply_project_layout(project)`，保证旧 `LayoutAnalyzer` 读取当前 layout。

3. 保存策略
   - 空白校对点击“保存空白基准”后只写工作区 baseline。
   - 用户点击项目“保存”时，现有 `save_project()` 刷新 checksum 并打包 `.examproj`。
   - 如果 baseline 文件存在，checksum 应包含 `config/blank_baseline.json`。

4. 测试与验证
   - 单元测试：保存 API/model 配置使用项目路径，不能写旧根目录。
   - 单元测试：calibration context 退出后还原旧模块全局路径。
   - 单元测试：baseline 文件存在时保存项目后 manifest checksums 包含 baseline。
   - GUI 烟测：侧边栏出现 online OCR 配置；工作区出现 `空白校对` tab；阅卷 tab 仍保留 `单套识别` 和 `批量阅卷`。
   - 全量测试：`py -m pytest -p no:cacheprovider`。

## 最终复盘

- 已完成 `.examproj` foundation：manifest、checksum、安全 ZIP 打包/打开/保存、运行期项目对象、业务校验、完整打开前验证、旧系统资产导入和 CLI。
- 已完成项目工作区基础闭环：`.examproj` 可以被新建、打开、保存、另存为和关闭；GUI 在打开后进入工作区，而不是停留在包检查工具。
- 已接入旧系统单套识别和批量阅卷视图的适配层；当前阶段仍依赖同级 `auto_grading_system` 源码，后续应逐步把识别/评分模块迁移成 `exam_project` 自有模块。
- 已接入答题卡设计器；设计器源数据写入当前项目的 `design` 资产，识别 layout 写入当前项目的 `layout` 资产，且旧设计器全局路径 patch 已加上下文保护。
- 已恢复项目级 online OCR / LLM 配置；配置写入当前 `.examproj` 工作区的 `config/api_keys.json` 与 `config/model_config.json`，不会污染旧系统根目录。
- 已接入空白校对模块；空白基准写入当前项目的 `config/blank_baseline.json`，项目保存时刷新 checksum 并打包进 `.examproj`。
- `阅卷` 工作区明确保留两条路径：`单套识别` 用于调试过程和课堂演示，`批量阅卷` 用于正式批处理。
- 旧系统真实根目录的 `config/sheet_layout.json` 与根目录 `参考答案.xlsx` 本身错配；新导入器会拒绝这种坏组合，这是正确行为，不应绕过校验。
- 当前阶段仍在复用旧系统 Streamlit 视图；后续重点不是再补入口，而是把旧识别、评分、设计器、空白校对和阅卷视图逐步迁移到 `exam_project` 自有模块。

## 后续计划

1. Task 18 定义旧模块迁移退出条件和路径访问器整理范围。
2. 逐步把旧系统识别、评分、设计器、空白校对和阅卷视图从同级目录依赖迁移到 `exam_project` 自有包，并为每项迁移写明退出任务编号。
