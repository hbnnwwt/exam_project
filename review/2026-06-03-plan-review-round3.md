# Plan 评审 Round 3 — Task 16/17 实现后复核

**评审对象**: `plan.md`（考试项目包基础实施计划）+ `src/exam_project/` 实现
**评审时点**: 2026-06-03
**任务进度**: Task 16、Task 17 已完成
**测试基线**: `188 passed, 1 skipped`（与 plan.md 第 60 行声明一致）
**评审视角**: Linus 风格——验证上一轮 review 的要求是否真的在代码层兑现

---

## 一、升级条件核对

上一轮 review 结尾给出了"如果三件都做到，So-so 升到 Good"的判断。本轮按该清单逐项验证。

| # | 上一轮要求 | 状态 | 证据 |
|---|---|---|---|
| 1 | `configure_project_designer()` 加 `try/finally` 保护 | ✅ 完全兑现 | `grading_adapter.py:125-142` |
| 2 | plan.md 新增"迁移退出条件"段落 | ✅ 完全兑现 | `plan.md:181-185` 显式段落；Task 18 承接 |
| 3 | `Project` 路径访问器替代直接拼接 | ⚠️ 部分兑现 | 核心三项是 property；剩余归 Task 18 |

**2/3 完全命中 + 1/3 部分命中且已 plan 后续**。

---

## 二、总体判断

| 维度 | 评价 |
|---|---|
| 三件核心要求的兑现 | **全部命中** |
| 代码与计划的一致性 | 高，测试计数完全一致 |
| 关键测试覆盖 | 好——`restores_paths_after_error` 是真正验证 `try/finally` 语义的关键测试 |
| 残余瑕疵 | 路径访问器还有未整理的死角，但已 plan 到 Task 18 |
| Context manager 质量 | backup/restore 在异常路径下也工作正常 |

**综合 Taste Score**: **Good**（升级达成）

---

## 三、关键代码质量验证

### 3.1 Context manager 真的做了 backup/restore（不是装饰品）

`grading_adapter.py:125-142`：

```python
@contextmanager
def configure_project_designer(project, legacy_root=None):
    root = legacy_root or default_legacy_root()
    designer = _import_legacy_module("views.designer_view", root)
    backup = {
        "_BASE_DIR": designer._BASE_DIR,
        "_LAYOUT_PATH": designer._LAYOUT_PATH,
        "_SAVED_DESIGNS_DIR": designer._SAVED_DESIGNS_DIR,
        "_AUTOSAVE_PATH": designer._AUTOSAVE_PATH,
    }
    try:
        yield _configure_project_designer(project, root)
    finally:
        for name, value in backup.items():
            setattr(designer, name, value)
```

**关键点**：`try/finally` 包住整个 `yield`——不是只保护 yield 成功路径。配合专用测试 `test_configure_project_designer_restores_paths_after_error`（`test_grading_adapter.py:61-74`）：

```python
try:
    with configure_project_designer(session.project) as designer:
        raise RuntimeError("simulated render failure")
except RuntimeError:
    pass
assert designer._LAYOUT_PATH != patched_layout_path  # 还原成功
```

**Linus 视角**：这是对的设计。很多 context manager 写法只在 yield 成功时还原，异常路径漏。`try/finally` 包住 yield 是正确语义。

### 3.2 `configure_project_calibration()` 复用同一模式

`grading_adapter.py:213-234` 完整复用了 backup/restore 模式。Task 17 没有重新发明轮子。**Good taste**——同一类问题用同一类解法。

测试 `test_configure_project_calibration_restores_paths_after_error` 同样验证异常路径还原。

### 3.3 Project dataclass 的 accessors 简洁

`core/project.py:11-36`：

```python
@property
def layout_path(self) -> Path:
    return self.asset_path("layout")

@property
def answers_path(self) -> Path:
    return self.asset_path("answers")

@property
def baseline_path(self) -> Path:
    return self.asset_path("baseline")
```

`frozen=True` dataclass + property + 单一 `asset_path()` 入口。**Linus 会喜欢**——没有特殊分支，路径解析只有一个地方。

### 3.4 迁移退出条件不只是写在 plan 里

`plan.md:181-185`：

> - Task 17 规划前必须明确旧模块迁移路线，不再让"逐步迁移"裸奔。
> - Task 17 起，新功能优先落在 `exam_project` 自有模块；若继续复用同级 `auto_grading_system` 运行时模块，必须在计划中写明延期理由和退出任务编号。
> - 识别、评分、设计器、阅卷视图最终不得依赖同级目录 import 作为长期架构。

并且 Task 18（`plan.md:255-256`）显式承接：

