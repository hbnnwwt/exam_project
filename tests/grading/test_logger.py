"""logger 测试。"""

from __future__ import annotations

import logging
from pathlib import Path

from exam_project.grading.logger import get_logger


def test_get_logger_returns_named_logger() -> None:
    log = get_logger("test_module")
    assert log.name == "test_module"
    assert isinstance(log, logging.Logger)


def test_get_logger_is_singleton() -> None:
    log1 = get_logger("same_name")
    log2 = get_logger("same_name")
    assert log1 is log2


def test_get_logger_with_file_handler(tmp_path: Path) -> None:
    log_path = tmp_path / "test.log"
    log = get_logger("test_with_file", str(log_path))
    log.info("hello world")
    # flush handlers
    for handler in log.handlers:
        handler.flush()
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "hello world" in content
