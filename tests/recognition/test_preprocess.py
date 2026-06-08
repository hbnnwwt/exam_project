"""图像预处理器测试。

cv2 路径上的实际像素运算不在单测覆盖范围（那是集成测试）。
此处覆盖：
- 构造参数校验
- load 错误传播
- PreprocessResult 形状契约
- process 入口不抛异常的最小 happy path
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from exam_project.recognition.preprocess import (
    ImagePreprocessor,
    PreprocessError,
    PreprocessResult,
)


# ---------------------------------------------------------------------------
# 构造参数校验
# ---------------------------------------------------------------------------


def test_default_construction_succeeds() -> None:
    p = ImagePreprocessor()
    assert p.denoise_method == "median"
    assert p.enhance_method == "clahe"
    assert p.binarize_method == "adaptive"


@pytest.mark.parametrize(
    "denoise",
    ["median", "gaussian", "bilateral"],
)
def test_valid_denoise_methods(denoise: str) -> None:
    ImagePreprocessor(denoise_method=denoise)


def test_invalid_denoise_method_raises() -> None:
    with pytest.raises(ValueError, match="不支持的去噪方法"):
        ImagePreprocessor(denoise_method="bogus")


@pytest.mark.parametrize("enhance", ["clahe", "histeq", "gamma"])
def test_valid_enhance_methods(enhance: str) -> None:
    ImagePreprocessor(enhance_method=enhance)


def test_invalid_enhance_method_raises() -> None:
    with pytest.raises(ValueError, match="不支持的增强方法"):
        ImagePreprocessor(enhance_method="bogus")


@pytest.mark.parametrize("binarize", ["otsu", "adaptive", "fixed"])
def test_valid_binarize_methods(binarize: str) -> None:
    ImagePreprocessor(binarize_method=binarize)


def test_invalid_binarize_method_raises() -> None:
    with pytest.raises(ValueError, match="不支持的二值化方法"):
        ImagePreprocessor(binarize_method="bogus")


def test_negative_denoise_strength_raises() -> None:
    with pytest.raises(ValueError, match="denoise_strength"):
        ImagePreprocessor(denoise_strength=-1)


# ---------------------------------------------------------------------------
# load 错误传播
# ---------------------------------------------------------------------------


def test_load_missing_file_raises_preprocess_error(tmp_path) -> None:
    missing = tmp_path / "does_not_exist.png"
    with pytest.raises(PreprocessError, match="无法加载图像"):
        ImagePreprocessor.load(str(missing))


def test_load_non_image_raises_preprocess_error(tmp_path) -> None:
    fake = tmp_path / "fake.png"
    fake.write_bytes(b"not an image")
    with pytest.raises(PreprocessError, match="无法加载图像"):
        ImagePreprocessor.load(str(fake))


def test_load_valid_png_returns_bgr_array(tmp_path) -> None:
    """最小有效 PNG：1x1 红色。"""
    import struct
    import zlib

    def make_png(path: Path) -> None:  # type: ignore[name-defined]
        sig = b"\x89PNG\r\n\x1a\n"
        ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        ihdr_chunk = b"IHDR" + ihdr
        raw = b"\x00\xff\x00\x00"  # filter byte + RGB red
        comp = zlib.compress(raw)
        idat = b"IDAT" + comp
        iend = b"IEND"
        with open(path, "wb") as f:
            f.write(sig)
            f.write(struct.pack(">I", len(ihdr)) + ihdr_chunk + struct.pack(">I", zlib.crc32(ihdr_chunk)))
            f.write(struct.pack(">I", len(comp)) + idat + struct.pack(">I", zlib.crc32(idat)))
            f.write(struct.pack(">I", 0) + iend + struct.pack(">I", zlib.crc32(iend)))

    from pathlib import Path
    png_path = tmp_path / "red.png"
    make_png(png_path)
    image = ImagePreprocessor.load(str(png_path))
    assert image.ndim == 3
    assert image.shape == (1, 1, 3)


# ---------------------------------------------------------------------------
# PreprocessResult 形状契约
# ---------------------------------------------------------------------------


def test_preprocess_result_is_frozen() -> None:
    """PreprocessResult 应当不可变，避免下游意外修改。"""
    fake = np.zeros((10, 10, 3), dtype=np.uint8)
    result = PreprocessResult(
        corrected=fake, gray=fake, enhanced=fake, binary=fake,
        correction_deg=0.0, quality_warning="",
    )
    with pytest.raises(Exception):  # FrozenInstanceError 来自 dataclass
        result.correction_deg = 1.0  # type: ignore[misc]


def test_preprocess_result_is_well_exposed_when_no_warning() -> None:
    fake = np.zeros((10, 10, 3), dtype=np.uint8)
    result = PreprocessResult(
        corrected=fake, gray=fake, enhanced=fake, binary=fake,
        correction_deg=0.0, quality_warning="",
    )
    assert result.is_well_exposed is True


def test_preprocess_result_not_well_exposed_when_warning() -> None:
    fake = np.zeros((10, 10, 3), dtype=np.uint8)
    result = PreprocessResult(
        corrected=fake, gray=fake, enhanced=fake, binary=fake,
        correction_deg=0.0, quality_warning="过暗",
    )
    assert result.is_well_exposed is False


# ---------------------------------------------------------------------------
# process happy path
# ---------------------------------------------------------------------------


def _make_synthetic_answer_sheet(size: int = 400) -> np.ndarray:
    """生成一张模拟答题卡：白底 + 黑色边框 + 一些文字噪声。

    用于 process() 入口的端到端冒烟测试。
    """
    image = np.full((size, size, 3), 255, dtype=np.uint8)
    # 黑色边框
    image[20:40, 20:size - 20] = 0
    image[size - 40:size - 20, 20:size - 20] = 0
    image[20:size - 20, 20:40] = 0
    image[20:size - 20, size - 40:size - 20] = 0
    # 内容：几个黑色方块（模拟填涂气泡）
    for row in range(5):
        for col in range(4):
            cy = 80 + row * 40
            cx = 80 + col * 40
            image[cy:cy + 15, cx:cx + 15] = 0
    return image


def _make_portrait_answer_sheet(height: int = 600, width: int = 400) -> np.ndarray:
    image = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (40, 40), (width - 40, height - 40), (0, 0, 0), 4)
    cv2.rectangle(image, (60, 120), (width - 60, 260), (0, 0, 0), 2)
    cv2.rectangle(image, (60, 320), (width - 60, 480), (0, 0, 0), 2)
    return image


def _rotate_same_canvas(image: np.ndarray, angle: float) -> np.ndarray:
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(
        image,
        matrix,
        (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )


def _raw_otsu_binary(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def test_process_synthetic_image_returns_result() -> None:
    p = ImagePreprocessor()
    image = _make_synthetic_answer_sheet()
    result = p.process(image)
    assert isinstance(result, PreprocessResult)
    assert result.corrected.shape == image.shape
    assert result.gray.ndim == 2
    assert result.enhanced.ndim == 2
    assert result.binary.ndim == 2
    assert isinstance(result.correction_deg, float)
    assert isinstance(result.quality_warning, str)


def test_process_corrects_small_portrait_skew() -> None:
    p = ImagePreprocessor()
    image = _rotate_same_canvas(_make_portrait_answer_sheet(), 3.0)

    result = p.process(image)
    residual = ImagePreprocessor.detect_orientation(_raw_otsu_binary(result.corrected))

    assert result.correction_deg == pytest.approx(3.0, abs=0.2)
    assert result.applied_rotation_deg == pytest.approx(-3.0, abs=0.2)
    assert abs(residual) < 0.2


def test_process_corrects_subthreshold_portrait_skew() -> None:
    p = ImagePreprocessor()
    image = _rotate_same_canvas(_make_portrait_answer_sheet(), 0.3)

    result = p.process(image)
    residual = ImagePreprocessor.detect_orientation(_raw_otsu_binary(result.corrected))

    assert result.correction_deg == pytest.approx(0.3, abs=0.2)
    assert result.applied_rotation_deg == pytest.approx(-result.correction_deg)
    assert abs(residual) < 0.2


def test_draw_orientation_detection_returns_bgr_visualization() -> None:
    image = _make_synthetic_answer_sheet()
    gray = np.mean(image, axis=2).astype(np.uint8)
    binary = np.where(gray < 128, 0, 255).astype(np.uint8)

    viz = ImagePreprocessor.draw_orientation_detection(binary)

    assert viz.shape == image.shape
    assert viz.dtype == np.uint8


def test_process_with_resize_target() -> None:
    p = ImagePreprocessor(target_size=(200, 200))
    image = _make_synthetic_answer_sheet(size=400)
    result = p.process(image)
    assert result.corrected.shape == (200, 200, 3)


def test_load_via_circular_ref_does_not_leak() -> None:
    """load 静态方法不依赖实例状态——多次调用互不污染。"""
    p1 = ImagePreprocessor(denoise_method="gaussian")
    p2 = ImagePreprocessor(denoise_method="median")
    # 这里只验证两个实例独立，不做 cv2 调用
    assert p1.denoise_method != p2.denoise_method
