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

## 最终复盘

- 已完成 `.examproj` foundation：manifest、checksum、安全 ZIP 打包/打开/保存、运行期项目对象、业务校验、完整打开前验证、旧系统资产导入和 CLI。
- 旧系统真实根目录的 `config/sheet_layout.json` 与根目录 `参考答案.xlsx` 本身错配；新导入器会拒绝这种坏组合，这是正确行为，不应绕过校验。
- 当前阶段没有迁移答题卡设计器 UI、识别流水线、评分 UI、空白页校对工作流；这些属于后续阶段。

## 后续计划

1. 项目包 foundation 实现完成后，再写答题卡设计器迁移计划。
2. 设计器迁移完成后，再写识别、评分、空白标定迁移计划。
3. 最后写 Streamlit 项目工作流计划。
