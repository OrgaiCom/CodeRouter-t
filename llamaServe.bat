@echo off
chcp 65001 > nul
setlocal

cd /d "%~dp0"

if not defined LLAMA_MODEL        set "LLAMA_MODEL=Jackrong/DeepSeek-V4-Pro-Qwen3.5-9B-MTP-GGUF:Q4_K_M"
if not defined LLAMA_PORT         set "LLAMA_PORT=8080"
if not defined LLAMA_CTX_SIZE     set "LLAMA_CTX_SIZE=128000"
if not defined LLAMA_N_GPU_LAYERS set "LLAMA_N_GPU_LAYERS=99"
if not defined LLAMA_N_CPU_MOE    set "LLAMA_N_CPU_MOE=30"
if not defined LLAMA_CTK          set "LLAMA_CTK=turbo4"
if not defined LLAMA_CTV          set "LLAMA_CTV=turbo4"
if not defined LLAMA_LLAMA_SERVER set "LLAMA_LLAMA_SERVER=C:\app\turboquant-plus-tqp-v0.4.0-windows-x64-cuda12.4\llama-server"

set "PATH=C:\app\turboquant-plus-tqp-v0.4.0-windows-x64-cuda12.4;%PATH%"
rem set "GGML_TQ_NATIVE=1"

echo  Model        : %LLAMA_MODEL%
echo  URL          : http://127.0.0.1:%LLAMA_PORT%/v1
echo  Context      : %LLAMA_CTX_SIZE%
echo  Parallel     : 1
echo  GPU layers   : %LLAMA_N_GPU_LAYERS%
echo  CPU MoE layer: %LLAMA_N_CPU_MOE%
echo  KV cache     : k=%LLAMA_CTK% v=%LLAMA_CTV%
echo.

"%LLAMA_LLAMA_SERVER%" ^
    -hf "%LLAMA_MODEL%" ^
    --host 127.0.0.1 ^
    --port %LLAMA_PORT% ^
    --no-mmproj ^
    -ngl %LLAMA_N_GPU_LAYERS% ^
    -ncmoe %LLAMA_N_CPU_MOE% ^
    -c %LLAMA_CTX_SIZE% ^
    -ctk %LLAMA_CTK% ^
    -ctv %LLAMA_CTV% ^
    --parallel 1 ^
    --flash-attn on ^
    --no-mmap ^
    --mlock ^
    --batch-size 2048 ^
    --ubatch-size 512 ^
    --threads 12 ^
    --cont-batching ^
    --timeout 300 ^
    --jinja ^
    --reasoning off ^
    --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0.05 ^
    --repeat-penalty 1.05 ^
    --repeat-last-n 128 ^
    --presence-penalty 0.0 ^
    --metrics ^
    --spec-type draft-mtp ^
    --spec-draft-n-max 2 ^
    --alias local-model

endlocal
