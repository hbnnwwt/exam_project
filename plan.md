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

## 最终复盘

- 已完成 `.examproj` foundation：manifest、checksum、安全 ZIP 打包/打开/保存、运行期项目对象、业务校验、完整打开前验证、旧系统资产导入和 CLI。
- 已完成项目工作区基础闭环：`.examproj` 可以被新建、打开、保存、另存为和关闭；GUI 在打开后进入工作区，而不是停留在包检查工具。
- 已接入旧系统单套识别和批量阅卷视图的适配层；当前阶段仍依赖同级 `auto_grading_system` 源码，后续应逐步把识别/评分模块迁移成 `exam_project` 自有模块。
- 旧系统真实根目录的 `config/sheet_layout.json` 与根目录 `参考答案.xlsx` 本身错配；新导入器会拒绝这种坏组合，这是正确行为，不应绕过校验。
- 当前阶段没有迁移答题卡设计器 UI 和空白页校对工作流；这些属于后续阶段。

## 后续计划

1. 迁移答题卡设计器，让空白新项目能在当前工作区内生成可阅卷布局。
2. 迁移空白标定工作流，把 baseline 写入当前 `.examproj`。
3. 逐步把旧系统识别、评分和阅卷视图从同级目录依赖迁移到 `exam_project` 自有包。
