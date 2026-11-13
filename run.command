#!/bin/bash
cd "$(dirname "$0")"

clear
echo "=============================================="
echo "  舆见 · B站评论区舆情洞察助手（macOS）"
echo "=============================================="
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "未检测到 Python 3。"
  echo "请安装 Python 3.9+：https://www.python.org/downloads/macos/"
  echo
  read -n 1 -s -r -p "按任意键退出..."
  exit 1
fi

export PORT="${PORT:-7860}"
export YUJIAN_NO_BROWSER=0

echo "Python: $(python3 --version)"
echo "正在启动，浏览器会自动打开 http://127.0.0.1:${PORT}"
echo "关闭此终端窗口即可停止服务。"
echo

python3 app.py

echo
read -n 1 -s -r -p "服务已停止，按任意键关闭窗口..."
