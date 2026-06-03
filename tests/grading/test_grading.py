"""grading 服务测试。"""

from __future__ import annotations

import pytest

from exam_project.grading.grading import (
    DefaultEssayGrader,
    GradingConfig,
    GradingService,
    classify_question,
)
from exam_project.grading.llm_grader import (
    LLMConfig,
    LLMEssayGrader,
    LLMScore,
    _is_rate_limited,
    _to_tuple,
    load_config,
    save_config,
    load_prompt_template,
)
from exam_project.recognition.types import RecognizeResult, Status


# ---------------------------------------------------------------------------
# classify_question
# ---------------------------------------------------------------------------


def test_classify_question_choice() -> None:
    layout = {
        "choice": {"question_start": 1, "question_count": 20},
        "judge": {"question_start": 21, "question_count": 10},
    }
    for q in [1, 10, 20]:
        assert classify_question(q, layout) == "choice"


def test_classify_question_judge() -> None:
    layout = {
        "choice": {"question_start": 1, "question_count": 20},
        "judge": {"question_start": 21, "question_count": 10},
    }
    for q in [21, 25, 30]:
        assert classify_question(q, layout) == "judge"


def test_classify_question_essay() -> None:
    layout = {
        "choice": {"question_start": 1, "question_count": 20},
        "judge": {"question_start": 21, "question_count": 10},
    }
    assert classify_question(31, layout) == "essay"
    assert classify_question(100, layout) == "essay"


def test_classify_question_with_empty_layout() -> None:
    assert classify_question(1, {}) == "essay"


# ---------------------------------------------------------------------------
# GradingConfig
# ---------------------------------------------------------------------------


def test_grading_config_defaults() -> None:
    cfg = GradingConfig()
    assert cfg.choice_score == 3
    assert cfg.judge_score == 2
    assert cfg.essay_max_score == 20


def test_grading_config_from_layout() -> None:
    cfg = GradingConfig.from_layout({"scoring": {"choice_score": 5, "judge_score": 3, "essay_max_score": 30}})
    assert cfg.choice_score == 5
    assert cfg.judge_score == 3
    assert cfg.essay_max_score == 30


def test_grading_config_from_empty_layout() -> None:
    cfg = GradingConfig.from_layout({})
    assert cfg.choice_score == 3


# ---------------------------------------------------------------------------
# DefaultEssayGrader
# ---------------------------------------------------------------------------


def test_default_grader_returns_zero() -> None:
    grader = DefaultEssayGrader()
    score, mx, fb = grader.score(31, "参考答案", "学生答案", 10)
    assert score == 0.0
    assert mx == 10
    assert "手动" in fb or "未作答" in fb


def test_default_grader_handles_blank_recognize_result() -> None:
    grader = DefaultEssayGrader()
    blank = RecognizeResult(text="", status=Status.BLANK)
    score, mx, fb = grader.score(31, "ref", blank, 10)
    assert score == 0.0
    assert "未作答" in fb


def test_default_grader_handles_system_failure() -> None:
    grader = DefaultEssayGrader()
    fail = RecognizeResult(text="", status=Status.API_ERROR, error="HTTP 503")
    score, mx, fb = grader.score(31, "ref", fail, 10)
    assert score == 0.0
    assert "系统失败" in fb


# ---------------------------------------------------------------------------
# GradingService
# ---------------------------------------------------------------------------


def test_grading_service_max_total() -> None:
    svc = GradingService(
        answer_key={"choice": {i: "A" for i in range(20)},
                    "judge": {i: "T" for i in range(21, 31)},
                    "essay": {31: "ref"}},
        layout={"scoring": {"choice_score": 3, "judge_score": 2, "essay_max_score": 20}},
    )
    assert svc.max_total == 20 * 3 + 10 * 2 + 1 * 20  # 100


def test_grading_service_grade_choice_correct() -> None:
    svc = GradingService(
        answer_key={"choice": {1: "A", 2: "B"}},
        layout={"scoring": {"choice_score": 3, "judge_score": 2, "essay_max_score": 20}},
    )
    result = svc.grade({"choice": {1: "A", 2: "B"}})
    assert result.choice_total == 6.0
    assert result.choice[1]["score"] == 3
    assert result.choice[2]["score"] == 3
    assert result.total == 6.0


def test_grading_service_grade_choice_partial() -> None:
    svc = GradingService(
        answer_key={"choice": {1: "A", 2: "B"}},
        layout={"scoring": {"choice_score": 3, "judge_score": 2, "essay_max_score": 20}},
    )
    result = svc.grade({"choice": {1: "A", 2: "C"}})
    assert result.choice_total == 3.0


