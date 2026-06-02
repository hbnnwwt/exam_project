import exam_project
import exam_project.core


def test_package_imports():
    assert exam_project.__version__ == "0.1.0"
    assert exam_project.core is not None
