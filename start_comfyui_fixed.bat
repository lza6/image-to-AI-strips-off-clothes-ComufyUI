@echo off
:: 设置 CMD 窗口为 UTF-8 编码
chcp 65001
title ComfyUI_Server_Fixed

echo ====================================================
echo   ComfyUI 终极核平启动器 (极速启动 + 逻辑绕过)
echo ====================================================

:: 1. 强制切换到 D 盘工作目录
d:
cd /d D:\C

:: 2. 释放端口 8000
echo [2/6] 正在释放端口 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    taskkill /f /pid %%a >nul 2>&1
)

:: 3. 设置路径变量
set PYTHON_EXE=D:\C\.venv\Scripts\python.exe
set MAIN_PY=C:\Users\Administrator.DESKTOP-EGNE9ND\AppData\Local\Programs\ComfyUI\resources\ComfyUI\main.py

:: 【修复点1】定义 USER_DIR 以及输入输出目录 (根据你之前的日志还原)
set USER_DIR=D:\C\user
set INPUT_DIR=D:\C\input
set OUTPUT_DIR=D:\C\output

:: 4. 设置环境变量 (彻底禁用 tqdm 进度条和彩色输出，完美修复 Errno 22)
set TQDM_DISABLE=1
set PYTHONUNBUFFERED=1
:: 【修复点2】禁用彩色输出，防止自定义节点加载时 colorama 报错
set ANSI_COLORS_DISABLED=1

:: 5. 检查前端组件
echo [4/6] 正在检查前端组件...
"%PYTHON_EXE%" -m pip install comfyui-frontend-package -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1

echo [5/6] 正在启动 ComfyUI 引擎...
echo ----------------------------------------------------

:: 6. 启动 ComfyUI
"%PYTHON_EXE%" -u "%MAIN_PY%" ^
  --cuda-malloc ^
  --fp16-text-enc ^
  --preview-method taesd ^
  --use-pytorch-cross-attention ^
  --normalvram ^
  --dont-print-server ^
  --base-directory "D:\C" ^
  --user-directory "%USER_DIR%" ^
  --input-directory "%INPUT_DIR%" ^
  --output-directory "%OUTPUT_DIR%" ^
  --disable-assets-autoscan ^
  --disable-metadata ^
  --port 8000 ^
  --listen 127.0.0.1

echo ----------------------------------------------------
echo [提示] 如果看到此消息，说明 ComfyUI 已正常关闭。
pause