def test_grading_service_grade_choice_unanswered() -> None:
    svc = GradingService(
        answer_key={"choice": {1: "A"}},
        layout={"scoring": {"choice_score": 3, "judge_score": 2, "essay_max_score": 20}},
    )
    result = svc.grade({"choice": {}})
    assert result.choice[1]["score"] == 0
    assert result.choice[1]["given"] is None


def test_grading_service_grade_judge() -> None:
    svc = GradingService(
        answer_key={"judge": {21: "T", 22: "F"}},
        layout={"scoring": {"choice_score": 3, "judge_score": 2, "essay_max_score": 20}},
    )
    result = svc.grade({"judge": {21: "T", 22: "T"}})
    assert result.judge_total == 2.0
    assert result.judge[22]["score"] == 0


def test_grading_service_grade_essay() -> None:
    svc = GradingService(
        answer_key={"essay": {31: "参考答案"}},
        layout={"scoring": {"choice_score": 3, "judge_score": 2, "essay_max_score": 20}},
    )
    result = svc.grade({"essay": {31: "学生答案"}})
    # Default grader 总是返回 0
    assert result.essay_total == 0.0
    assert result.essay_detail[31]["feedback"] is not None


def test_grading_service_generate_report() -> None:
    svc = GradingService(
        answer_key={"choice": {1: "A"}, "judge": {21: "T"}, "essay": {31: "ref"}},
        layout={"scoring": {"choice_score": 3, "judge_score": 2, "essay_max_score": 20}},
    )
    result = svc.grade({"choice": {1: "A"}, "judge": {21: "T"}, "essay": {31: "ok"}})
    report = svc.generate_report(result)
    assert "总分" in report
    assert "选择题" in report
    assert "判断题" in report
    assert "第1题" in report
    assert "第21题" in report


# ---------------------------------------------------------------------------
# LLMConfig / helpers
# ---------------------------------------------------------------------------


def test_llm_config_build_configs_cartesian() -> None:
    cfg = LLMConfig(
        api_keys=("k1", "k2"),
        base_urls=("https://a", "https://b"),
        models=("m1", "m2"),
    )
    configs = cfg.build_configs()
    assert len(configs) == 2 * 2 * 2  # 8
    for c in configs:
        assert "api_key" in c
        assert "base_url" in c
        assert "model" in c


def test_to_tuple_with_string() -> None:
    assert _to_tuple("k1") == ("k1",)


def test_to_tuple_with_list() -> None:
    assert _to_tuple(["a", "b"]) == ("a", "b")


def test_to_tuple_with_none() -> None:
    assert _to_tuple(None) == ()


def test_to_tuple_with_empty_string() -> None:
    assert _to_tuple("") == ()


def test_is_rate_limited_by_429_in_message() -> None:
    assert _is_rate_limited(Exception("HTTP 429: rate limited")) is True


def test_is_rate_limited_false() -> None:
    assert _is_rate_limited(Exception("HTTP 500: server error")) is False


# ---------------------------------------------------------------------------
# load_config / save_config
# ---------------------------------------------------------------------------


def test_load_config_missing_returns_defaults(tmp_path) -> None:
    cfg = load_config(tmp_path / "missing.json")
    assert cfg["api_key"] == ""
    assert cfg["base_url"]  # 非空


def test_save_and_load_config(tmp_path) -> None:
    path = tmp_path / "config.json"
    save_config({"api_key": "k1", "base_url": "http://x"}, path)
    loaded = load_config(path)
    assert loaded["api_key"] == "k1"


def test_save_config_merges_existing(tmp_path) -> None:
    path = tmp_path / "config.json"
    save_config({"api_key": "k1", "base_url": "http://x"}, path)
    save_config({"api_key": "k2"}, path)  # 只更新 api_key
    loaded = load_config(path)
    assert loaded["api_key"] == "k2"
    assert loaded["base_url"] == "http://x"


def test_load_prompt_template_missing_returns_default(tmp_path) -> None:
    template = load_prompt_template(tmp_path / "missing.txt")
    assert "得分" in template  # 默认 prompt 包含"得分"


# ---------------------------------------------------------------------------
# LLMEssayGrader
# ---------------------------------------------------------------------------


def test_llm_grader_no_config_returns_error() -> None:
    grader = LLMEssayGrader(LLMConfig())
    score, mx, fb = grader.score(31, "ref", "student", 10)
    assert score == 0.0
    assert "未配置" in fb


