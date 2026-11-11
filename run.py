"""启动本地服务，自动选择空闲端口并打开浏览器。"""

from __future__ import annotations

import socket
import threading
import time
import webbrowser

import uvicorn

PREFERRED_PORT = 8000


def _port_is_free(port: int) -> bool:
    """Windows 上 SO_REUSEADDR 会允许绑定已占用端口，因此先做连接探测。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        try:
            probe.connect(("127.0.0.1", port))
        except OSError:
            pass
        else:
            return False

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            except OSError:
                pass
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
        return True


def find_free_port(preferred: int = PREFERRED_PORT) -> int:
    """优先使用 8000，被占用时顺延；全部占用则交给系统分配。"""
    for port in range(preferred, preferred + 30):
        if _port_is_free(port):
            return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def open_browser(url: str) -> None:
    time.sleep(1.2)
    webbrowser.open(url)


if __name__ == "__main__":
    port = find_free_port()
    url = f"http://127.0.0.1:{port}"
    threading.Thread(target=open_browser, args=(url,), daemon=True).start()
    print(f"服务地址：{url}")
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, reload=False)
