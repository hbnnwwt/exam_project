"""统一日志配置。

教学注释：
  生产代码用 logging 而非 print()，因为：
  1. 可按级别过滤（DEBUG/INFO/WARNING/ERROR）
  2. 可同时输出到控制台和文件
  3. 自动附带时间戳、模块名等上下文
"""

from __future__ import annotations

import logging
import sys
from typing import Optional


def get_logger(name: str, log_file: Optional[str] = None) -> logging.Logger:
    """获取配置好的 logger。

    Args:
        name: 通常用 __name__，日志中会显示模块名
        log_file: 可选，日志文件路径。为 None 时只输出到控制台。

    Returns:
        已配置好 handler 的 logger 实例
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # 控制台：INFO 及以上
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    logger.addHandler(console)

    # 文件（可选）：DEBUG 及以上
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    return logger
