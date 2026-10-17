# Windows: RTX 4070 Laptop（8GB）で Qwen3.6 35B-A3B を使う

この構成は、Qwen3.6 35B-A3B の通常版（非MTP）を `llama-server` で起動し、
CodeRouter の全プロファイル（Fable, Opus, Sonnet, Haiku）に `coderouter-*-model` として割り当てる。

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
-ngl 99 -ncmoe 31 -c 90000 -np 1 -ctk q4_0 -ctv q4_0 --reasoning off
```

- **コンテキスト**: `90000`（90K）
- **並列度**: `-np 1`（1スロット専用にすることで、不要なKVキャッシュ確保を防止）
- **CPU MoE退避層数**: `QWEN_N_CPU_MOE=31`
  - RTX 4070 Laptop（8188 MiB）の実機計測では、`31` で **7554 MiB 使用（空き 395 MiB）** となり、共有メモリ（メインRAM）へのスワップを完全に防ぎつつGPUリソースを最大限に活用できる。
  - `30` 以下にすると空きが 15 MiB 以下になり、トークン生成時に共有メモリスワップが発生して極端に遅くなる。

サーバーは `127.0.0.1:8080` にのみバインドされ、LANには公開されない。

## 4. 起動と連携

`startAll.bat` は先に Qwen サーバーを立ち上げ、VRAM を確保してから CAT-Translate、CodeRouter を起動する。

```bat
startAll.bat
```

CodeRouter では以下の名前で全プロファイルからアクセス可能である：
- `coderouter-fable-model` (thinking)
- `coderouter-opus-model` (reasoning)
- `coderouter-sonnet-model` (coding)
- `coderouter-haiku-model` (general)

