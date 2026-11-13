# -*- coding: utf-8 -*-
"""舆见最小冒烟测试：启动临时端口，检查健康接口与演示模式全流程。"""
import os
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_health(base_url, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base_url + "/api/health", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    port = free_port()
    env = os.environ.copy()
    env["PORT"] = str(port)
    env["HOST"] = "127.0.0.1"
    env["YUJIAN_NO_BROWSER"] = "1"

    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=flags,
    )
    base = "http://127.0.0.1:%d" % port

    try:
        if not wait_health(base):
            raise RuntimeError("服务未在超时时间内启动")

        form = urllib.parse.urlencode({
            "demo": "1",
            "pages": "1",
            "sub": "1",
            "engine": "rule",
        }).encode("utf-8")
        req = urllib.request.Request(base + "/analyze", data=form, method="POST")
        with urllib.request.urlopen(req, timeout=90) as r:
            html = r.read().decode("utf-8", "ignore")

        for word in ("正面", "中性", "负面"):
            if word not in html:
                raise AssertionError("结果页缺少关键字：%s" % word)

        print("SMOKE_OK port=%d" % port)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
