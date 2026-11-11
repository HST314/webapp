"""把 HPGL / PLT 子集解析成闭合轮廓和内部切割线，坐标统一换算为毫米。"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

_COMMAND_RE = re.compile(r"([A-Z]{2})([^;]*);")
_TOKEN_RE = re.compile(r"[,\s]+")

# 这些命令不参与几何绘制，直接忽略
_IGNORED_COMMANDS = {
    "IN", "PS", "NP", "PC", "SP", "PW", "PG", "LT", "LB",
    "PM", "CI", "EA", "ER", "VS", "FS", "FP", "WU", "TL", "DI",
}


@dataclass
class ParseResult:
    polygons: list[list[tuple[float, float]]] = field(default_factory=list)
    lines: list[list[tuple[float, float]]] = field(default_factory=list)
    ignored: int = 0


def _numbers(text: str) -> list[float]:
    values: list[float] = []
    for token in _TOKEN_RE.split(text.strip()):
        if not token:
            continue
        try:
            values.append(float(token))
        except ValueError:
            # 单个坏数值不应该毁掉整份图纸
            continue
    return values


def parse_plt(content: str, scale: float, close_tol_mm: float) -> ParseResult:
    """解析 PLT 文本。

    scale: 1 个绘图单位对应的毫米数（原脚本为 0.025）。
    close_tol_mm: 首尾点距离小于该值即视为闭合轮廓（原脚本为 2.0）。
    """
    result = ParseResult()
    path: list[tuple[float, float]] = []
    pen_x = 0.0
    pen_y = 0.0
    relative = False

    def finish_path() -> None:
        nonlocal path
        if len(path) >= 3 and math.dist(path[0], path[-1]) <= close_tol_mm:
            result.polygons.append(path)
        elif len(path) >= 2:
            result.lines.append(path)
        path = []

    for cmd, args in _COMMAND_RE.findall(content):
        if cmd == "PR":
            relative = True
        elif cmd == "PA":
            relative = False
        elif cmd == "PU":
            finish_path()
            values = _numbers(args)
            if len(values) >= 2:
                # 多坐标的 PU 取最后一个落点，与原脚本保持一致
                nx, ny = values[-2], values[-1]
                if relative:
                    nx += pen_x
                    ny += pen_y
                pen_x, pen_y = nx, ny
                path = [(pen_x * scale, pen_y * scale)]
        elif cmd == "PD":
            values = _numbers(args)
            # 修复原脚本只处理第一对的问题：PD 后面可能跟多组坐标
            pairs = list(zip(values[0::2], values[1::2]))
            if not path:
                path = [(pen_x * scale, pen_y * scale)]
            for nx, ny in pairs:
                if relative:
                    nx += pen_x
                    ny += pen_y
                pen_x, pen_y = nx, ny
                path.append((pen_x * scale, pen_y * scale))
        elif cmd not in _IGNORED_COMMANDS:
            result.ignored += 1

    finish_path()
    return result
