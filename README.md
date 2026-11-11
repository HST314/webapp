# 裁片填色（Web 版）

把项目根目录下 `导出测试.py` 的能力搬到了浏览器：上传 PLT 图纸，按页面上的参数拆片、分色，一次性导出 PNG 压缩包。

所有参数默认值与桌面脚本一致，改完立即生效，不需要再动源码。

## 安装

建议使用虚拟环境（Python 3.10+）：

```bat
cd /d "d:\File\创业\软件及网站\上传plt\webapp"
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

## 启动

```bat
python run.py
```

浏览器会自动打开。服务优先使用 8000；如果被其它程序占用，会自动顺延到下一个空闲端口，控制台会打印实际地址。也可以手动启动：

```bat
python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

## 页面参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| 单位换算 | 0.025 | 1 个 PLT 绘图单位对应的毫米数 |
| 输出分辨率 | 300 DPI | PNG 的像素密度 |
| 主裁片阈值 | 500 mm² | 面积大于此值才视为主裁片 |
| 碎块过滤 | 200 mm² | 小于此值的面片不导出 |
| 闭环容差 | 2 mm | 首尾点距离小于此值算闭合轮廓 |
| 色板 | 5 个颜色 | 按面积从大到小循环取色，可增删改 |
| 文件名前缀 | PLT 文件名 | 导出格式：前缀_序号_宽X高.png |

## 接口

`POST /api/convert`，`multipart/form-data`：

| 字段 | 类型 | 说明 |
|---|---|---|
| file | 文件 | `.plt`，上限 20 MB |
| scale | float | 默认 0.025 |
| dpi | int | 默认 300 |
| min_area | float | 默认 500 |
| min_piece_area | float | 默认 200 |
| close_tol | float | 默认 2 |
| colors | JSON 字符串 | `["#CCCCFF", ...]` |
| prefix | string | 文件名前缀，可空 |

返回 `application/zip`。响应头 `X-Piece-Count` 是图片数量，`X-Output-Name` 是 ZIP 文件名（URL 编码）。

## 与桌面脚本的差异

- 参数全部可视化，不再写死在代码里。
- 修复 `PD` 后跟多组坐标时只取第一组的问题。
- 切割线改为：把落在同一裁片上的线合并成一张切割网，一次性分割。单根线经常只是网络中的一段，逐根切会切不动。
- 自相交或退化轮廓会先用 `buffer(0)` 修复。
- 输出改为浏览器下载 ZIP，不再写回 PLT 所在目录。

## 部署到云服务器

线上使用 **Ubuntu + systemd/venv + Nginx**，纯 HTTP、无认证。详细步骤、Deploy Key、限流与资源建议见 [deploy/README.md](deploy/README.md)。

仓库内附 `samples/demo.plt`，可在服务器上做冒烟测试，不包含客户图纸。

## 已知限制

- 只取多边形外轮廓，真正的孔洞（袖窿、口袋开口）不会挖空；PLT 里没有孔洞语义，内部闭合小块仍按“色块”处理。
- 颜色按面积顺序循环，不代表部件语义。要固定某类部件颜色，调整色板顺序即可。
- 仅支持 `PU / PD / PA / PR` 组成的 PLT 子集，圆弧、填充、文字等命令会被忽略。
