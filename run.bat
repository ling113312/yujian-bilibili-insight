@echo off
chcp 65001 >nul
cd /d %~dp0

where python >nul 2>nul
if errorlevel 1 (
  echo [提示] 未检测到 Python。
  echo 请安装 Python 3.8 或更高版本，并勾选 "Add python.exe to PATH"。
  pause
  exit /b 1
)

set PORT=7860
echo 正在启动「舆见」...
echo 访问地址：http://127.0.0.1:7860
echo 关闭本窗口即可停止服务。
echo.

python app.py
pause
