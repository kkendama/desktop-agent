# Chat Template and Completion API Guide

## 概要

Desktop AgentにLLMのchat templateを1ファイル単位で管理し、system.yamlからテンプレート選択できる機能を実装しました。また、Completions APIを使用した応答生成により、toolやcodeの実行結果をassistant応答に含めて継続生成できるようになりました。

## 主要機能

### 1. Chat Template管理システム

#### ファイル構造
```
config/
├── system.yaml          # LLM設定とテンプレート選択
└── chat_templates/      # Chat templateファイル
    ├── qwen3.yaml       # Qwen3用テンプレート
    ├── chatml.yaml      # ChatML標準テンプレート
    └── openai.yaml      # OpenAI互換テンプレート
```

#### 設定例（system.yaml）
```yaml
llm:
  provider: "vllm"
  model: "unsloth/qwen3-30b-a3b-instruct-2507"
  endpoint: "http://172.30.144.1:1234"
  
  chat_template:
    template: "qwen3"     # 使用するテンプレート名
    auto_detect: true     # モデル名による自動検出
    overrides:
      system_message: null
      max_tokens: null
```

#### Chat Templateファイル例（qwen3.yaml）
```yaml
name: "qwen3"
description: "Qwen3 Chat Template with <|im_start|> and <|im_end|> tokens"
model_family: "qwen3"

format:
  system: "<|im_start|>system\n{content}<|im_end|>\n"
  user: "<|im_start|>user\n{content}<|im_end|>\n"
  assistant: "<|im_start|>assistant\n{content}<|im_end|>\n"
  function: "<|im_start|>function\n{content}<|im_end|>\n"
  generation_prompt: "<|im_start|>assistant\n"

stop_tokens:
  - "<|im_end|>"
  - "<|endoftext|>"

defaults:
  system_message: "You are a helpful assistant."
  add_generation_prompt: true

completion:
  enabled: true
  continue_template: "{partial_content}"
  completion_stop_tokens:
    - "<|im_end|>"
    - "\n\n"

compatible_models:
  - ".*qwen3.*"
  - ".*Qwen3.*"
```

### 2. Completions API統合

#### 基本的な使用方法
```python
from core.llm.manager import LLMManager

# 初期化
manager = LLMManager()
await manager.initialize()

# Chat形式での生成
messages = [
    LLMMessage(role="system", content="You are a helpful assistant."),
    LLMMessage(role="user", content="Hello!")
]
response = await manager.generate(messages)

# Completion形式での生成
response = await manager.completion(
    prompt="The capital of Japan is",
    max_tokens=50,
    temperature=0.1
)
```

### 3. Tool/Code実行結果の統合

#### 継続生成の使用例
```python
from core.llm.continuation import ContinuationManager, ConversationState

# 初期化
llm_manager = LLMManager()
await llm_manager.initialize()
continuation_manager = ContinuationManager(llm_manager)

# 会話状態の管理
state = ConversationState()
state.add_message(LLMMessage(role="user", content="Calculate 2 + 2"))
state.start_assistant_response("I'll calculate that for you:")

# Tool実行結果を含めた継続生成
continued_response = await continuation_manager.continue_with_tool_result(
    conversation_messages=state.get_conversation_copy(),
    partial_assistant_response=state.current_assistant_response,
    tool_name="calculator",
    tool_result="4",
    max_continuation_tokens=200
)

# Code実行結果を含めた継続生成
continued_response = await continuation_manager.continue_with_code_result(
    conversation_messages=state.get_conversation_copy(),
    partial_assistant_response=state.current_assistant_response,
    code="print(2 + 2)",
    code_output="4",
    max_continuation_tokens=150
)
```

## アーキテクチャ

### クラス構成

1. **ChatTemplateManager** (`core/llm/chat_template.py`)
   - Chat templateファイルの読み込み・管理
   - メッセージフォーマット処理
   - テンプレート自動検出

2. **LLMManager** (`core/llm/manager.py`)
   - LLMエンジンとchat templateの統合管理
   - Chat/Completion API統一インターフェース
   - テンプレート選択・切り替え

3. **ContinuationManager** (`core/llm/continuation.py`)
   - Tool/code実行結果の統合
   - 継続生成処理
   - 会話状態管理

4. **BaseLLMEngine** (`core/llm/base.py`)
   - Completion APIの抽象インターフェース
   - Chat/Completion統一レスポンス形式

### データフロー

```
User Message → Chat Template → Formatted Prompt → LLM Engine → Response
                    ↓
Tool/Code Execution → Result Integration → Completion API → Continued Response
```

## 利点

### 1. 柔軟なテンプレート管理
- 1ファイル1テンプレートで管理が簡単
- モデル別の最適化されたテンプレート使用
- 設定による簡単な切り替え

### 2. 継続生成による自然な対話
- Tool実行結果を含めた自然な応答継続
- Code実行結果の適切な統合
- ストリーミング対応

### 3. 拡張性
- 新しいモデル用テンプレートの追加が容易
- プラガブルなLLMエンジン対応
- カスタムテンプレート作成可能

## 使用例とテスト

### テスト実行
```bash
# 基本機能テスト
uv run examples/test_chat_templates.py

# 使用例実行
uv run examples/chat_template_usage_example.py
```

### 実際の動作例

#### Tool実行結果統合
```
User: "What's the current time in Tokyo?"
Assistant: "I'll check the current time in Tokyo for you."
[Tool execution: get_current_time]
Assistant (continued): "The current time in Tokyo is 14:30 JST on January 15, 2024."
```

#### Code実行結果統合
```
User: "Calculate the factorial of 5"
Assistant: "I'll calculate the factorial of 5 for you:

```python
import math
result = math.factorial(5)
print(f'5! = {result}')
```

[Code execution output: "5! = 120"]
Assistant (continued): "The factorial of 5 is 120. This means 5! = 5 × 4 × 3 × 2 × 1 = 120."
```

## 設定可能な項目

### system.yaml設定
- `template`: 使用するテンプレート名
- `auto_detect`: モデル名による自動検出の有効/無効
- `overrides`: テンプレート設定のオーバーライド

### テンプレートファイル設定
- `format`: 各ロール用のフォーマット文字列
- `stop_tokens`: 生成停止トークン
- `completion`: 継続生成用設定
- `compatible_models`: 対応モデルパターン

## トラブルシューティング

### よくある問題
1. **テンプレートファイルが見つからない**
   - `config/chat_templates/` ディレクトリの存在確認
   - YAMLファイルの構文確認

2. **Completion APIが動作しない**
   - LLMサーバーの起動確認
   - エンドポイント設定の確認

3. **継続生成が期待通りに動作しない**
   - テンプレートのcompletion対応確認
   - stop_tokensの適切な設定

### デバッグ方法
```python
# テンプレート情報確認
template_info = manager.get_template_info()
print(template_info)

# フォーマット結果確認
formatted = manager.format_chat_messages(messages)
print(formatted)

# Stop tokens確認
stop_tokens = manager.get_template_stop_tokens(completion_mode=True)
print(stop_tokens)
```

## 今後の拡張可能性

1. **追加テンプレート**
   - Gemini、Claude等の他モデル対応
   - カスタムフォーマット追加

2. **高度な継続制御**
   - 複数tool結果の統合
   - 条件分岐による継続制御

3. **パフォーマンス最適化**
   - テンプレートキャッシュ
   - バッチ処理対応