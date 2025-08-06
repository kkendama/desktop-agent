# Desktop Agent - Streaming機能

## 概要

Desktop AgentにLLMのstreaming出力機能を実装しました。この機能により、LLMの応答をリアルタイムで表示し、よりインタラクティブなユーザー体験を提供します。

## 実装された機能

### 1. LLMManagerの拡張
- `generate_stream()` メソッドを追加
- vLLM、Ollamaエンジンの既存streaming対応を活用
- エラーハンドリングと例外処理を強化

### 2. CLIのstreaming UI
- Rich ライブラリの `Live` コンポーネントを使用
- リアルタイムでのマークダウン表示
- 美しいパネル表示でstreaming出力を表示

### 3. 動的モード切り替え
- `/stream` コマンドでstreaming ON/OFF切り替え
- デフォルトでstreaming有効
- 非streamingモードにフォールバック機能

### 4. エラーハンドリング
- streaming中の例外を適切に処理
- 自動的に非streamingモードへフォールバック
- ユーザーフレンドリーなエラーメッセージ

### 5. ツール統合
- streaming中でもツール呼び出しが正常に動作
- ツール実行結果の表示

## 使用方法

### CLI起動
```bash
python -m cli.main
```

### コマンド
- `/help` - ヘルプ表示
- `/stream` - streaming モードの ON/OFF 切り替え
- `/status` - システム状態確認（streaming状態も表示）
- 通常のチャット - streaming または非streaming で応答

### streaming動作例
```
Desktop Agent> こんにちは

🤖 Desktop Agent
┌─────────────────────────────────────────┐
│ こんにちは！お手伝いできることがあれば   │
│ お気軽にお声かけください。プログラミン   │
│ グ、ファイル操作、Web検索など、様々な   │
│ タスクをサポートできます。             │
└─────────────────────────────────────────┘
```

## テスト

テストスクリプトで動作確認：
```bash
python test_streaming.py
```

テスト項目：
- ✅ LLM接続とhealth check
- ✅ 非streaming応答
- ✅ streaming応答（チャンク分割表示）
- ✅ エラーハンドリング
- ✅ 設定ファイル検証

## 技術的詳細

### アーキテクチャ
```
CLI Layer (main.py)
├── _handle_streaming_response()    # streaming処理
├── _handle_non_streaming_response() # 非streaming処理
└── Rich Live コンポーネント

LLM Manager Layer (manager.py)  
├── generate_stream()              # streaming generator
├── generate()                     # 従来の非streaming
└── エラーハンドリング

Engine Layer (vllm_engine.py, ollama_engine.py)
├── _stream_generate()             # プロバイダ固有streaming
└── OpenAI互換API streaming
```

### 特徴
- **非破壊的実装**: 既存の非streaming機能を維持
- **プロバイダ非依存**: vLLM、Ollama両方で動作
- **Rich UI**: 美しいマークダウン表示
- **エラー耐性**: streaming失敗時の自動フォールバック
- **デバッグフレンドリー**: 詳細なエラー情報とデバッグ出力

## 設定

システム設定 (`config/system.yaml`) は従来通り：
```yaml
llm:
  provider: "vllm"  # or "ollama"
  model: "qwen/qwen3-30b-a3b-2507"
  endpoint: "http://localhost:8000"
```

## パフォーマンス

- streaming応答の初回表示レイテンシが大幅改善
- チャンク単位での逐次表示によりUX向上
- メモリ効率的な実装（大量のテキスト生成時）

## 今後の拡張可能性

1. **WebSocket対応**: GUI版での実装に向けた準備
2. **プログレス表示**: 生成進行状況の可視化
3. **カスタマイズ**: streaming表示スタイルの設定可能化
4. **並列処理**: 複数LLMの同時streaming

---

**注意**: streaming機能を使用するには、LLMプロバイダ（vLLMまたはOllama）が適切に起動している必要があります。