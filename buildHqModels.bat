@echo off
chcp 65001 > nul
setlocal

cd /d "%~dp0"
set PYTHONUTF8=1

if not exist "scripts\build_hq_argos_models.py" (
    echo [ERROR] scripts\build_hq_argos_models.py not found.
    pause
    exit /b 1
)

set OUT_DIR=models\hq
set EXTRA_ARGS=%*

echo ============================================================
echo  Build HQ Argos models (.argosmodel + SHA256SUMS.json)
echo  Output: %OUT_DIR%
echo ============================================================

if /i "%~1"=="--help" goto :build
if /i "%~1"=="-y" if /i "%~2"=="--help" (
    set EXTRA_ARGS=--help %3 %4 %5 %6
    goto :build
)

where ct2-transformers-converter > nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [INFO] ct2-transformers-converter not found -- will check pip packages.
)

echo [0/2] Checking build deps...
python -c "import huggingface_hub, ctranslate2, transformers, sentencepiece" > nul 2>&1
if %ERRORLEVEL% equ 0 goto :confirm
echo [WARN] 不足: huggingface_hub ctranslate2 transformers sentencepiece

if /i "%~1"=="-y" goto :install_deps
set /p INSTALL="pip installしますか？ [Y/n]: "
if "%INSTALL%"=="" set INSTALL=Y
if /i not "%INSTALL%"=="Y" (
    echo 中断。手動導入: python -m pip install huggingface_hub ctranslate2 transformers sentencepiece
    pause
    exit /b 1
)

:install_deps
python -m pip install huggingface_hub ctranslate2 transformers sentencepiece
if %ERRORLEVEL% neq 0 (
    echo [ERROR] pip install failed: %ERRORLEVEL%
    pause
    exit /b %ERRORLEVEL%
)

:confirm
if /i "%~1"=="-y" (
    set EXTRA_ARGS=%2 %3 %4 %5 %6
    goto :build
)
set /p REPLY="Buildを実行しますか？ [Y/n]: "
if "%REPLY%"=="" set REPLY=Y
if /i not "%REPLY%"=="Y" (
    echo Skipped.
    exit /b 0
)

:build
echo [1/2] Building...
python -u scripts\build_hq_argos_models.py --output-dir %OUT_DIR% %EXTRA_ARGS%
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Build failed: %ERRORLEVEL%
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [2/2] Verifying...
python -u scripts\setup_argos_models.py --model-dir %OUT_DIR% --verify-only --model-tier high-quality --skip-hash-check

echo.
echo ============================================================
echo  [DONE] %OUT_DIR%\SHA256SUMS.json を確認してください
echo  Next: Release公開後、URL+SHA256を MODEL_REGISTRYへ転記
echo ============================================================
pause
