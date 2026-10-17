rem @echo off
cd /d "%~dp0"

if not exist "%USERPROFILE%\.coderouter-t" mkdir "%USERPROFILE%\.coderouter-t"

copy /Y "%~dp0providers.yaml" "%USERPROFILE%\.coderouter-t\."

:: 1. new cmd and llamaTranslateServe.bat (only when CAT-Translate is installed)
if exist "%~dp0models\cat-translate\CAT-Translate-1.4b.Q4_K_M.gguf" (
    start "CAT-Translate llama-server" cmd /k "%~dp0llamaTranslateServe.bat"
    call :wait_for_llama
) else (
    echo [INFO] CAT-Translate GGUF not found. Skipping llama-server.
)

:: 2. new cmd and Qwen3.6 35B-A3B llama-server
if exist "%~dp0models\qwen3.6-35b-a3b\Qwen3.6-35B-A3B-UD-Q4_K_M.gguf" (
    start "Qwen3.6 llama-server" cmd /k "%~dp0llamaQwenServe.bat"
    call :wait_for_qwen
) else (
    echo [INFO] Qwen3.6 35B-A3B GGUF not found. Skipping Qwen llama-server.
)

:: 3. new cmd and codeRouterServe.bat
start "CodeRouter-t Server" cmd /k "%~dp0codeRouterServe.bat"

:: 4. new cmd and ollamaServe.bat
start "Ollama Server" cmd /k "%~dp0ollamaServe.bat"

:: 5. new cmd and ollamaPs.bat
start "Ollama Ps" cmd /k "%~dp0ollamaPs.bat"

:: 6. VS Code
start code ..
exit /b 0

:wait_for_llama
set "LLAMA_WAIT_COUNT=0"
if not defined TRANSLATE_PORT set "TRANSLATE_PORT=8765"
:wait_for_llama_loop
curl.exe --noproxy "*" -fsS "http://127.0.0.1:%TRANSLATE_PORT%/health" >nul 2>&1
if not errorlevel 1 (
    echo [INFO] llama-server is up.
    exit /b 0
)
set /a LLAMA_WAIT_COUNT+=1
if %LLAMA_WAIT_COUNT% GEQ 60 (
    echo [WARN] Timed out waiting for llama-server. Starting CodeRouter anyway.
    exit /b 0
)
timeout /t 1 /nobreak >nul
goto :wait_for_llama_loop

:wait_for_qwen
set "QWEN_WAIT_COUNT=0"
if not defined QWEN_PORT set "QWEN_PORT=8080"
:wait_for_qwen_loop
curl.exe --noproxy "*" -fsS "http://127.0.0.1:%QWEN_PORT%/health" >nul 2>&1
if not errorlevel 1 (
    echo [INFO] Qwen llama-server is up.
    exit /b 0
)
set /a QWEN_WAIT_COUNT+=1
if %QWEN_WAIT_COUNT% GEQ 300 (
    echo [WARN] Timed out waiting for Qwen llama-server. Starting CodeRouter anyway.
    exit /b 0
)
timeout /t 1 /nobreak >nul
goto :wait_for_qwen_loop
