"""
Tool execution handler for Desktop Agent.
Parses <tool_use> tags and executes MCP tools.
"""

import re
import yaml
import json
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from .simple_mcp_executor import SimpleMCPExecutor, SimpleMCPResult


@dataclass
class ToolCall:
    """Represents a tool call parsed from <tool_use> tags."""
    name: str
    parameters: Dict[str, Any]
    raw_content: str


@dataclass
class ToolResult:
    """Represents the result of a tool execution."""
    name: str
    content: str
    success: bool
    error: Optional[str] = None


class ToolExecutor:
    """Handles parsing and execution of tool calls."""
    
    def __init__(self, mcp_manager=None):
        """Initialize tool executor with MCP manager."""
        self.mcp_manager = mcp_manager
        self.simple_executor = SimpleMCPExecutor()  # Fallback executor
        self.tool_use_pattern = re.compile(
            r'<tool_use>\s*(.*?)\s*</tool_use>', 
            re.DOTALL | re.IGNORECASE
        )
    
    def parse_tool_calls(self, text: str) -> List[ToolCall]:
        """
        Parse <tool_use> tags from text and extract tool calls.
        
        Expected format:
        <tool_use>
        name: get_current_time
        parameters:
          timezone: "Asia/Tokyo"
          format: "iso"
        </tool_use>
        
        Or simple format:
        <tool_use> name: get_current_time parameters: {} </tool_use>
        """
        tool_calls = []
        
        for match in self.tool_use_pattern.finditer(text):
            raw_content = match.group(1).strip()
            
            try:
                # Check if it's simple inline format: "name: xxx parameters: yyy"
                if ' parameters: ' in raw_content and '\n' not in raw_content:
                    # Simple inline format
                    parts = raw_content.split(' parameters: ')
                    if len(parts) == 2:
                        name = parts[0].replace('name:', '').strip()
                        param_str = parts[1].strip()
                        
                        # Parse parameters - multiple formats supported
                        if param_str:
                            try:
                                # Try JSON first (e.g., {"key": "value"})
                                parameters = json.loads(param_str)
                            except json.JSONDecodeError:
                                try:
                                    # Try standard YAML (e.g., {key: value})
                                    parameters = yaml.safe_load(param_str)
                                except yaml.YAMLError:
                                    try:
                                        # Try as space-separated key-value pairs: key1: "value1" key2: "value2"
                                        # Convert to proper YAML dict format
                                        if ':' in param_str and not param_str.startswith('{'):
                                            # Split by spaces but keep quoted values together
                                            import shlex
                                            tokens = shlex.split(param_str)
                                            param_dict = {}
                                            i = 0
                                            while i < len(tokens):
                                                if i + 1 < len(tokens) and tokens[i].endswith(':'):
                                                    key = tokens[i][:-1]  # Remove trailing :
                                                    value = tokens[i + 1]
                                                    param_dict[key] = value
                                                    i += 2
                                                else:
                                                    i += 1
                                            parameters = param_dict
                                        else:
                                            parameters = {}
                                    except Exception:
                                        parameters = {}
                        else:
                            parameters = {}
                    else:
                        continue
                else:
                    # Multi-line YAML format
                    parsed = yaml.safe_load(raw_content)
                    if isinstance(parsed, dict):
                        name = parsed.get('name', '')
                        parameters = parsed.get('parameters', {})
                    else:
                        continue
                
                if name:
                    tool_calls.append(ToolCall(
                        name=name,
                        parameters=parameters or {},
                        raw_content=raw_content
                    ))
                    
            except (yaml.YAMLError, ValueError, json.JSONDecodeError) as e:
                print(f"Failed to parse tool call: {raw_content}, error: {e}")
                continue
        
        return tool_calls
    
    async def execute_tool_call(self, tool_call: ToolCall) -> ToolResult:
        """Execute a single tool call using SimpleMCP executor."""
        try:
            # Use SimpleMCPExecutor for reliable execution
            result = await self.simple_executor.execute_tool(
                tool_name=tool_call.name,
                arguments=tool_call.parameters
            )
            
            return ToolResult(
                name=tool_call.name,
                content=result.content,
                success=result.success,
                error=result.error
            )
            
        except Exception as e:
            return ToolResult(
                name=tool_call.name,
                content="",
                success=False,
                error=str(e)
            )
    
    async def execute_tools_in_text(self, text: str) -> Tuple[List[ToolResult], str]:
        """
        Execute all tools found in text and return results with cleaned text.
        
        Returns:
            Tuple of (tool_results, cleaned_text)
        """
        tool_calls = self.parse_tool_calls(text)
        tool_results = []
        
        # Execute all tool calls
        for tool_call in tool_calls:
            result = await self.execute_tool_call(tool_call)
            tool_results.append(result)
        
        # Remove tool_use tags from text
        cleaned_text = self.tool_use_pattern.sub('', text).strip()
        
        return tool_results, cleaned_text
    
    def format_tool_result_for_history(self, tool_result: ToolResult) -> Dict[str, Any]:
        """Format tool result for conversation history."""
        return {
            "role": "tool",
            "name": tool_result.name,
            "content": tool_result.content if tool_result.success else f"Error: {tool_result.error}"
        }
    
    def has_tool_calls(self, text: str) -> bool:
        """Check if text contains tool_use tags."""
        return bool(self.tool_use_pattern.search(text))


# Test function for development
def test_tool_parsing():
    """Test tool parsing functionality."""
    executor = ToolExecutor()
    
    # Test cases
    test_cases = [
        '<tool_use> name: get_current_time parameters: {} </tool_use>',
        '''<tool_use>
name: convert_timezone
parameters:
  time: "2024-01-01 12:00:00"
  from_timezone: "UTC"
  to_timezone: "Asia/Tokyo"
</tool_use>''',
        'Some text <tool_use> name: fetch_url parameters: {"url": "https://example.com"} </tool_use> more text'
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTest case {i}:")
        print(f"Input: {test_case}")
        
        tool_calls = executor.parse_tool_calls(test_case)
        print(f"Parsed {len(tool_calls)} tool calls:")
        
        for call in tool_calls:
            print(f"  - Name: {call.name}")
            print(f"  - Parameters: {call.parameters}")


if __name__ == "__main__":
    test_tool_parsing()