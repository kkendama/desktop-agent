"""
Simple MCP Tool Executor
直接プロセス通信でMCPサーバーを実行する簡易実装
"""

import asyncio
import json
import subprocess
from typing import Dict, Any, Optional, List
from dataclasses import dataclass


@dataclass 
class SimpleMCPResult:
    """Simple MCP execution result."""
    success: bool
    content: str
    error: Optional[str] = None


class SimpleMCPExecutor:
    """
    Simple MCP tool executor using direct process communication.
    Bypasses complex MCP client implementation for immediate functionality.
    """
    
    def __init__(self):
        self.server_commands = {
            'get_current_time': ['uvx', 'mcp-server-time'],
            'convert_time': ['uvx', 'mcp-server-time'],
            'fetch': ['uvx', 'mcp-server-fetch'],
        }
    
    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> SimpleMCPResult:
        """Execute a tool using direct MCP server communication."""
        
        if tool_name not in self.server_commands:
            return SimpleMCPResult(
                success=False,
                content="",
                error=f"Unknown tool: {tool_name}"
            )
        
        try:
            # Get server command
            server_cmd = self.server_commands[tool_name]
            
            # Create MCP message sequence
            messages = [
                # 1. Initialize
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "simple-mcp-client", "version": "1.0.0"}
                    }
                },
                # 2. Initialized notification
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized"
                },
                # 3. Tool call
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": arguments
                    }
                }
            ]
            
            # Prepare input
            input_data = '\n'.join(json.dumps(msg) for msg in messages) + '\n'
            
            # Execute server process
            process = await asyncio.create_subprocess_exec(
                *server_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Send messages and get response
            stdout, stderr = await process.communicate(input=input_data.encode())
            
            if process.returncode != 0:
                return SimpleMCPResult(
                    success=False,
                    content="",
                    error=f"Process failed with code {process.returncode}: {stderr.decode()}"
                )
            
            # Parse responses
            responses = []
            for line in stdout.decode().strip().split('\n'):
                if line.strip():
                    try:
                        responses.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            
            # Find tool call result (id=2)
            tool_result = None
            for response in responses:
                if response.get('id') == 2:
                    tool_result = response
                    break
            
            if not tool_result:
                return SimpleMCPResult(
                    success=False,
                    content="",
                    error="No tool result found in server response"
                )
            
            # Check for error
            if 'error' in tool_result:
                return SimpleMCPResult(
                    success=False,
                    content="",
                    error=f"Server error: {tool_result['error']}"
                )
            
            # Extract result content
            result = tool_result.get('result', {})
            content = result.get('content', [])
            
            # Format content
            if isinstance(content, list) and content:
                formatted_content = content[0].get('text', str(content[0])) if content[0] else str(result)
            else:
                formatted_content = str(result)
            
            return SimpleMCPResult(
                success=True,
                content=formatted_content
            )
            
        except Exception as e:
            return SimpleMCPResult(
                success=False,
                content="",
                error=f"Execution error: {str(e)}"
            )


# Test function
async def test_simple_executor():
    """Test the simple MCP executor."""
    executor = SimpleMCPExecutor()
    
    test_cases = [
        ("get_current_time", {"timezone": "Asia/Tokyo"}),
        ("fetch", {"url": "https://httpbin.org/json", "max_length": 500}),
    ]
    
    for tool_name, arguments in test_cases:
        print(f"\n=== Testing {tool_name} ===")
        print(f"Arguments: {arguments}")
        
        result = await executor.execute_tool(tool_name, arguments)
        print(f"Success: {result.success}")
        if result.success:
            print(f"Content: {result.content[:200]}...")
        else:
            print(f"Error: {result.error}")


if __name__ == "__main__":
    asyncio.run(test_simple_executor())