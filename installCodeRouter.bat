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
echo  [OPTIONAL] Translation Layer Setup
echo ------------------------------------------------------------
echo  CodeRouter の日本語・英語 双方向翻訳層用の
echo  モデルをダウンロード＆セットアップしますか？
echo.

set DO_TRANSLATE=
if /i "%~1"=="-y" set DO_TRANSLATE=Y
if /i "%~1"=="/y" set DO_TRANSLATE=Y

if "%DO_TRANSLATE%"=="" (
    set /p DO_TRANSLATE="セットアップを実行しますか？ [Y/n]: "
)
if "%DO_TRANSLATE%"=="" set DO_TRANSLATE=Y

set MODEL_TIER=standard
set TRANSLATION_BACKEND=argos
if /i "%DO_TRANSLATE%"=="Y" goto :do_translate_setup
goto :skip_translate_setup

:do_translate_setup
    echo.
    echo [2/2] Checking and setting up translation models...
    if /i "%~1"=="-y" goto :skip_tier_prompt
    if /i "%~1"=="/y" goto :skip_tier_prompt
    echo.
    echo  翻訳バックエンドを選択してください:
    echo    [1] Argos Standard      - 軽量・CPU向け (約230MB)
    echo    [2] Argos High-Quality  - OPUS-MTベース (約1GB、構築に時間がかかります)
    echo    [3] CAT-Translate 1.4B - llama-server + GGUF (約931MB)
    set BACKEND_CHOICE=
    set /p BACKEND_CHOICE="選択 [1/2/3] (デフォルト: 1): "
    if "%BACKEND_CHOICE%"=="2" set MODEL_TIER=high-quality
    if "%BACKEND_CHOICE%"=="3" set TRANSLATION_BACKEND=cat_translate
:skip_tier_prompt
    if /i "%~2"=="hq" set MODEL_TIER=high-quality
    if /i "%~2"=="high-quality" set MODEL_TIER=high-quality
    if "%TRANSLATION_BACKEND%"=="cat_translate" goto :cat_translate_setup
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
        echo   max_buffer_tokens: 131072
        echo   chunk_size_chars: 4096
        echo   chunk_timeout_s: 10.0
        echo ------------------------------------------------------------
    ) else (
        echo.
        echo [WARN] 翻訳モデルのセットアップでエラーが発生しました。
        echo 手動で再試行する場合は以下を実行してください:
        echo   python -u scripts\setup_argos_models.py --download --model-tier standard
    )
    goto :translate_setup_done

:cat_translate_setup
    echo.
    echo [CAT] CAT-Translate 1.4B + llama-server をセットアップします。
    echo [CAT] 量子化済みGGUF (Q4_K_M, 約931MB) を取得します。
    echo.
    python -m pip install --upgrade "huggingface_hub[hf_transfer]"
    if %ERRORLEVEL% neq 0 (
        echo [WARN] huggingface_hub のインストールに失敗しました。
        goto :translate_setup_done
    )
    if not exist "models\cat-translate\CAT-Translate-1.4b.Q4_K_M.gguf" (
        python -u gguf_dl.py mradermacher/CAT-Translate-1.4b-GGUF CAT-Translate-1.4b.Q4_K_M.gguf --dest models\cat-translate -y
        if errorlevel 1 (
            echo [WARN] CAT-Translate GGUF の取得に失敗しました。
            goto :translate_setup_done
        )
    ) else (
        echo [CAT] 既存のGGUFを使用します。
    )
    where llama-server.exe >nul 2>&1
    if errorlevel 1 (
        where winget.exe >nul 2>&1
        if not errorlevel 1 (
            echo [CAT] llama.cpp をインストールします。
            winget install --id ggml.llamacpp --exact --accept-package-agreements --accept-source-agreements
        ) else (
            echo [WARN] winget が見つかりません。llama.cpp を手動でインストールしてください。
            echo        https://github.com/ggml-org/llama.cpp/releases
        )
    )
    echo.
    echo [CAT] セットアップが完了しました。
    echo [CAT] サーバー起動例:
    echo   llama-server.exe -m models\cat-translate\CAT-Translate-1.4b.Q4_K_M.gguf --host 127.0.0.1 --port 8080 -c 8192
    echo.
    echo [CAT] providers.yaml 設定例:
    echo ------------------------------------------------------------
    echo translation:
    echo   enabled: true
    echo   backend: cat_translate
    echo   cat_endpoint: http://127.0.0.1:8080/v1
    echo   cat_model: CAT-Translate-1.4b
    echo   cat_fallback_to_argos: true
    echo ------------------------------------------------------------
    goto :translate_setup_done

:hq_build
    echo.
    echo [HQ] High-Quality models are built locally (about 1GB download, several minutes).
    if not exist "models\hq\translate-ja_en-opus-mt-1_0.argosmodel" goto :hq_run_build
    if not exist "models\hq\translate-en_ja-opus-mt-1_0.argosmodel" goto :hq_run_build
    echo [HQ] Verifying existing models...
    python -u scripts\setup_argos_models.py --model-dir models\hq --verify-only --model-tier high-quality
    if %ERRORLEVEL% equ 0 goto :hq_done
    echo [HQ] Verification failed. Rebuilding...
:hq_run_build
    call buildHqModels.bat -y
    if %ERRORLEVEL% neq 0 (
        echo.
        echo [WARN] HQ build failed.
        echo Retry manually with:
        echo   call buildHqModels.bat
        goto :translate_setup_done
    )
:hq_done
    echo.
    echo [INFO] HQ models are ready.
    echo For CUDA, set translation.device: cuda in providers.yaml.
    echo.
    echo [TIP] To enable translation, set in providers.yaml:
    echo ------------------------------------------------------------
    echo translation:
    echo   enabled: true
    echo   device: cuda
    echo   log_translations: false
    echo   verbose: true
    echo   log_tool_calls: true
    echo   max_buffer_tokens: 131072
    echo   chunk_size_chars: 4096
    echo   chunk_timeout_s: 10.0
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
