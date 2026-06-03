"""Exam project 识别核心。

从零构建的答题卡识别模块集合。不依赖 auto_grading_system 任何源码。

子模块：
- types: 识别结果统一数据结构
- constants: 识别算法所需的全部常量
- preprocess: 图像预处理（矫正、二值化、版面分析前序）
- layout: 答题卡版面区域定位
- bubble_base: 选择题/判断题气泡识别基类
- choice: 选择题识别
- judge: 判断题识别
- essay: 简答题识别（本地 OCR + 在线 OCR/LLM）
- student_id: 学号识别
- blank_calibrator: 空白答题卡基准标定
"""
