# Desktop Agent

PC常駐型AIアシスタント - タスク管理、スケジュール管理、身の回りのサポートを提供するインテリジェントなデスクトップエージェント

## 🎯 概要

Desktop Agentは、デスクトップ環境に常駐し、ユーザーの日常業務をサポートするAIアシスタントです。自然言語でのコミュニケーションを通じて、コード実行、Web検索、ファイル操作などの多様なタスクを実行できます。

### 主な機能

- 🤖 **自然言語対話**: LLMとの自然な会話
- 💻 **コード実行**: セキュアなサンドボックス環境でのコード実行
- 🌐 **Web検索**: リアルタイムな情報収集
- 📁 **ファイル操作**: 安全なファイル読み書き（承認制）
- 🔧 **拡張可能**: MCP（Model Context Protocol）による機能拡張
- ⚙️ **柔軟な設定**: YAML + TOML による詳細設定

## 🛠️ 技術スタック

- **言語**: Python 3.11+
- **LLM**: vLLM / Ollama（設定で切り替え可能）
- **想定モデル**: Qwen3
- **UI**: CLI（将来的にReactフロントエンド予定）
- **設定**: YAML（システム） + TOML（プロンプト）
- **セキュリティ**: Docker サンドボックス

## 📦 インストール

### 1. 前提条件

- Python 3.11以上
- Docker（コード実行用）
- Ollama または vLLM サーバー

### 2. プロジェクトのクローン

```bash
git clone <repository-url>
cd desktop-agent
```

### 3. 依存関係のインストール

```bash
pip install -e .
# または開発環境の場合
pip install -e ".[dev]"
```

## ⚙️ 設定

### 1. LLMサーバーの準備

#### Ollamaを使用する場合

```bash
# Ollamaのインストール
curl -fsSL https://ollama.ai/install.sh | sh

# Qwen3モデルのダウンロード
ollama pull qwen3:latest

# サーバー起動
ollama serve
```

#### vLLMを使用する場合

```bash
# vLLMのインストール
pip install vllm

# サーバー起動（例）
python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-7B-Instruct \
    --port 8000
```

### 2. 設定ファイルの確認

デフォルトの設定ファイルが `config/` ディレクトリに配置されています：

- `config/system.yaml`: システム設定（LLM、MCP、セキュリティなど）
- `config/prompts.toml`: プロンプトテンプレート

必要に応じて設定を変更してください。

## 🚀 使用方法

### CLIでの起動

```bash
# デフォルト設定で起動
desktop-agent

# 設定ディレクトリを指定
desktop-agent --config-dir /path/to/config

# デバッグモードで起動
desktop-agent --debug
```

### 基本的な使い方

```
Desktop Agent> こんにちは
Desktop Agent> Pythonでフィボナッチ数列を計算するコードを書いて実行して
Desktop Agent> 今日の天気を教えて
Desktop Agent> /help  # ヘルプを表示
Desktop Agent> /quit  # 終了
```

### 利用可能なコマンド

- `/help` - ヘルプを表示
- `/quit` または `/exit` - アプリケーション終了
- `/clear` - 会話履歴をクリア
- `/status` - システム状態を表示
- `/reload` - 設定を再読み込み

## 📁 プロジェクト構造

```
desktop-agent/
├── core/                    # コアエンジン
│   ├── llm/                # LLM推論処理
│   ├── agent/              # エージェント実行エンジン
│   ├── tools/              # ツール管理
│   ├── mcp/                # MCP統合
│   └── config.py           # 設定管理
├── cli/                    # CLI インターフェース
│   └── main.py             # メインCLIアプリケーション
├── api/                    # RESTful API（将来実装）
├── config/                 # 設定ファイル
│   ├── system.yaml         # システム設定
│   └── prompts.toml        # プロンプトテンプレート
├── data/                   # データ永続化
├── sandbox/                # Docker サンドボックス設定
└── tests/                  # テストコード
```

## 🔧 開発

### 開発環境のセットアップ

```bash
# 開発依存関係をインストール
pip install -e ".[dev]"

# pre-commitのセットアップ
pre-commit install

# テスト実行
pytest

# コードフォーマット
black .

# 型チェック
mypy .
```

### テスト

```bash
# 全テスト実行
pytest

# 特定のテストファイル
pytest tests/test_llm.py

# カバレッジ付き
pytest --cov=core
```

## 🔒 セキュリティ

- **サンドボックス実行**: コードはDockerコンテナ内で実行
- **ファイル操作制限**: 書き込み・削除は承認制
- **パス制限**: システムディレクトリへのアクセス禁止
- **タイムアウト制御**: 長時間実行の防止

## 🌟 将来の計画

### Phase 1: CLI版（現在）
- ✅ 基本チャット機能
- ✅ LLM推論処理
- 🔄 コード実行（実装中）
- 🔄 Web検索（実装中）
- 🔄 ファイル操作（実装中）

### Phase 2: 拡張機能
- 📅 高度なメモリー管理
- 📅 タスク・スケジュール管理
- 📅 外部サービス連携
- 📅 プロアクティブな問いかけ

### Phase 3: GUI版
- 📅 React フロントエンド
- 📅 リアルタイム通信
- 📅 ビジュアルUI

## 🤝 コントリビューション

コントリビューションを歓迎します！

1. Forkしてください
2. フィーチャーブランチを作成してください (`git checkout -b feature/amazing-feature`)
3. 変更をコミットしてください (`git commit -m 'Add some amazing feature'`)
4. ブランチにプッシュしてください (`git push origin feature/amazing-feature`)
5. Pull Requestを作成してください

## 📄 ライセンス

このプロジェクトは [MIT License](LICENSE) の下でライセンスされています。

## 🙏 謝辞

- [Hugging Face smolagents](https://github.com/huggingface/smolagents) - エージェント設計の参考
- [GitHub MCP Server](https://github.com/github/github-mcp-server) - MCP統合の参考
