"""
MCP (Model Context Protocol) integration module for Desktop Agent.

This module provides comprehensive MCP support including:
- MCP client and server management
- Security and permission handling
- Configuration management
- Integration with the agent system

Example usage:
    from core.mcp import MCPIntegration
    
    # Initialize MCP integration
    mcp = MCPIntegration()
    await mcp.initialize()
    
    # Call a tool
    result = await mcp.call_tool("calculator", {"operation": "add", "a": 1, "b": 2})
    
    # Get a resource
    content = await mcp.get_resource("file://data/example.txt")
"""

from .client import MCPClient, MCPServerConfig, MCPServerInstance
from .manager import MCPServerManager
from .security import MCPSecurityManager, SecurityRule, PermissionLevel, OperationType
from .config import MCPConfigManager, MCPConfig
from .integration import MCPIntegration

__all__ = [
    'MCPClient',
    'MCPServerConfig', 
    'MCPServerInstance',
    'MCPServerManager',
    'MCPSecurityManager',
    'SecurityRule',
    'PermissionLevel',
    'OperationType',
    'MCPConfigManager',
    'MCPConfig',
    'MCPIntegration'
]

__version__ = "1.0.0"