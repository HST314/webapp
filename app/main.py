"""FastAPI 入口：一次请求完成解析、填色与打包。"""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .geometry import Garment, build_garments
from .plt_parser import parse_plt
from .renderer import build_svg, format_dimension, pixel_size, render_png

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

DEFAULT_COLORS = ["#CCCCFF", "#FF9933", "#00CCFF", "#99CCCC", "#CCFFCC"]

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
# multipart 边界、表单项会额外占几十 KB
MAX_REQUEST_BYTES = 25 * 1024 * 1024
MAX_GARMENTS = 200
MAX_COLORS = 24
# 单张 / 整批输出像素上限，避免高 DPI + 大图纸把内存打爆
MAX_PIXELS_PER_IMAGE = 120_000_000
MAX_TOTAL_PIXELS = 400_000_000
MAX_SIDE_MM = 4_000.0
COLOR_RE = re.compile(r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")
BAD_NAME_RE = re.compile(r'[\\/:*?"<>|\r\n\t]')

app = FastAPI(
    title="裁片填色",
    description="PLT 线框 → 分色 PNG 的本地工具",
    version="1.0.0",
)


@app.middleware("http")
async def reject_oversized_requests(request: Request, call_next):
    """在读取 multipart 之前先看 Content-Length，避免超大请求落盘。"""
    if request.method == "POST" and request.url.path == "/api/convert":
        raw_length = request.headers.get("content-length")
        if raw_length:
            try:
                length = int(raw_length)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Content-Length 不合法。"},
                )
            if length > MAX_REQUEST_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": (
                            f"请求体超过 {MAX_REQUEST_BYTES // (1024 * 1024)} MB 上限。"
                        )
                    },
                )
    return await call_next(request)


def _validate_pixels(garments: list[Garment], dpi: int) -> list[tuple[Garment, int, int]]:
    """渲染前统一校验尺寸与像素总量，避免中途浪费算力。"""
    plan: list[tuple[Garment, int, int]] = []
    total_pixels = 0
    for garment in garments:
        if garment.width_mm <= 0 or garment.height_mm <= 0:
            continue
        if garment.width_mm > MAX_SIDE_MM or garment.height_mm > MAX_SIDE_MM:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"第 {garment.index + 1} 张裁片为 "
                    f"{garment.width_mm / 10:.1f}×{garment.height_mm / 10:.1f} cm，"
                    f"单边超过 {MAX_SIDE_MM / 10:.0f} cm 上限。请检查换算比例。"
                ),
            )
        px_w, px_h = pixel_size(garment.width_mm, garment.height_mm, dpi)
        pixels = px_w * px_h
        if pixels > MAX_PIXELS_PER_IMAGE:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"第 {garment.index + 1} 张图在 {dpi} DPI 下为 {px_w}×{px_h} 像素，"
                    f"超过单张 {MAX_PIXELS_PER_IMAGE // 1_000_000} 百万像素上限。"
                    "请降低 DPI。"
                ),
            )
        total_pixels += pixels
        if total_pixels > MAX_TOTAL_PIXELS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"整批累计 {total_pixels / 1_000_000:.0f} 百万像素，"
                    f"超过 {MAX_TOTAL_PIXELS // 1_000_000} 百万像素上限。"
                    "请降低 DPI 或分批处理。"
                ),
            )
        plan.append((garment, px_w, px_h))
    return plan


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _validate_range(value: float, label: str, low: float, high: float) -> None:
    if value < low or value > high:
        raise HTTPException(
            status_code=400,
            detail=f"{label}超出范围（{low:g} – {high:g}）。",
        )


def _parse_colors(raw: str) -> list[str]:
    try:
        palette = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="色板格式不正确，应为颜色数组。")

    if not isinstance(palette, list) or not palette:
        raise HTTPException(status_code=400, detail="色板至少需要 1 个颜色。")
    if len(palette) > MAX_COLORS:
        raise HTTPException(
            status_code=400, detail=f"色板最多 {MAX_COLORS} 个颜色。"
        )

    cleaned: list[str] = []
    for color in palette:
        if not isinstance(color, str) or not COLOR_RE.match(color.strip()):
            raise HTTPException(
                status_code=400,
                detail=f"颜色值“{color}”不是合法的 #RGB 或 #RRGGBB。",
            )
        cleaned.append(color.strip())
    return cleaned


