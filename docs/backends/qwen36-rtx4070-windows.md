# Windows: RTX 4070 Laptop（8GB）で Qwen3.6 35B-A3B を使う

この構成は、Qwen3.6 35B-A3B の通常版（非MTP）を `llama-server` で起動し、
CodeRouter の Fable (`thinking`) と Opus (`reasoning`) の両プロファイルに割り当てる。
Sonnet と Haiku は既存の Ollama プロバイダーのままである。

## 1. llama.cpp runtime

GitHub の [llama.cpp Releases](https://github.com/ggml-org/llama.cpp/releases) から、
Windows x64 CUDA 13.4 の最新アーカイブを取得して展開する。展開後の
`llama-server.exe` と同じディレクトリにCUDA DLLが存在する状態で、次の場所へ置く。

```text
runtime\llama.cpp\llama-server.exe
```

CUDA Toolkit のインストールは不要である。NVIDIA ドライバーが CUDA 13.x と互換で
あることを確認する。配置後、次で CUDA ビルドと GPU 検出を確認する。

```bat
runtime\llama.cpp\llama-server.exe --version
runtime\llama.cpp\llama-server.exe --list-devices
```

## 2. モデル配置

Hugging Face CLI で通常版の Unsloth Dynamic Quant Q4_K_M を取得する。MTP版は使わない。

```powershell
hf download unsloth/Qwen3.6-35B-A3B-GGUF --include "*UD-Q4_K_M*" --local-dir models\qwen3.6-35b-a3b
```

起動スクリプトの既定ファイル名は次である。

```text
models\qwen3.6-35b-a3b\Qwen3.6-35B-A3B-UD-Q4_K_M.gguf
```

ファイル名が異なる場合は、起動前に `QWEN_MODEL` にGGUFの絶対パスを指定する。

## 3. 起動とチューニング

`llamaQwenServe.bat` は以下を既定にする。

```text
-ngl 99 -ncmoe 26 -c 98304 -ctk q4_0 -ctv q4_0 --reasoning off
```

8GB VRAMは記事の12GBより少ない。起動できない、またはVRAMが不足する場合は、
CPUへ退避するMoE層数を増やす。

```bat
set QWEN_N_CPU_MOE=30
llamaQwenServe.bat
```

次に `32`、`34` の順で試し、起動できる最小値を採用する。サーバーは
`127.0.0.1:8080` にのみバインドされ、LANには公開されない。

MTP版は投機デコードで高速化する可能性がある一方、長文コンテキストのCUDA経路に
未解決の問題があるため、この構成の標準にはしない。通常版が安定した後に、別途
同じプロンプトとコンテキスト長で比較する。

## 4. 確認

`startAll.bat` はQwenサーバーの `/health` を最大5分待ってから CodeRouter を起動する。
モデルが起動した後、次を実行する。

```bat
uv run coderouter doctor --check-model llamacpp-qwen3-6-35b-a3b
```

基本応答、ストリーミング、tool call を確認してから Fable／Opus プロファイルで利用する。
