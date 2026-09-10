@echo off
chcp 65001 > nul
setlocal

echo ============================================================
echo  Installing / Updating CodeRouter in Editable Mode (-e)
echo ============================================================
echo.

cd /d "%~dp0"

if not exist "pyproject.toml" (
    echo [ERROR] pyproject.toml not found in "%~dp0"!
    echo Please make sure this script is located in the CodeRouter root directory.
    pause
    exit /b 1
)

echo [1/2] Installing CodeRouter (with translation support)...
python -m pip install -e ".[translation]"

if %ERRORLEVEL% neq 0 (
    echo [WARN] Failed to install with [translation] extra. Trying base install...
    python -m pip install -e .
    if %ERRORLEVEL% neq 0 (
        echo.
        echo ============================================================
        echo  [ERROR] Installation failed. Error code: %ERRORLEVEL%
        echo ============================================================
        pause
        exit /b %ERRORLEVEL%
    )
)

echo.
echo ============================================================
echo  [SUCCESS] CodeRouter package installed successfully!
echo ============================================================
echo.

echo ------------------------------------------------------------
echo  [OPTIONAL] Translation Layer Setup (Argos Translate JA - EN)
echo ------------------------------------------------------------
echo  CodeRouter の日本語・英語 双方向翻訳層（Argos Translate）用の
echo  モデル（約230MB）をダウンロード＆セットアップしますか？
echo.

set DO_TRANSLATE=
if /i "%~1"=="-y" set DO_TRANSLATE=Y
if /i "%~1"=="/y" set DO_TRANSLATE=Y

if "%DO_TRANSLATE%"=="" (
    set /p DO_TRANSLATE="セットアップを実行しますか？ [Y/n]: "
)
if "%DO_TRANSLATE%"=="" set DO_TRANSLATE=Y

set MODEL_TIER=standard
if /i "%DO_TRANSLATE%"=="Y" goto :do_translate_setup
goto :skip_translate_setup

:do_translate_setup
    echo.
    echo [2/2] Checking and setting up translation models...
    if /i "%~1"=="-y" goto :skip_tier_prompt
    if /i "%~1"=="/y" goto :skip_tier_prompt
    echo.
    echo  翻訳モデルのティアを選択してください:
    echo    [1] Standard     - 軽量（標準 Argos モデル, 約230MB, DL）
    echo    [2] High-Quality - 高精度（OPUS-MT, 現地ビルド, 約1GB取得・数分）
    set TIER_CHOICE=
    set /p TIER_CHOICE="選択 [1/2] (デフォルト: 1): "
    if "%TIER_CHOICE%"=="2" set MODEL_TIER=high-quality
:skip_tier_prompt
    if /i "%~2"=="hq" set MODEL_TIER=high-quality
    if /i "%~2"=="high-quality" set MODEL_TIER=high-quality
    if "%MODEL_TIER%"=="high-quality" goto :hq_build
    python -u scripts\setup_argos_models.py --download --model-tier standard
    if %ERRORLEVEL% equ 0 (
        echo.
        echo [INFO] 翻訳モデルのセットアップが完了しました。
        echo.
        echo 【ヒント】翻訳層を有効化するには providers.yaml に以下を設定してください:
        echo ------------------------------------------------------------
        echo translation:
        echo   enabled: true
        echo   device: cpu
        echo   log_translations: false
        echo   verbose: true            # 新[translation]ペアは既定ON
        echo   log_tool_calls: true     # [tool call repair]も既定ON
        echo ------------------------------------------------------------
    ) else (
        echo.
        echo [WARN] 翻訳モデルのセットアップでエラーが発生しました。
        echo 手動で再試行する場合は以下を実行してください:
        echo   python -u scripts\setup_argos_models.py --download --model-tier standard
    )
    goto :translate_setup_done

:hq_build
    echo.
    echo [HQ] High-Qualityは配布DLせず現地ビルドします（約1GB取得・数分）。
    if not exist "models\hq\translate-ja_en-opus-mt-1_0.argosmodel" goto :hq_run_build
    if not exist "models\hq\translate-en_ja-opus-mt-1_0.argosmodel" goto :hq_run_build
    echo [HQ] 既存モデルを検証します...
    python -u scripts\setup_argos_models.py --model-dir models\hq --verify-only --model-tier high-quality
    if %ERRORLEVEL% equ 0 goto :hq_done
    echo [HQ] 検証失敗のため再ビルドします。
:hq_run_build
    call buildHqModels.bat -y
    if %ERRORLEVEL% neq 0 (
        echo.
        echo [WARN] HQビルドに失敗しました。
        echo 手動で再試行する場合は以下を実行してください:
        echo   call buildHqModels.bat
        goto :translate_setup_done
    )
:hq_done
    echo.
    echo [INFO] HQモデルの準備ができました。
    echo CUDA利用時は providers.yaml で translation.device: cuda を設定してください。
    echo.
    echo 【ヒント】翻訳層を有効化するには providers.yaml に以下を設定してください:
    echo ------------------------------------------------------------
    echo translation:
    echo   enabled: true
    echo   device: cuda
    echo   log_translations: false
    echo   verbose: true
    echo   log_tool_calls: true
    echo ------------------------------------------------------------
    goto :translate_setup_done

:skip_translate_setup
    echo.
    echo 翻訳モデルのダウンロードをスキップしました。
    echo 後からセットアップする場合は以下を実行してください:
    echo   python -u scripts\setup_argos_models.py --download

:translate_setup_done

echo.
echo ============================================================
echo  Setup Completed!
echo ============================================================
echo.
pause
