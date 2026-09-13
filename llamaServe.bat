@echo off
chcp 65001 > nul
setlocal

cd /d "%~dp0"

set "CAT_MODEL=%~dp0models\cat-translate\CAT-Translate-1.4b.Q4_K_M.gguf"
if not defined LLAMA_PORT set "LLAMA_PORT=8080"
if not defined LLAMA_CTX_SIZE set "LLAMA_CTX_SIZE=8192"
if not defined LLAMA_N_PARALLEL set "LLAMA_N_PARALLEL=1"
if not defined LLAMA_N_GPU_LAYERS set "LLAMA_N_GPU_LAYERS=99"

if not exist "%CAT_MODEL%" (
    echo [ERROR] CAT-Translate GGUF が見つかりません。
    echo         %CAT_MODEL%
    echo.
    echo installCodeRouter.bat の翻訳バックエンド選択で CAT-Translate を選択してください。
    pause
    exit /b 1
)

where llama-server.exe >nul 2>&1
if errorlevel 1 (
    echo [ERROR] llama-server.exe が見つかりません。
    echo         llama.cpp をインストールして PATH を更新してください。
    echo         https://github.com/ggml-org/llama.cpp/releases
    pause
    exit /b 1
)

echo ============================================================
echo  CAT-Translate llama-server
echo ============================================================
echo  Model : %CAT_MODEL%
echo  URL   : http://127.0.0.1:%LLAMA_PORT%/v1
echo  GPU layers: %LLAMA_N_GPU_LAYERS%
echo.
echo VRAM競合を避ける場合は、起動前に次を設定してください:
echo   set LLAMA_N_GPU_LAYERS=0
echo.

llama-server.exe ^
    -m "%CAT_MODEL%" ^
    --host 127.0.0.1 ^
    --port %LLAMA_PORT% ^
    -c %LLAMA_CTX_SIZE% ^
    -np %LLAMA_N_PARALLEL% ^
    -ngl %LLAMA_N_GPU_LAYERS%

endlocal
