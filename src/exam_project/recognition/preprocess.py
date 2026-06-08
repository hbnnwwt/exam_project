"""答题卡图像预处理。

负责方向矫正、去噪、对比度增强、二值化，输出供版面分析使用的二值图。

设计要点：
- 图像加载走 cv2.imdecode + np.fromfile，兼容 Windows 中文路径
- 方向检测采用 minAreaRect + 上下密度比，支持任意角度（不限于 90° 整数倍）
- 主入口 process() 返回 dataclass 结果，副作用（矫正角度、质量警告）也包含在结果里
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from .constants import MORPH_KERNEL


# 防止超大图像触发 OOM
MAX_DIMENSION = 8000

# 方向判定时二值图最大轮廓占图面积的下限，低于此视为无内容（不参与方向判定）
MIN_CONTOUR_AREA_RATIO = 0.03

# 上下密度比阈值：底部密度 > 顶部 × 此系数 → 视为倒置
INVERT_DENSITY_RATIO = 1.2

# 上下密度绝对下限：低于此值视为内容过少、不可靠
INVERT_MIN_BOTTOM_DENSITY = 0.005

class PreprocessError(Exception):
    """图像加载或预处理失败。"""


@dataclass(frozen=True)
class PreprocessResult:
    """单次预处理的完整结果。

    Attributes:
        corrected: 方向矫正后的 BGR 图像
        gray: 去噪后的灰度图
        enhanced: 对比度增强后的灰度图
        binary: 二值化后的图（黑底白内容/或反之，由方法决定）
        correction_deg: 检测到的页面倾斜角（度，逆时针为正）
        applied_rotation_deg: 实际应用到图像上的旋转角（派生属性）
        quality_warning: 扫描质量警告文本。无问题则为空串
    """

    corrected: np.ndarray
    gray: np.ndarray
    enhanced: np.ndarray
    binary: np.ndarray
    correction_deg: float
    quality_warning: str

    @property
    def is_well_exposed(self) -> bool:
        return not self.quality_warning

    @property
    def applied_rotation_deg(self) -> float:
        if abs(self.correction_deg) <= 1e-6:
            return 0.0
        return -self.correction_deg


class ImagePreprocessor:
    """答题卡图像预处理器。

    构造时接受方法选择，process() 返回 PreprocessResult。
    不在实例上保存中间图像——单次处理的结果完全封装在返回值里。
    """

    def __init__(
        self,
        denoise_method: str = "median",
        denoise_strength: int = 2,
        enhance_method: str = "clahe",
        binarize_method: str = "adaptive",
        target_size: Optional[tuple[int, int]] = None,
    ) -> None:
        if denoise_method not in ("gaussian", "median", "bilateral"):
            raise ValueError(f"不支持的去噪方法: {denoise_method}")
        if enhance_method not in ("clahe", "histeq", "gamma"):
            raise ValueError(f"不支持的增强方法: {enhance_method}")
        if binarize_method not in ("otsu", "adaptive", "fixed"):
            raise ValueError(f"不支持的二值化方法: {binarize_method}")
        if denoise_strength < 0:
            raise ValueError("denoise_strength 必须 >= 0")

        self.denoise_method = denoise_method
        self.denoise_strength = denoise_strength
        self.enhance_method = enhance_method
        self.binarize_method = binarize_method
        self.target_size = target_size

    # ------------------------------------------------------------------ load

    @staticmethod
    def load(path: str) -> np.ndarray:
        """加载图像文件，兼容含中文/特殊字符的路径。

        Args:
            path: 图像文件绝对路径

        Returns:
            BGR numpy 数组

        Raises:
            PreprocessError: 路径不存在或文件不可读
        """
        try:
            buf = np.fromfile(path, dtype=np.uint8)
        except (FileNotFoundError, OSError) as exc:
            raise PreprocessError(f"无法加载图像: {path}") from exc
        image = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if image is None:
            raise PreprocessError(f"无法加载图像: {path}")
        ImagePreprocessor._warn_if_too_large(image)
        return image

    @staticmethod
    def _warn_if_too_large(image: np.ndarray) -> None:
        h, w = image.shape[:2]
        if max(h, w) > MAX_DIMENSION:
            warnings.warn(
                f"图像尺寸 {w}x{h} 超过 {MAX_DIMENSION} 像素，"
                f"内存占用约 {h * w * 3 / 1024 / 1024:.0f}MB",
                stacklevel=2,
            )

    # --------------------------------------------------------------- resize

    def resize(self, image: np.ndarray) -> np.ndarray:
        if self.target_size is None:
            return image
        tw, th = self.target_size
        h, w = image.shape[:2]
        if w != tw or h != th:
            return cv2.resize(image, (tw, th))
        return image

    # -------------------------------------------------------- orientation

    @staticmethod
    def _detect_with_contour(
        binary: np.ndarray,
    ) -> tuple[float, Optional[np.ndarray], Optional[tuple]]:
        """Return orientation angle together with the contour evidence."""
        inv = 255 - binary
        contours, _ = cv2.findContours(
            inv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if not contours:
            return 0.0, None, None
        largest = max(contours, key=cv2.contourArea)
        if cv2.contourArea(largest) < binary.size * MIN_CONTOUR_AREA_RATIO:
            return 0.0, None, None

        rect = cv2.minAreaRect(largest)
        (_, (w, h), angle) = rect

        if binary.shape[0] >= binary.shape[1]:
            correction = ImagePreprocessor._small_skew_correction(angle)
            bh, bw = binary.shape
            top = np.sum(binary[: bh // 5, :] == 0) / max(bh // 5 * bw, 1)
            bot = np.sum(binary[4 * bh // 5 :, :] == 0) / max(
                (bh - 4 * bh // 5) * bw, 1
            )
            if bot > top * INVERT_DENSITY_RATIO and bot > INVERT_MIN_BOTTOM_DENSITY:
                return ImagePreprocessor._normalize_correction(180.0 + correction), largest, rect
            return correction, largest, rect
        else:
            tilt = angle + 90.0
            rotated = cv2.rotate(binary, cv2.ROTATE_90_CLOCKWISE)
            rh, rw = rotated.shape
            top = np.sum(rotated[: rh // 5, :] == 0) / max(rh // 5 * rw, 1)
            bot = np.sum(rotated[4 * rh // 5 :, :] == 0) / max(
                (rh - 4 * rh // 5) * rw, 1
            )
            if bot > top * INVERT_DENSITY_RATIO and bot > INVERT_MIN_BOTTOM_DENSITY:
                return -90.0 - tilt, largest, rect
            return 90.0 - tilt, largest, rect

    @staticmethod
    def _small_skew_correction(angle: float) -> float:
        skew = angle + 90.0 if angle < -45.0 else angle
        return -skew

    @staticmethod
    def _normalize_correction(angle: float) -> float:
        while angle > 180.0:
            angle -= 360.0
        while angle <= -180.0:
            angle += 360.0
        return angle

    @staticmethod
    def _detect_orientation(binary: np.ndarray) -> float:
        """检测图像需要旋转的角度（度，逆时针为正）。"""
        angle, _, _ = ImagePreprocessor._detect_with_contour(binary)
        return angle

    @staticmethod
    def detect_orientation(binary: np.ndarray) -> float:
        return ImagePreprocessor._detect_orientation(binary)

    @staticmethod
    def draw_orientation_detection(binary: np.ndarray) -> np.ndarray:
        """Draw the contour/minAreaRect evidence used for orientation correction."""
        angle, contour, rect = ImagePreprocessor._detect_with_contour(binary)
        viz = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)

        if contour is not None:
            cv2.drawContours(viz, [contour], -1, (0, 200, 0), 2)
        if rect is not None:
            box = np.intp(cv2.boxPoints(rect))
            cv2.drawContours(viz, [box], -1, (0, 100, 255), 2)
            cx, cy = int(rect[0][0]), int(rect[0][1])
            cv2.putText(
                viz,
                f"{angle:+.1f} deg",
                (cx - 60, cy - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (0, 100, 255),
                2,
                cv2.LINE_AA,
            )
        return viz

    # -------------------------------------------------------------- denoise

    def _denoise(self, image: np.ndarray) -> np.ndarray:
        gray = (
            cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            if image.ndim == 3
            else image
        )
        if self.denoise_method == "gaussian":
            k = self.denoise_strength * 2 + 1
            return cv2.GaussianBlur(gray, (k, k), 0)
        if self.denoise_method == "median":
            return cv2.medianBlur(gray, self.denoise_strength * 2 + 1)
        # bilateral
        return cv2.bilateralFilter(gray, 9, 75, 75)

    # -------------------------------------------------------------- enhance

    def _enhance(self, gray: np.ndarray) -> np.ndarray:
        if self.enhance_method == "clahe":
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            return clahe.apply(gray)
        if self.enhance_method == "histeq":
            return cv2.equalizeHist(gray)
        # gamma
        inv = 255.0 / gray.max() if gray.max() > 0 else 1
        norm = (gray * inv).astype(np.uint8)
        return (np.power(norm / 255.0, 0.8) * 255).astype(np.uint8)

    # ------------------------------------------------------------ binarize

    def _binarize(self, gray: np.ndarray) -> np.ndarray:
        if self.binarize_method == "otsu":
            _, binary = cv2.threshold(
                gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
        elif self.binarize_method == "adaptive":
            binary = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, 11, 2,
            )
        else:
            _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
        # 开运算去除 1-2px 孤立点
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, MORPH_KERNEL)
        return cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

    # -------------------------------------------------------------- quality

    @staticmethod
    def _quality_warning(binary: np.ndarray) -> str:
        white_ratio = np.sum(binary == 255) / binary.size
        if white_ratio > 0.98:
            return "图像过暗：二值化后几乎全黑，扫描可能曝光不足"
        if white_ratio < 0.02:
            return "图像过亮：二值化后几乎全白，扫描可能曝光过度"
        return ""

    # ----------------------------------------------------------------- main

    def process(self, image: np.ndarray) -> PreprocessResult:
        """完整预处理管线：缩放 → 方向矫正 → 去噪 → 增强 → 二值化。

        Args:
            image: BGR numpy 数组（通常来自 self.load）

        Returns:
            PreprocessResult 包含各阶段产物和方向矫正角度
        """
        image = self.resize(image)
        gray_raw = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, binary_raw = cv2.threshold(
            gray_raw, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        quality_warning = self._quality_warning(binary_raw)

        correction = self._detect_orientation(binary_raw)

        if abs(correction) > 1e-6:
            h, w = image.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, -correction, 1.0)
            image = cv2.warpAffine(
                image, M, (w, h),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_REPLICATE,
            )

        gray = self._denoise(image)
        enhanced = self._enhance(gray)
        binary = self._binarize(enhanced)

        return PreprocessResult(
            corrected=image,
            gray=gray,
            enhanced=enhanced,
            binary=binary,
            correction_deg=correction,
            quality_warning=quality_warning,
        )

    # ---------------------------------------------- edge extraction (static)

    @staticmethod
    def extract_vertical_edges(
        gray: np.ndarray,
        min_height_ratio: float = 0.05,
        min_area: int = 20,
    ) -> np.ndarray:
        """提取增强后的灰度图中的垂直线（用于版面分析）。

        流程：高斯去噪 → Sobel X → OTSU → 连通区域高度过滤 → 闭运算
        """
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        sobel_x = cv2.Sobel(blurred, cv2.CV_64F, 1, 0, ksize=3)
        sobel_x = np.abs(sobel_x)
        sobel_x = np.uint8(255 * sobel_x / (sobel_x.max() + 1e-6))
        _, sobel_bin = cv2.threshold(
            sobel_x, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        h, w = sobel_bin.shape
        min_height = int(h * min_height_ratio)
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
            sobel_bin, connectivity=8
        )
        mask = np.zeros_like(sobel_bin)
        for i in range(1, num_labels):
            x, y, bw, bh, area = stats[i]
            if bh >= min_height and area >= min_area:
                mask[labels == i] = 255

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 7))
        return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    @staticmethod
    def extract_horizontal_edges(
        gray: np.ndarray,
        min_width_ratio: float = 0.05,
        min_area: int = 20,
    ) -> np.ndarray:
        """水平线提取，对称于 vertical 版本。"""
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        sobel_y = cv2.Sobel(blurred, cv2.CV_64F, 0, 1, ksize=3)
        sobel_y = np.abs(sobel_y)
        sobel_y = np.uint8(255 * sobel_y / (sobel_y.max() + 1e-6))
        _, sobel_bin = cv2.threshold(
            sobel_y, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        h, w = sobel_bin.shape
        min_width = int(w * min_width_ratio)
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
            sobel_bin, connectivity=8
        )
        mask = np.zeros_like(sobel_bin)
        for i in range(1, num_labels):
            x, y, bw, bh, area = stats[i]
            if bw >= min_width and area >= min_area:
                mask[labels == i] = 255

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 3))
        return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
