"""Exam project 评分核心。

从零构建的评分模块集合。不依赖 auto_grading_system 任何源码。

子模块：
- logger: 统一日志配置
- defaults: 模型配置默认值
- config_validator: 配置文件完整性校验
- pipeline: 识别管线编排
- grading: 评分逻辑
- llm_grader: LLM 评分（简答题主观题）
"""