> 1. Task 18 定义旧模块迁移退出条件和路径访问器整理范围。
> 2. 逐步把旧系统识别、评分、设计器、空白校对和阅卷视图从同级目录依赖迁移到 `exam_project` 自有包，并为每项迁移写明退出任务编号。

**Good**——把"逐步"这个空头支票变成了"Task 18 必须定义 deadline"的硬约束。

---

## 四、残余瑕疵（不阻塞）

### 瑕疵 1：`grading_adapter.py` 仍有内联路径

`grading_adapter.py:21-34`：

```python
workdir = project.workdir
data_dir = workdir / "data"
output_dir = data_dir / "output"
processed_dir = data_dir / "processed"
answer_sheets_dir = data_dir / "answer_sheets"
...
return {
    "api_keys": str(workdir / "config" / "api_keys.json"),
    "model_config": str(workdir / "config" / "model_config.json"),
    ...
}
```

**问题**：这些路径规则改一处（比如 `data/` 改成 `runtime/`），调用方需要找 N 处。

**已 plan**：`plan.md:255` 把这件事挪到 Task 18。**可接受**——大头（layout/answers/baseline/design）已经在 `Project` 里，剩下的归并到 Task 18 是合理排期。

### 瑕疵 2：`_import_legacy_module` 修改 `sys.path` 没有还原

`grading_adapter.py:38-42`：

```python
def _import_legacy_module(name, legacy_root):
    root_text = str(legacy_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    return importlib.import_module(name)
```

`sys.path.insert(0, ...)` 是有副作用的进程级状态。当前依赖 `auto_grading_system` 是同级固定路径，影响有限。但**如果未来出现多个 legacy root 或测试隔离需求**，这就是个雷。

**建议**：在 `_import_legacy_module` 外面再叠一层 `@contextmanager`（`with legacy_module_imported(name, root): yield module`），进退时管 `sys.path`。比 context manager for paths 更进一步。

**非阻塞**，等真有第二个 root 时再处理。

### 瑕疵 3：缺少"用户操作路径"复盘

`plan.md:241-251` 最终复盘章节有技术指标（`188 passed`、基础闭环、模块接入），但**没有回答"用户新建项目到首次阅卷需要几步"**这种用户视角的指标。

三轮过去仍然没补。**不阻塞交付**，但确实是用户视角的盲点。

---

## 五、对账结论

### 升级路径完整走通

| 轮次 | Taste Score | 主要贡献 |
|---|---|---|
| Round 1 | So-so | 提出 6 个问题（4 个未解决 + 2 个新增） |
| Round 2 | So-so → 取决于兑现 | 钉住 4 个遗留问题，给出升级条件 |
| Round 3 | **Good** | 2/3 完全兑现 + 1/3 部分兑现且已 plan；Taste 升级达成 |

### 关键工程决策的演进

- **路径访问器演进**：从"散落在 plan 文本里" → "Project 三个核心 property" → "Task 18 接管剩余归并"
- **monkey-patch 演进**：从"裸修改全局" → "@contextmanager + try/finally + 异常路径测试"
- **迁移 deadline 演进**：从"逐步"空头支票 → "迁移退出条件"硬约束 + "Task 18 必须定义"

### 一句话总评

> 两轮 review 提的核心担忧全部在代码层兑现：`@contextmanager` + backup/restore 写得对、测试覆盖了异常路径、`Project` 把三个核心路径收口、`迁移退出条件` 进了 plan。**这是按 review 改的 plan，不是按 plan 编的 review**。
>
> 残余瑕疵是排期问题（Task 18），不是设计问题。

---

## 六、下一轮评审重点

如果还有下一轮（Task 18 完成后），重点验证三件事：

1. **`Project` 路径访问器是否覆盖所有"用户资产路径"**（`saved_designs_dir` / `api_keys_path` / `data_dir` 等），调用方不再有内联 `workdir / "..."`
2. **`_import_legacy_module` 的 `sys.path` 是否纳入 context 管理**（如果届时还在用）
3. **复盘章节是否补"用户操作路径计数"**

如果三件都做到，并且**届时识别/评分模块已经停止 `import auto_grading_system.*` 运行时模块**（Task 18 应该把这个 deadline 钉死），可以考虑 Taste Score 升到 **Good Taste（满分档）**。

---

## 七、参考索引

- 第一轮 review 记录：`review/2026-06-03-plan-review.md`（两轮综合快照）
- 本轮 review：`review/2026-06-03-plan-review-round3.md`（本文）
- 受审计划：`plan.md`
- 关键代码：`src/exam_project/gui/grading_adapter.py`、`src/exam_project/core/project.py`
- 关键测试：`tests/gui/test_grading_adapter.py`
