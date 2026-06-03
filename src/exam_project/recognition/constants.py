"""识别层常量。

集中管理识别算法所需的全部阈值、形态学核尺寸、合法文件后缀等。
不存任何模块级可变状态——纯常量。

子模块不直接 import 本文件的字段名（应通过 from .constants import X 显式引用），
便于后续重构为可配置项。
"""

from __future__ import annotations

import os
import re
from typing import Iterable


# ============================================================================
# API 默认值
# ============================================================================

DEFAULT_BASE_URL = "https://api-inference.modelscope.cn"
DEFAULT_LLM_MODEL = "Qwen/Qwen3-235B-A22B"
DEFAULT_OCR_MODEL = "Qwen/Qwen3-VL-235B-A22B-Instruct"


# ============================================================================
# 通用图像处理
# ============================================================================

MORPH_KERNEL = (3, 3)
FILL_BAND_THRESHOLD = 0.02

IMAGE_EXTS: frozenset[str] = frozenset(
    {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif"}
)


def is_image_file(path: str | os.PathLike) -> bool:
    """判断文件路径是否属于支持的图像格式。"""
    return os.path.splitext(str(path))[1].lower() in IMAGE_EXTS


# ============================================================================
# 判断题识别常量
# ============================================================================

JUDGE_MIN_FILL = 0.05           # 填涂检测最低填充率
JUDGE_STAIN_FILL_LOW = 0.04     # 污渍检测-填充率极低（淡铅笔可低至 4~5%）
JUDGE_STAIN_FILL_HIGH = 0.07    # 污渍检测-填充率较低
JUDGE_STAIN_RATIO = 0.80        # 污渍检测-对称率阈值
JUDGE_VALID_RATIO = 0.92        # 有效填涂-不对称率阈值
JUDGE_MULTI_FILL = 0.10         # 多选检测-单侧最低填充率
JUDGE_MULTI_RATIO = 0.85        # 多选检测-对称率阈值
JUDGE_BLOB_AREA_MIN = 100       # 气泡最小面积
JUDGE_BLOB_AREA_MAX = 3000      # 气泡最大面积
JUDGE_BLOB_ASPECT_MIN = 0.4     # 气泡最小宽高比
JUDGE_BLOB_ASPECT_MAX = 2.5     # 气泡最大宽高比
JUDGE_SIDE_MARGIN_RATIO = 0.10  # 侧边距比例
JUDGE_VERT_MARGIN_RATIO = 0.15  # 上下边距比例


# ============================================================================
# 排序辅助
# ============================================================================

def natural_sort_key(path: str | os.PathLike) -> list:
    """提取文件名中的数字用于自然排序。

    例如：kaojuan_10.png -> ['kaojuan_', 10, '.png']
          kaojuan_100.png -> ['kaojuan_', 100, '.png']
    确保 3,4,5...9,10,11... 的顺序正确，而非字典序的 10,100,101...11。
    """
    filename = os.path.basename(str(path))
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(r"(\d+)", filename)]


def sorted_image_paths(paths: Iterable[str | os.PathLike]) -> list[str]:
    """按自然数顺序排序图像文件路径。"""
    return sorted(paths, key=natural_sort_key)
