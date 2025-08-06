"""
MCP Client implementation for Desktop Agent.

This module provides a client implementation for the Model Context Protocol (MCP),
allowing the agent to connect to and communicate with MCP servers.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel


class MCPServerConfig(BaseModel):
    """Configuration for an MCP server."""
    name: str
    description: str
    command: List[str]
    env: Dict[str, str] = {}
    permissions: Dict[str, bool] = {}
    enabled: bool = True


class MCPServerInstance(BaseModel):
    """Runtime instance of an MCP server."""
    model_config = {"arbitrary_types_allowed": True}
    
    config: MCPServerConfig
    session: Optional[ClientSession] = None
    process: Optional[asyncio.subprocess.Process] = None
    tools: List[Dict[str, Any]] = []
    resources: List[Dict[str, Any]] = []
    status: str = "stopped"  # stopped, starting, running, error


class MCPClient:
    """
    Desktop Agent MCP Client.
    
    Manages connections to multiple MCP servers and provides a unified interface
    for tool and resource access.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.servers: Dict[str, MCPServerInstance] = {}
        self.permission_handler: Optional[Callable] = None
        
    def set_permission_handler(self, handler: Callable[[str, str, Dict], bool]):
        """Set the permission handler for security checks."""
        self.permission_handler = handler
        
    async def load_server_config(self, config: MCPServerConfig) -> bool:
        """Load and configure an MCP server."""
        try:
            self.logger.info(f"Loading MCP server: {config.name}")
            
            if not config.enabled:
                self.logger.info(f"Server {config.name} is disabled, skipping")
                return False
                
            server_instance = MCPServerInstance(config=config)
            self.servers[config.name] = server_instance
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load server config {config.name}: {e}")
            return False
    
    async def start_server(self, server_name: str) -> bool:
        """Start an MCP server and establish connection."""
        if server_name not in self.servers:
            self.logger.error(f"Server {server_name} not found")
            return False
            
        server = self.servers[server_name]
        
        try:
            self.logger.info(f"Starting MCP server: {server_name}")
            server.status = "starting"
            
            # Create server parameters
            server_params = StdioServerParameters(
                command=server.config.command[0],
                args=server.config.command[1:] if len(server.config.command) > 1 else [],
                env=server.config.env
            )
            
            # Start the server process and establish connection
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    # Initialize the session
                    await session.initialize()
                    
                    # Store session and update status
                    server.session = session
                    server.status = "running"
                    
                    # Get available tools and resources
                    await self._fetch_server_capabilities(server)
                    
                    self.logger.info(f"MCP server {server_name} started successfully")
                    return True
                    
        except Exception as e:
            self.logger.error(f"Failed to start server {server_name}: {e}")
            server.status = "error"
            return False
    
    async def stop_server(self, server_name: str) -> bool:
        """Stop an MCP server."""
        if server_name not in self.servers:
            self.logger.error(f"Server {server_name} not found")
            return False
            
        server = self.servers[server_name]
        
        try:
            self.logger.info(f"Stopping MCP server: {server_name}")
            
            if server.session:
                # Close the session gracefully
                await server.session.close()
                server.session = None
                
            if server.process:
                # Terminate the process
                server.process.terminate()
                await server.process.wait()
                server.process = None
                
            server.status = "stopped"
            server.tools = []
            server.resources = []
            
            self.logger.info(f"MCP server {server_name} stopped")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to stop server {server_name}: {e}")
            return False
    
    async def _fetch_server_capabilities(self, server: MCPServerInstance):
        """Fetch tools and resources from the server."""
        try:
            if not server.session:
                return
                
            # List available tools
            tools_result = await server.session.list_tools()
            server.tools = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "schema": tool.inputSchema
                }
                for tool in tools_result.tools
            ]
            
            # List available resources
            resources_result = await server.session.list_resources()
            server.resources = [
                {
                    "uri": resource.uri,
                    "name": resource.name,
                    "description": resource.description,
                    "mimeType": resource.mimeType
                }
                for resource in resources_result.resources
            ]
            
            self.logger.info(
                f"Server {server.config.name}: {len(server.tools)} tools, {len(server.resources)} resources"
            )
            
        except Exception as e:
            self.logger.error(f"Failed to fetch capabilities for {server.config.name}: {e}")
    
    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool on a specific MCP server."""
        if server_name not in self.servers:
            raise ValueError(f"Server {server_name} not found")
            
        server = self.servers[server_name]
        
        if server.status != "running" or not server.session:
            raise RuntimeError(f"Server {server_name} is not running")
        
        # Check permissions
        if not self._check_permissions(server_name, "tool", {"tool_name": tool_name, "arguments": arguments}):
            raise PermissionError(f"Permission denied for tool {tool_name} on server {server_name}")
        
        try:
            self.logger.info(f"Calling tool {tool_name} on server {server_name}")
            
            result = await server.session.call_tool(tool_name, arguments)
            
            return {
                "success": True,
                "result": result.content,
                "isError": result.isError if hasattr(result, 'isError') else False
            }
            
        except Exception as e:
            self.logger.error(f"Tool call failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_resource(self, server_name: str, resource_uri: str) -> Dict[str, Any]:
        """Get a resource from a specific MCP server."""
        if server_name not in self.servers:
            raise ValueError(f"Server {server_name} not found")
            
        server = self.servers[server_name]
        
        if server.status != "running" or not server.session:
            raise RuntimeError(f"Server {server_name} is not running")
        
        # Check permissions
        if not self._check_permissions(server_name, "resource", {"resource_uri": resource_uri}):
            raise PermissionError(f"Permission denied for resource {resource_uri} on server {server_name}")
        
        try:
            self.logger.info(f"Getting resource {resource_uri} from server {server_name}")
            
            result = await server.session.read_resource(resource_uri)
            
            return {
                "success": True,
                "contents": result.contents
            }
            
        except Exception as e:
            self.logger.error(f"Resource access failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _check_permissions(self, server_name: str, operation_type: str, context: Dict[str, Any]) -> bool:
        """Check if an operation is permitted."""
        # Get server config
        if server_name not in self.servers:
            return False
            
        server = self.servers[server_name]
        permissions = server.config.permissions
        
        # Basic permission check based on operation type
        if operation_type == "tool":
            if "execute" in permissions and not permissions["execute"]:
                return False
        elif operation_type == "resource":
            if "read" in permissions and not permissions["read"]:
                return False
        
        # Call custom permission handler if available
        if self.permission_handler:
            return self.permission_handler(server_name, operation_type, context)
        
        return True
    
    def get_all_tools(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get all available tools from all servers."""
        all_tools = {}
        for server_name, server in self.servers.items():
            if server.status == "running":
                all_tools[server_name] = server.tools
        return all_tools
    
    def get_all_resources(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get all available resources from all servers."""
        all_resources = {}
        for server_name, server in self.servers.items():
            if server.status == "running":
                all_resources[server_name] = server.resources
        return all_resources
    
    def get_server_status(self) -> Dict[str, str]:
        """Get status of all servers."""
        return {name: server.status for name, server in self.servers.items()}
    
    async def start_all_servers(self) -> Dict[str, bool]:
        """Start all configured servers."""
        results = {}
        for server_name in self.servers.keys():
            results[server_name] = await self.start_server(server_name)
        return results
    
    async def stop_all_servers(self) -> Dict[str, bool]:
        """Stop all running servers."""
        results = {}
        for server_name in self.servers.keys():
            results[server_name] = await self.stop_server(server_name)
        return results
    
    async def restart_server(self, server_name: str) -> bool:
        """Restart a specific server."""
        await self.stop_server(server_name)
        await asyncio.sleep(1)  # Brief pause
        return await self.start_server(server_name)
    
    async def cleanup(self):
        """Clean up all resources."""
        await self.stop_all_servers()
        self.servers.clear()