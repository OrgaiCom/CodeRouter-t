
@echo off
chcp 65001 > nul
setlocal

cd /d "%~dp0"

if not defined LLAMA_MODEL set "LLAMA_MODEL=C:\models\hf\LFM2.5-24B-A2B-TBrill-NEO-IQ4_XS.gguf"
if not defined LLAMA_PORT set "LLAMA_PORT=8080"

rem Hardware settings
if not defined LLAMA_CTX_SIZE set "LLAMA_CTX_SIZE=128000"
if not defined LLAMA_N_GPU_LAYERS set "LLAMA_N_GPU_LAYERS=99"

rem Model settings
if not defined LLAMA_TEMP set "LLAMA_TEMP=0.6"
if not defined LLAMA_TOP_P set "LLAMA_TOP_P=0.95"
if not defined LLAMA_TOP_K set "LLAMA_TOP_K=50"
if not defined LLAMA_MIN_P set "LLAMA_MIN_P=0.05"
if not defined LLAMA_REPEAT_PENALTY set "LLAMA_REPEAT_PENALTY=1.05"

if not defined LLAMA_SERVER set "LLAMA_SERVER=llama-server.exe"

echo.
echo  Model        : %LLAMA_MODEL%
echo  URL          : http://127.0.0.1:%LLAMA_PORT%/v1
echo  Context      : %LLAMA_CTX_SIZE%
echo  Parallel     : 1
echo  GPU layers   : %LLAMA_N_GPU_LAYERS%
echo  KV Cache     : Q4_0 / Q4_0
echo  Temperature  : %LLAMA_TEMP%
echo  Top P        : %LLAMA_TOP_P%
echo  Top K        : %LLAMA_TOP_K%
echo  Min P        : %LLAMA_MIN_P%
echo.

if not exist "%LLAMA_MODEL%" (
    echo ERROR: Model file not found.
    pause
    exit /b 1
)

"%LLAMA_SERVER%" ^
    -m "%LLAMA_MODEL%" ^
    --host 127.0.0.1 ^
    --port %LLAMA_PORT% ^
    -np 1 ^
    -ngl %LLAMA_N_GPU_LAYERS% ^
    --n-cpu-moe 33 ^
    -c %LLAMA_CTX_SIZE% ^
    -ctk q4_0 ^
    -ctv q4_0 ^
    --jinja ^
    --temp %LLAMA_TEMP% ^
    --top-p %LLAMA_TOP_P% ^
    --top-k %LLAMA_TOP_K% ^
    --min-p %LLAMA_MIN_P% ^
    --repeat-penalty %LLAMA_REPEAT_PENALTY%

endlocal
