@echo off
chcp 65001 > nul
setlocal

cd /d "%~dp0"

if not defined LLAMA_MODEL set "LLAMA_MODEL=XHToken/Spark-X2.6-4B-GGUF:Q4_K_M"
if not defined LLAMA_PORT set "LLAMA_PORT=8080"
if not defined LLAMA_CTX_SIZE set "LLAMA_CTX_SIZE=128000"
if not defined LLAMA_N_GPU_LAYERS set "LLAMA_N_GPU_LAYERS=99"
if not defined LLAMA_N_CPU_MOE set "LLAMA_N_CPU_MOE=31"
if not defined LLAMA_LLAMA_SERVER set "LLAMA_LLAMA_SERVER=llama"

echo  Model        : %LLAMA_MODEL%
echo  URL          : http://127.0.0.1:%LLAMA_PORT%/v1
echo  Context      : %LLAMA_CTX_SIZE%
echo  Parallel     : 1
echo  GPU layers   : %LLAMA_N_GPU_LAYERS%
echo  CPU MoE layer: %LLAMA_N_CPU_MOE%
echo.

"%LLAMA_LLAMA_SERVER%" serve ^
    -hf "%LLAMA_MODEL%" ^
    --host 127.0.0.1 ^
    --port %LLAMA_PORT% ^
    -np 1 ^
    -ngl %LLAMA_N_GPU_LAYERS% ^
    -ncmoe %LLAMA_N_CPU_MOE% ^
    -c %LLAMA_CTX_SIZE% ^
    -ctk q4_0 ^
    -ctv q4_0 ^
    --reasoning off

endlocal
