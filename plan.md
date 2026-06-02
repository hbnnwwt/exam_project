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

## 审查记录

- Task 3 已完成规格审查和代码质量审查；manifest 输入边界收紧为严格 JSON dict/list，资产路径和资产键均拒绝空白边界。
- Task 4 已完成规格审查和代码质量审查；checksum 使用 SHA-256 分块读取，资产路径复用 manifest 安全校验。

## 后续计划

1. 项目包 foundation 实现完成后，再写答题卡设计器迁移计划。
2. 设计器迁移完成后，再写识别、评分、空白标定迁移计划。
3. 最后写 Streamlit 项目工作流计划。