def _clean_name(value: str, fallback: str) -> str:
    name = BAD_NAME_RE.sub("_", value).strip().strip(".")
    return (name or fallback)[:80]


@app.post("/api/convert")
def convert(
    file: UploadFile = File(...),
    scale: float = Form(0.025),
    dpi: int = Form(300),
    min_area: float = Form(500.0),
    min_piece_area: float = Form(200.0),
    close_tol: float = Form(2.0),
    colors: str = Form(json.dumps(DEFAULT_COLORS)),
    prefix: str = Form(""),
) -> Response:
    filename = (file.filename or "").replace("\\", "/").split("/")[-1]
    if not filename.lower().endswith(".plt"):
        raise HTTPException(status_code=400, detail="只支持 .plt 文件。")

    # 同步端点会把整个转换放进线程池，避免 CPU 工作阻塞事件循环
    raw = file.file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 20 MB 上限。")
    if not raw:
        raise HTTPException(status_code=400, detail="文件是空的。")

    _validate_range(scale, "换算比例", 0.0001, 10.0)
    _validate_range(float(dpi), "DPI", 36, 2400)
    _validate_range(min_area, "主裁片阈值", 0.0, 1e9)
    _validate_range(min_piece_area, "碎块过滤阈值", 0.0, 1e9)
    _validate_range(close_tol, "闭环容差", 0.0, 100.0)

    palette = _parse_colors(colors)
    stem = Path(filename).stem
    name_prefix = _clean_name(prefix, stem)
    zip_name = f"{name_prefix}填色.zip"

    content = raw.decode("utf-8", errors="ignore")
    parsed = parse_plt(content, scale=scale, close_tol_mm=close_tol)
    if not parsed.polygons:
        raise HTTPException(
            status_code=400,
            detail="没有识别到闭合轮廓。请确认这是由 PU/PD/PA/PR 命令组成的 PLT 图纸。",
        )

    garments, _warnings = build_garments(
        parsed.polygons,
        parsed.lines,
        min_area=min_area,
        min_piece_area=min_piece_area,
    )
    if not garments:
        raise HTTPException(
            status_code=400,
            detail=(
                f"没有面积超过 {min_area:g} mm² 的主裁片。"
                "可以调低主裁片阈值，或确认换算比例是否正确。"
            ),
        )
    if len(garments) > MAX_GARMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"识别出 {len(garments)} 个主裁片，超过 {MAX_GARMENTS} 个上限。",
        )

    plan = _validate_pixels(garments, dpi)

    outputs: list[tuple[str, bytes]] = []
    for garment, px_w, px_h in plan:
        svg = build_svg(garment, palette)
        try:
            png = render_png(svg, px_w=px_w, px_h=px_h)
        except Exception as exc:  # resvg 内部错误
            raise HTTPException(
                status_code=500,
                detail=f"PNG 渲染失败：{exc}",
            ) from exc

        width_cm = garment.width_mm / 10.0
        height_cm = garment.height_mm / 10.0
        out_name = (
            f"{name_prefix}_{garment.index + 1}_"
            f"{format_dimension(width_cm)}X{format_dimension(height_cm)}.png"
        )
        outputs.append((out_name, png))

    if not outputs:
        raise HTTPException(status_code=400, detail="没有生成任何图片。")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for out_name, payload in outputs:
            archive.writestr(out_name, payload)
    archive_bytes = buffer.getvalue()

    headers = {
        "Content-Disposition": (
            "attachment; filename=\"plt_fill.zip\"; "
            f"filename*=UTF-8''{quote(zip_name)}"
        ),
        "X-Piece-Count": str(len(outputs)),
        "X-Output-Name": quote(zip_name),
        "Cache-Control": "no-store",
    }
    return Response(
        content=archive_bytes,
        media_type="application/zip",
        headers=headers,
    )


# 静态页面放在最后挂载，保证 /api/* 优先匹配
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
