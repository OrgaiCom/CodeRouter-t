rem @echo off
cd /d "%~dp0"

if not exist "%USERPROFILE%\.coderouter-t" mkdir "%USERPROFILE%\.coderouter-t"

copy /Y "%~dp0providers.yaml" "%USERPROFILE%\.coderouter-t\."

:: 1. new cmd and llamaServe.bat (only when CAT-Translate is installed)
if exist "%~dp0models\cat-translate\CAT-Translate-1.4b.Q4_K_M.gguf" (
    start "CAT-Translate llama-server" cmd /k "%~dp0llamaServe.bat"
    call :wait_for_llama
) else (
    echo [INFO] CAT-Translate GGUF not found. Skipping llama-server.
)

:: 2. new cmd and codeRouterServe.bat
start "CodeRouter-t Server" cmd /k "%~dp0codeRouterServe.bat"

:: 3. new cmd and ollamaServe.bat
start "Ollama Server" cmd /k "%~dp0ollamaServe.bat"

:: 4. new cmd and ollamaPs.bat
start "Ollama Ps" cmd /k "%~dp0ollamaPs.bat"

:: 5. VS Code
call code .
exit /b 0

:wait_for_llama
set "LLAMA_WAIT_COUNT=0"
if not defined LLAMA_PORT set "LLAMA_PORT=8080"
:wait_for_llama_loop
curl.exe -fsS "http://127.0.0.1:%LLAMA_PORT%/health" >nul 2>&1
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
