"""SVG 拼装与 300 DPI PNG 光栅化。"""

from __future__ import annotations

import resvg_py

from .geometry import Garment

CRISP_EDGES = 'shape-rendering="crispEdges"'


def build_svg(garment: Garment, colors: list[str]) -> str:
    """生成单片裁片的 SVG。

    颜色按面片面积从大到小循环取用，与原脚本一致。
    ---
    坐标做了 Y 轴翻转（PLT 的 Y 轴向下），viewBox 同步调整。
    """
    paths: list[str] = []
    color_index = 0
    for piece in garment.pieces:
        color = colors[color_index % len(colors)]
        color_index += 1
        points = " ".join(
            f"{x:.2f},{-y:.2f}" for x, y in piece.exterior.coords
        )
        paths.append(
            f'<polygon points="{points}" fill="{color}" stroke="none" {CRISP_EDGES} />'
        )

    width = garment.width_mm
    height = garment.height_mm
    view_top = -garment.max_y

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width:.2f}" height="{height:.2f}" '
        f'viewBox="{garment.min_x:.2f} {view_top:.2f} {width:.2f} {height:.2f}">\n'
        + "\n".join(paths)
        + "\n</svg>"
    )


def pixel_size(width_mm: float, height_mm: float, dpi: int) -> tuple[int, int]:
    """与原脚本一致，向下取整到整像素。"""
    return (
        max(1, int(width_mm * dpi / 25.4)),
        max(1, int(height_mm * dpi / 25.4)),
    )


def render_png(svg: str, px_w: int, px_h: int) -> bytes:
    return resvg_py.svg_to_bytes(svg_string=svg, width=px_w, height=px_h)


def format_dimension(value_cm: float) -> str:
    """把厘米尺寸格式化成文件名里的整数 / 一位小数。"""
    if abs(value_cm - round(value_cm)) < 0.05:
        return str(int(round(value_cm)))
    return f"{value_cm:.1f}"
