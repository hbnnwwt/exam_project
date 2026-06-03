# Plan 评审综合记录

**评审对象**: `plan.md`（考试项目包基础实施计划）
**评审时点**: 2026-06-03
**当前任务**: Task 16（项目工作区接入答题卡设计器）
**评审视角**: Linus 风格——数据结构和特殊用例驱动，杜绝"温水煮青蛙"式累积

---

## 一、总体判断

| 维度 | 评价 |
|---|---|
| 大方向 | 对。`.examproj` 闭环路径明确，从 manifest 基础到项目工作区、设计器接入，逻辑链完整 |
| 数据结构 | 良好。`workdir` 作为可编辑资产单一源，`dirty` 标记考虑到了保存语义，session 状态与业务函数分层 |
| 复杂度 | 受控。明确划定"复用旧 UI，不完整迁移"边界，避免一次吞掉全系统 |
| 特殊用例 | 显著改进。第二轮新增"不替代阅卷 tab"约束，从设计层消除了"合并 tab"的潜在分支 |
| 破坏分析 | 仍欠债。monkey-patch 缺乏安全保护，旧模块迁移无 deadline |
| 实用性 | 良好。最终复盘有真实测试指标和可验证的烟测清单 |

**综合 Taste Score**: **So-so → Good（取决于遗留问题是否在 Task 17 之前清掉）**

---

## 二、两次审查的问题追踪

| # | 问题 | 严重度 | 第一轮 | 第二轮后 | 处置建议 |
|---|---|---|---|---|---|
| 1 | `configure_project_designer()` 直接修改旧模块全局变量，无 `try/finally` 保护 | 高 | 提出 | 未动 | Task 16 必须解决 |
| 2 | "逐步迁移旧模块"无 deadline 或退出条件 | 高 | 提出 | 未动（"逐步"仍在第 187 行） | Task 17 规划前必须定义 |
| 3 | 项目资产路径散落（`workdir / "design" / "saved_designs"` 等直接拼路径） | 中 | 提出 | 未动 | 建议在 Task 17 引入 `Project` 语义化访问器 |
| 4 | 缺少"新建项目 → 首次阅卷"的用户操作路径计数 | 低 | 提出 | 未动 | 复盘章节补一句即可 |
| 5 | 设计器接入不应替代阅卷 tab；单套识别 vs 批量阅卷角色切分 | — | 未提 | **新增约束**（已解决） | 落实为代码层强约束 |
| 6 | 新建项目初始 layout 应保持为空，避免参考答案校验失败 | — | 暗含 | **明确写入**（已解决） | 已是正确决策 |

**总结**: 第二轮回应了 2 个新问题（#5、#6），但第一轮提出的 4 个核心问题全部未动。本评审的核心价值是**把这些遗留问题钉在桌面上**，避免它们随 task 数增长而模糊。

---

## 三、未解决问题的详细分析

### 3.1 Monkey-patch 全局状态污染（问题 #1）

**现状**（plan.md 第 143-147 行）:

```python
# 导入旧 views.designer_view，设置：
_Layout_PATH = project.layout_path
_SAVED_DESIGNS_DIR = project.workdir / "design" / "saved_designs"
_AUTOSAVE_PATH = project.asset_path("design")
```

**风险**:
- 任何后续 task 把 `render_designer()` 抽到多线程/子进程里调用，状态会互相覆盖
- 单测里 `configure_project_designer()` 改全局后未还原，会污染下一个测试
- 工程师读 `render_designer()` 代码时，不会看到任何"上下文参数"，因为他只看到了"这个模块用 `_LAYOUT_PATH`"，找不到调用方在哪改了这个变量

**Linus 视角**: 这是"用全局状态换接口稳定"的典型脏招。**特殊用例被掩盖，而不是被消除**。

**最低成本修复**:
1. 把 designer tab 渲染包成上下文管理器 `with designer_paths(project): render_designer()`，进入时备份、退出时还原
2. 或者把 `render_designer()` 改造为接受 `paths` 参数（依赖注入），彻底消灭全局
3. 若两者都做不到，至少在 `configure_project_designer()` 文档里写明"调用方负责在会话结束前 close"，并在 session 层显式调用

**必做时点**: Task 16 提交前。

### 3.2 旧模块迁移缺乏退出条件（问题 #2）

**现状**（plan.md 第 187 行）:

> 逐步把旧系统识别、评分、设计器和阅卷视图从同级目录依赖迁移到 `exam_project` 自有包。

**为什么这是空头支票**:
- Task 15 加了阅卷视图 adapter
- Task 16 加了设计器 adapter
- 每个 task 都在**加深**对旧模块的依赖
- "逐步"如果不定义"什么时候停止"，等同于"永不"

**Linus 视角**: 温水煮青蛙。当前还能撑 2-3 个 task，再往后迁移成本会随耦合度指数上升。

**最低成本修复**（在 plan.md 中加一段）:

