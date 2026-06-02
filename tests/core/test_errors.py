from exam_project.core.errors import ProjectError, ProjectValidationError


def test_project_error_keeps_user_message():
    err = ProjectError("项目无法打开")
    assert str(err) == "项目无法打开"
    assert err.user_message == "项目无法打开"


def test_validation_error_records_code():
    err = ProjectValidationError("参考答案与布局不一致", code="answer_layout_mismatch")
    assert err.code == "answer_layout_mismatch"
    assert err.user_message == "参考答案与布局不一致"
