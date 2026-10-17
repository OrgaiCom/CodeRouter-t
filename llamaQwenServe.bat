@echo off
chcp 65001 > nul
setlocal

cd /d "%~dp0"

if not defined QWEN_MODEL set "QWEN_MODEL=%~dp0models\qwen3.6-35b-a3b\Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"
if not defined QWEN_PORT set "QWEN_PORT=8080"
if not defined QWEN_CTX_SIZE set "QWEN_CTX_SIZE=98304"
if not defined QWEN_N_GPU_LAYERS set "QWEN_N_GPU_LAYERS=99"
if not defined QWEN_N_CPU_MOE set "QWEN_N_CPU_MOE=26"
if not defined QWEN_LLAMA_SERVER set "QWEN_LLAMA_SERVER=%~dp0runtime\llama.cpp\llama-server.exe"

if not exist "%QWEN_MODEL%" (
    echo [ERROR] Qwen3.6 35B-A3B GGUF was not found.
    echo         %QWEN_MODEL%
    echo.
    echo Set QWEN_MODEL to the downloaded UD-Q4_K_M GGUF path and retry.
    pause
    exit /b 1
)

if not exist "%QWEN_LLAMA_SERVER%" (
    echo [ERROR] Latest llama-server.exe was not found.
    echo         %QWEN_LLAMA_SERVER%
    echo.
    echo Install the official Windows x64 CUDA runtime under runtime\llama.cpp,
    echo or set QWEN_LLAMA_SERVER to an explicit executable path.
    pause
    exit /b 1
)

echo ============================================================
echo  Qwen3.6 35B-A3B llama-server
echo ============================================================
echo  Model        : %QWEN_MODEL%
echo  URL          : http://127.0.0.1:%QWEN_PORT%/v1
echo  Context      : %QWEN_CTX_SIZE%
echo  GPU layers   : %QWEN_N_GPU_LAYERS%
echo  CPU MoE layer: %QWEN_N_CPU_MOE%
echo.
echo RTX 4070 Laptop ^(8GB^) may require a larger QWEN_N_CPU_MOE value.
echo.

"%QWEN_LLAMA_SERVER%" ^
    -m "%QWEN_MODEL%" ^
    --host 127.0.0.1 ^
    --port %QWEN_PORT% ^
    -ngl %QWEN_N_GPU_LAYERS% ^
    -ncmoe %QWEN_N_CPU_MOE% ^
    -c %QWEN_CTX_SIZE% ^
    -ctk q4_0 ^
    -ctv q4_0 ^
    --reasoning off

endlocal
