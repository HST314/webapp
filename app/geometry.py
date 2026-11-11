"""裁片分组、切割线分割与内部小块归属。"""

from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.ops import split as split_geometry
from shapely.ops import unary_union

# 切割线两端向外延伸的余量（毫米），避免端点没完全贴合轮廓导致切不开
LINE_EXTEND_MM = 1.0
# 切割线过短会被忽略，避免零长度线触发异常
MIN_LINE_MM = 0.05


@dataclass
class Garment:
    index: int
    pieces: list[Polygon]
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width_mm(self) -> float:
        return self.max_x - self.min_x

    @property
    def height_mm(self) -> float:
        return self.max_y - self.min_y


def shoelace_area(coords: list[tuple[float, float]]) -> float:
    """鞋带公式求面积，单位与坐标一致（mm²）。"""
    area = 0.0
    n = len(coords)
    for i in range(n):
        j = (i + 1) % n
        area += coords[i][0] * coords[j][1]
        area -= coords[j][0] * coords[i][1]
    return abs(area) / 2.0


def _make_polygon(coords: list[tuple[float, float]]) -> tuple[Polygon | None, bool]:
    """构造面片；自相交时用 buffer(0) 修复。返回 (面片, 是否修过)。"""
    try:
        poly = Polygon(coords)
    except Exception:
        return None, True

    if poly.is_empty:
        return None, True
    if poly.is_valid:
        return poly, False

    try:
        fixed = poly.buffer(0)
    except Exception:
        return None, True
    if isinstance(fixed, MultiPolygon):
        if not fixed.geoms:
            return None, True
        fixed = max(fixed.geoms, key=lambda geom: geom.area)
    if fixed.is_empty or fixed.geom_type != "Polygon":
        return None, True
    return fixed, True


def _extend_line(line: LineString, margin: float) -> LineString:
    x0, y0 = line.coords[0]
    x1, y1 = line.coords[-1]
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length <= MIN_LINE_MM:
        return line
    ux, uy = dx / length, dy / length
    return LineString(
        [
            (x0 - ux * margin, y0 - uy * margin),
            (x1 + ux * margin, y1 + uy * margin),
        ]
    )


def build_garments(
    polygons: list[list[tuple[float, float]]],
    lines: list[list[tuple[float, float]]],
    min_area: float,
    min_piece_area: float,
) -> tuple[list[Garment], list[str]]:
    """把轮廓按面积分成主裁片和内部小块，并用切割线把主裁片分割开。"""
    warnings: list[str] = []
    mains: list[dict] = []
    subs: list[Polygon] = []
    repaired = 0
    dropped_sub = 0

    for coords in polygons:
        area = shoelace_area(coords)
        poly, was_repaired = _make_polygon(coords)
        if was_repaired:
            repaired += 1
        if poly is None:
            continue

        if area > min_area:
            xs = [point[0] for point in coords]
            ys = [point[1] for point in coords]
            mains.append(
                {
                    "poly": poly,
                    "min_x": min(xs),
                    "max_x": max(xs),
                    "min_y": min(ys),
                    "max_y": max(ys),
                    "cx": sum(xs) / len(xs),
                    "cy": sum(ys) / len(ys),
                }
            )
        else:
            subs.append(poly)

    if repaired:
        warnings.append(f"{repaired} 个轮廓存在自相交或退化，已自动修复。")

    cutter_lines: list[LineString] = []
    for coords in lines:
        if len(coords) < 2:
            continue
        line = LineString(coords)
        if line.length <= MIN_LINE_MM:
            continue
        cutter_lines.append(line)

    mains.sort(key=lambda item: (round(-item["cy"] / 10.0), item["cx"]))

    garments: list[Garment] = []
    for item in mains:
        main_poly: Polygon = item["poly"]
        pieces: list[Polygon] = [main_poly]

        # 把落在该裁片上的切割线合并成一张“切割网”，一次性切开。
        # 单根线经常只是网络中的一段（两端都在内部），逐根切会切不动。
        relevant_lines = [
            line for line in cutter_lines if main_poly.intersects(line)
        ]
        if relevant_lines:
            network = unary_union(
                [_extend_line(line, LINE_EXTEND_MM) for line in relevant_lines]
            )
            try:
                parts = list(split_geometry(main_poly, network).geoms)
            except Exception:
                parts = []
            split_pieces = [
                geom
                for geom in parts
                if geom.geom_type == "Polygon" and not geom.is_empty
            ]
            if len(split_pieces) > 1:
                pieces = split_pieces

        for sub in subs:
            if main_poly.contains(sub):
                pieces.append(sub)

        kept_pieces = [piece for piece in pieces if piece.area >= min_piece_area]
        dropped_sub += len(pieces) - len(kept_pieces)
        if not kept_pieces:
            continue

        kept_pieces.sort(key=lambda piece: piece.area, reverse=True)
        garments.append(
            Garment(
                index=len(garments),
                pieces=kept_pieces,
                min_x=item["min_x"],
                min_y=item["min_y"],
                max_x=item["max_x"],
                max_y=item["max_y"],
            )
        )

    if dropped_sub:
        warnings.append(f"{dropped_sub} 个面片小于碎块阈值，未导出。")
    return garments, warnings
