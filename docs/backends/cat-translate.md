# CAT-Translate 翻訳バックエンド

CAT-TranslateはCodeRouter内へロードせず、別プロセスのOpenAI互換 `llama-server` へHTTPで接続します。既存のArgos Translateは削除せず、既定のバックエンドとして残しています。

## 設定例

```yaml
translation:
  enabled: true
  backend: cat_translate
  cat_endpoint: http://127.0.0.1:8080/v1
  cat_model: CAT-Translate-1.4b
  cat_timeout_s: 30
  cat_max_new_tokens: 2048
  cat_fallback_to_argos: true
```

CAT利用時は `cat_fallback_to_argos: true` (既定) にしておくと、llama-server不在時に既存Argosへ自動フォールバックします。

モデルファイルはリポジトリへ含めません。Windowsでは、CodeRouterのルートで次を実行すると、量子化済みGGUFとllama.cppのセットアップを行えます。

```text
installCodeRouter.bat cat
```

セットアップでは、公式Safetensorsを毎回変換する代わりに、CAT-Translateを元にした公開GGUF量子化版Q4_K_M（約931MB）を取得します。モデルカードの最大位置長は8192のため、CodeRouterは長文を段落・文境界で分割します。

セットアップ済みの環境では、ワークスペース直下の`startAllSystem.bat`から`CodeRouter\startAll.bat`を呼び出し、`llamaServe.bat`を先に起動します。ヘルスチェック完了後にCodeRouterを起動します。GGUFが存在しない場合は、llama-serverを起動せず従来の起動処理を続行します。

CATへのリクエストは、公式形式に合わせて次のプロンプトを使います。

```text
Translate the following Japanese text into English.

{TEXT}
```

英日ではJapaneseとEnglishを逆にします。Markdownのテーブルはセル単位ではなく、構造を保護したテキストブロック単位で送信します。