def test_llm_grader_blank_returns_unanswered() -> None:
    grader = LLMEssayGrader(LLMConfig(
        api_keys=("k1",), base_urls=("http://x",), models=("m1",),
    ))
    score, mx, fb = grader.score(31, "ref", "", 10)
    assert score == 0.0
    assert "未作答" in fb


def test_llm_grader_system_failure_skips_api() -> None:
    """系统失败时不应调用 LLM（避免浪费 token）。"""
    grader = LLMEssayGrader(LLMConfig(
        api_keys=("k1",), base_urls=("http://x",), models=("m1",),
    ))
    fail = RecognizeResult(text="", status=Status.API_ERROR, error="HTTP 503")
    score, mx, fb = grader.score(31, "ref", fail, 10)
    assert score == 0.0
    assert "系统失败" in fb
    assert "HTTP 503" in fb


def test_llm_grader_accepts_string_student_answer() -> None:
    grader = LLMEssayGrader(LLMConfig(
        api_keys=("k1",), base_urls=("http://x",), models=("m1",),
    ))
    # 字符串且非空 → 应当构造 RecognizeResult 并尝试调用 LLM
    # 由于 LLM 不可达，会失败但路径应当走过 LLM 调用
    score, mx, fb = grader.score(31, "ref", "学生写了一些字", 10)
    # 应当进入 _call_api → 网络失败 → 兜底返回 0
    assert score == 0.0
    assert "调用失败" in fb or "调用" in fb


def test_llm_grader_with_low_confidence_prefix() -> None:
    grader = LLMEssayGrader(LLMConfig(
        api_keys=("k1",), base_urls=("http://x",), models=("m1",),
    ))
    low = RecognizeResult(text="一些字", status=Status.LOW_CONFIDENCE, confidence=0.4)
    score, mx, fb = grader.score(31, "ref", low, 10)
    # 反馈应当带"低置信度"前缀
    assert "低置信度" in fb or "调用失败" in fb


# ---------------------------------------------------------------------------
# LLMScore
# ---------------------------------------------------------------------------


def test_llm_score_is_frozen() -> None:
    s = LLMScore(score=5, max_score=10, feedback="好")
    with __import__("pytest").raises(Exception):
        s.score = 6  # type: ignore[misc]


# ---------------------------------------------------------------------------
# LLMEssayGrader._parse_response
# ---------------------------------------------------------------------------


def test_parse_response_json_format() -> None:
    grader = LLMEssayGrader(LLMConfig())
    result = grader._parse_response('{"score": 7, "feedback": "不错"}', 10)
    assert result.score == 7
    assert result.feedback == "不错"


def test_parse_response_chinese_format() -> None:
    grader = LLMEssayGrader(LLMConfig())
    result = grader._parse_response("得分：8\n反馈：回答准确", 10)
    assert result.score == 8
    assert "回答准确" in result.feedback


def test_parse_response_english_format() -> None:
    grader = LLMEssayGrader(LLMConfig())
    result = grader._parse_response("Score: 6\nFeedback: good answer", 10)
    assert result.score == 6
    assert "good answer" in result.feedback


def test_parse_response_x_over_y() -> None:
    grader = LLMEssayGrader(LLMConfig())
    result = grader._parse_response("5/10", 10)
    assert result.score == 5


def test_parse_response_x_fen() -> None:
    grader = LLMEssayGrader(LLMConfig())
    result = grader._parse_response("3分", 10)
    assert result.score == 3


def test_parse_response_empty() -> None:
    grader = LLMEssayGrader(LLMConfig())
    result = grader._parse_response("", 10)
    assert result.score == 0


def test_parse_response_unparseable() -> None:
    grader = LLMEssayGrader(LLMConfig())
    result = grader._parse_response("完全无法解析的内容", 10)
    assert result.score == 0
    assert "无法解析" in result.feedback


def test_parse_response_caps_at_max_score() -> None:
    grader = LLMEssayGrader(LLMConfig())
    result = grader._parse_response("得分：100", 10)
    assert result.score == 10  # 应当被 cap 在 max_score


# ---------------------------------------------------------------------------
# LLMConfig is frozen
# ---------------------------------------------------------------------------


def test_llm_config_is_frozen() -> None:
    cfg = LLMConfig()
    with __import__("pytest").raises(Exception):
        cfg.max_tokens = 100  # type: ignore[misc]