> **迁移退出条件**:
> - Task N（建议 Task 17）开始前，识别/评分/设计器模块不再 `import auto_grading_system.*` 中的任何运行时模块
> - 从 Task N 起，新代码必须以 `exam_project` 包内模块身份存在
> - 若某 task 无法满足该条件，必须在 plan 中显式声明延期理由，不得默认通过

**必做时点**: Task 17 规划前。

### 3.3 项目资产路径散落（问题 #3）

**现状**: 至少三处路径直接拼接:

```python
project.layout_path                                       # 第 145 行
project.workdir / "design" / "saved_designs"              # 第 146 行
project.asset_path("design")                              # 第 147 行
project.workdir / "config" / "sheet_layout.json"          # Task 15 隐含
```

**为什么是问题**:
- 三种表达方式（`project.layout_path`、`workdir / "..."`、`project.asset_path()`）混用
- 路径规则改一处，调用方散落改 N 处
- 单元测试时 mock 路径需要重写多处

**Linus 视角**: 路径是数据结构的延伸。**坏的数据结构会让所有调用方都做相同的小修正**。

**建议**（在 Task 17 之前引入）:

```python
class Project:
    def design_dir(self) -> Path: ...        # design/ 目录
    def design_path(self) -> Path: ...       # design/answer_sheet.json
    def saved_designs_dir(self) -> Path: ... # design/saved_designs/
    def layout_path(self) -> Path: ...       # config/sheet_layout.json
    def answers_path(self) -> Path: ...      # 参考答案.xlsx
    def workdir_data(self) -> Path: ...      # workdir/data/
```

**建议时点**: Task 17 引入，Task 16 暂不阻塞。

---

## 四、做得好的地方（避免一边倒批评）

### 4.1 第二轮新增的"不替代阅卷 tab"约束 — Good Taste

> 答题卡设计器只新增设计入口，不替代阅卷入口。工作区必须继续保留 `阅卷` tab，且 `阅卷` tab 内必须同时保留 `单套识别` 和 `批量阅卷`。

这条约束**预先关闭**了未来代码评审必然会问的问题："为什么不合并 tab？" 配合下面的角色切分：

- 单套识别 → 调试过程 + 课堂演示
- 批量阅卷 → 正式批处理

它把"是否合并"这个决策永远钉死。**Linus 原则：好的设计消灭分支，而不是增加分支**。

### 4.2 新建项目初始 layout 保持为空

> 若含题型，参考答案仍为空会导致业务校验失败，因此新项目初始仍应保持 layout 空，设计器同步后再要求参考答案匹配。

这是这个 plan 里**最重要的一句话**之一。它避免了一个陷阱：给新项目塞默认 layout，参考答案校验立刻挂掉，制造一个"看起来对其实烂掉"的项目包。

### 4.3 答案与布局错配时拒绝保存

> 若 layout 同步后参考答案不匹配，保存会失败并显示校验错误。这是正确行为：不能保存一个布局和答案错配的项目。

**这就是防错配项目包的必要保护**。Plan 敢于把"用户必须修"作为特性，而不是绕过校验，态度正确。

### 4.4 五层拆解方法论一致

整个 plan 在 Task 15、Task 16 都使用了统一的"五层拆解"框架（数据结构 / 特殊用例 / 复杂度 / 破坏分析 / 实用性），让 task 之间可比、可审、可追溯。

---

## 五、行动建议（按优先级）

### 5.1 必做：Task 16 提交前

1. **monkey-patch 保护**: `configure_project_designer()` 必须有 `try/finally` 还原旧模块全局，或封装为上下文管理器
2. **测试隔离**: 单测必须在 `configure_project_designer()` 之后显式还原全局，或使用 fixture 自动保存/恢复

### 5.2 强烈建议：Task 17 规划前

1. **定义迁移退出条件**: 明确"哪个 task 之后不再 `import auto_grading_system.*`"
2. **引入 `Project` 路径访问器**: 集中路径规则，禁止调用方直接拼 `workdir / "..."`

### 5.3 建议：复盘章节补一句

> 用户新建一个项目并完成首次阅卷，需要点击几次鼠标、切换几个 tab？把这条作为下一阶段的可用性指标。

---

## 六、结论

**当前 plan 处在"骨架层完成、适配层加深"的临界点**。

- 骨架层（manifest / checksum / package / session）做得好，是 `.examproj` 能立得住的根基
- 适配层（grading adapter / designer adapter）每一个 task 都在加深对旧模块的依赖

**核心警告**: 不要再让"逐步"两个字裸奔。**今天写下"什么时候停止用 adapter"，否则 Task 17/18 一定会让 plan 变得越来越难执行**。

下一轮评审时，建议优先验证三件事：

1. `configure_project_designer()` 是否做了全局变量保护
2. plan.md 是否新增了"迁移退出条件"段落
3. `Project` 路径访问器是否被引入并替换了直接路径拼接

如果三件都做到了，**Taste Score 可以从 So-so 升到 Good**。
