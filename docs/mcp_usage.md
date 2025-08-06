# MCP (Model Context Protocol) 使用ガイド

Desktop AgentのMCP統合機能の使用方法について説明します。

## 概要

MCPは、大規模言語モデルが外部ツールやリソースに安全にアクセスするためのプロトコルです。Desktop AgentのMCP実装では以下の機能を提供します：

- **複数MCPサーバーの管理**: 設定ファイルからの自動起動・停止
- **セキュリティ機能**: 権限管理、承認ワークフロー、監査ログ
- **動的設定**: 設定の再読み込みとホットリロード
- **統合CLI**: エージェントとMCPツールのシームレスな統合

## 設定方法

### 1. system.yamlでのMCP設定

```yaml
# config/system.yaml
mcp:
  enabled: true
  servers:
    - name: "file-ops"
      description: "ファイル操作ツール"
      command: ["python", "-m", "mcp_file_server"]
      env: {}
      permissions:
        read: true
        write: false  # 承認が必要
        delete: false  # 承認が必要
      enabled: true
    
    - name: "web-search"
      description: "Web検索機能"
      command: ["python", "-m", "mcp_web_search"]
      env:
        API_KEY: "your-api-key"
      permissions:
        read: true
      enabled: true

  security:
    audit_file: "data/logs/mcp_audit.log"
    rate_limits:
      calls_per_minute: 60
      calls_per_hour: 1000
    
    # ブロックリスト
    blocked_servers: []
    blocked_tools: ["dangerous-tool"]
    blocked_resources: ["secret://"]
    
    # セキュリティルール
    rules:
      - name: "allow-read-operations"
        operation_type: "resource_read"
        permission: "allowed"
        description: "リソース読み取りを許可"
      
      - name: "require-approval-for-writes"
        operation_type: "tool_call"
        tool_pattern: ".*write.*|.*delete.*"
        permission: "require_approval"
        description: "書き込み操作は承認が必要"
```

### 2. 新しいMCPサーバーの追加

新しいMCPサーバーを追加するには：

1. `system.yaml`の`mcp.servers`セクションに新しいサーバー設定を追加
2. CLI で `/reload` コマンドを実行して設定を再読み込み
3. `/mcp` コマンドでサーバーの状態を確認

## CLI での使用方法

### 基本コマンド

```bash
# システム状態確認（MCP情報を含む）
/status

# MCP専用の詳細状態確認
/mcp

# 利用可能なツール一覧
/tools

# 承認待ちのリクエスト確認
/approvals

# 設定の再読み込み
/reload
```

### 自然言語でのツール使用

MCPツールは自然言語で呼び出せます：

```
ユーザー: "プロジェクトのREADME.mdファイルを読んで内容を教えて"
→ file-opsサーバーのreadツールが自動的に呼び出される

ユーザー: "Pythonの最新情報を検索して"
→ web-searchサーバーの検索ツールが呼び出される

ユーザー: "新しいファイルconfig.jsonを作成して"
→ セキュリティルールにより承認が必要な場合があります
```

## セキュリティ機能

### 権限レベル

- **allowed**: 自動的に許可
- **require_approval**: 承認が必要
- **denied**: 常に拒否

### セキュリティルールの例

```yaml
# 特定のパターンのツールを常に許可
- name: "safe-tools"
  operation_type: "tool_call"
  tool_pattern: "read.*|list.*|search.*"
  permission: "allowed"

# 危険な操作は承認が必要
- name: "dangerous-operations"
  operation_type: "tool_call"
  tool_pattern: "delete.*|format.*|system.*"
  permission: "require_approval"

# 特定のサーバーからのアクセスは拒否
- name: "block-test-server"
  operation_type: "tool_call"
  server_pattern: "test-.*"
  permission: "denied"
```

### 監査ログ

すべてのMCP操作は監査ログに記録されます：

```json
{
  "timestamp": "2024-12-10T10:30:00Z",
  "operation_type": "tool_call",
  "server_name": "file-ops",
  "tool_name": "read_file",
  "arguments": {"path": "README.md"},
  "result": "allowed",
  "user_id": null
}
```

## プログラムでの使用

```python
from core.mcp import MCPIntegration

# MCP統合の初期化
async def main():
    mcp = MCPIntegration()
    await mcp.initialize()
    
    # ツールの呼び出し
    result = await mcp.call_tool(
        "read_file", 
        {"path": "example.txt"}
    )
    
    if result["success"]:
        print("ファイル内容:", result["result"])
    else:
        print("エラー:", result["error"])
    
    # リソースの取得
    content = await mcp.get_resource("file://data/config.json")
    
    # 利用可能なツール一覧
    tools = mcp.list_tools()
    for tool in tools:
        print(f"- {tool['name']} (from {tool['server']})")
    
    await mcp.shutdown()
```

## トラブルシューティング

### よくある問題

1. **MCPサーバーが起動しない**
   - コマンドが正しく指定されているか確認
   - 必要な依存関係がインストールされているか確認
   - ログファイルでエラーメッセージを確認

2. **ツールが呼び出せない**
   - セキュリティルールで許可されているか確認
   - レート制限に引っかかっていないか確認
   - サーバーが正常に動作しているか確認

3. **承認が必要な操作**
   - 現在は自動承認システムのみ実装
   - 将来のバージョンで手動承認機能を追加予定

### デバッグ方法

```bash
# デバッグモードでCLI起動
desktop-agent --debug

# ログファイルの確認
tail -f data/logs/desktop_agent.log
tail -f data/logs/mcp_audit.log
```

## 今後の拡張予定

- 手動承認ワークフローのUI
- より細かい権限制御
- MCPサーバーのプラグインシステム
- リアルタイム通知機能
- パフォーマンス監視機能

## 参考リンク

- [Model Context Protocol 公式仕様](https://spec.modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP サーバー例](https://github.com/modelcontextprotocol/servers)