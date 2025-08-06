"""
MCP Server Manager for Desktop Agent.

This module manages the lifecycle of MCP servers, including loading configurations,
starting/stopping servers, and monitoring their health.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
import yaml
from datetime import datetime, timedelta

from .client import MCPClient, MCPServerConfig


class MCPServerManager:
    """
    Manages the lifecycle of MCP servers for Desktop Agent.
    
    Features:
    - Load server configurations from system.yaml
    - Start/stop servers automatically
    - Monitor server health
    - Handle server failures and restarts
    - Provide unified interface for MCP operations
    """
    
    def __init__(self, config_path: Optional[str] = None):
        self.logger = logging.getLogger(__name__)
        self.config_path = config_path or "config/system.yaml"
        self.client = MCPClient()
        
        # Health monitoring
        self.health_check_interval = 30  # seconds
        self.max_restart_attempts = 3
        self.restart_delay = 5  # seconds
        self._health_monitor_task: Optional[asyncio.Task] = None
        self._server_restart_counts: Dict[str, int] = {}
        self._last_restart_times: Dict[str, datetime] = {}
        
        # Callbacks
        self.on_server_started: Optional[Callable] = None
        self.on_server_stopped: Optional[Callable] = None
        self.on_server_error: Optional[Callable] = None
        
    async def initialize(self) -> bool:
        """Initialize the MCP manager and load configurations."""
        try:
            self.logger.info("Initializing MCP Server Manager")
            
            # Load configurations
            success = await self.load_configurations()
            if not success:
                return False
            
            # Start health monitoring
            self._health_monitor_task = asyncio.create_task(self._health_monitor_loop())
            
            self.logger.info("MCP Server Manager initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize MCP manager: {e}")
            return False
    
    async def load_configurations(self) -> bool:
        """Load MCP server configurations from system.yaml."""
        try:
            config_file = Path(self.config_path)
            if not config_file.exists():
                self.logger.warning(f"Configuration file not found: {self.config_path}")
                return False
            
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            mcp_config = config.get('mcp', {})
            if not mcp_config.get('enabled', False):
                self.logger.info("MCP is disabled in configuration")
                return True
            
            servers_config = mcp_config.get('servers', [])
            if not servers_config:
                self.logger.warning("No MCP servers configured")
                return True
            
            # Load each server configuration
            loaded_count = 0
            for server_config in servers_config:
                try:
                    mcp_server_config = MCPServerConfig(**server_config)
                    success = await self.client.load_server_config(mcp_server_config)
                    if success:
                        loaded_count += 1
                        self.logger.info(f"Loaded server configuration: {mcp_server_config.name}")
                    else:
                        self.logger.error(f"Failed to load server: {mcp_server_config.name}")
                        
                except Exception as e:
                    self.logger.error(f"Invalid server configuration: {e}")
                    continue
            
            self.logger.info(f"Loaded {loaded_count} MCP server configurations")
            return loaded_count > 0
            
        except Exception as e:
            self.logger.error(f"Failed to load configurations: {e}")
            return False
    
    async def start_all_servers(self) -> Dict[str, bool]:
        """Start all configured MCP servers."""
        self.logger.info("Starting all MCP servers")
        results = await self.client.start_all_servers()
        
        # Reset restart counts for successfully started servers
        for server_name, success in results.items():
            if success:
                self._server_restart_counts[server_name] = 0
                if self.on_server_started:
                    await self._safe_callback(self.on_server_started, server_name)
            else:
                if self.on_server_error:
                    await self._safe_callback(self.on_server_error, server_name, "Failed to start")
        
        return results
    
    async def stop_all_servers(self) -> Dict[str, bool]:
        """Stop all running MCP servers."""
        self.logger.info("Stopping all MCP servers")
        results = await self.client.stop_all_servers()
        
        # Trigger callbacks for stopped servers
        for server_name, success in results.items():
            if success and self.on_server_stopped:
                await self._safe_callback(self.on_server_stopped, server_name)
        
        return results
    
    async def restart_server(self, server_name: str) -> bool:
        """Restart a specific MCP server."""
        self.logger.info(f"Restarting MCP server: {server_name}")
        
        # Check restart limits
        current_time = datetime.now()
        if server_name in self._last_restart_times:
            time_since_last = current_time - self._last_restart_times[server_name]
            if time_since_last < timedelta(minutes=5):  # 5-minute cooldown
                restart_count = self._server_restart_counts.get(server_name, 0)
                if restart_count >= self.max_restart_attempts:
                    self.logger.error(f"Server {server_name} exceeded max restart attempts")
                    return False
        
        # Perform restart
        success = await self.client.restart_server(server_name)
        
        if success:
            self._server_restart_counts[server_name] = 0
            if self.on_server_started:
                await self._safe_callback(self.on_server_started, server_name)
        else:
            self._server_restart_counts[server_name] = self._server_restart_counts.get(server_name, 0) + 1
            self._last_restart_times[server_name] = current_time
            if self.on_server_error:
                await self._safe_callback(self.on_server_error, server_name, "Restart failed")
        
        return success
    
    async def get_server_info(self) -> Dict[str, Any]:
        """Get comprehensive information about all servers."""
        status = self.client.get_server_status()
        tools = self.client.get_all_tools()
        resources = self.client.get_all_resources()
        
        info = {}
        for server_name in status.keys():
            info[server_name] = {
                "status": status[server_name],
                "tools": len(tools.get(server_name, [])),
                "resources": len(resources.get(server_name, [])),
                "restart_count": self._server_restart_counts.get(server_name, 0),
                "last_restart": self._last_restart_times.get(server_name)
            }
        
        return info
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], server_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Call a tool, automatically finding the appropriate server if not specified.
        """
        if server_name:
            return await self.client.call_tool(server_name, tool_name, arguments)
        
        # Find server with the tool
        all_tools = self.client.get_all_tools()
        for srv_name, tools in all_tools.items():
            for tool in tools:
                if tool["name"] == tool_name:
                    return await self.client.call_tool(srv_name, tool_name, arguments)
        
        raise ValueError(f"Tool '{tool_name}' not found in any server")
    
    async def get_resource(self, resource_uri: str, server_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get a resource, automatically finding the appropriate server if not specified.
        """
        if server_name:
            return await self.client.get_resource(server_name, resource_uri)
        
        # Find server with the resource
        all_resources = self.client.get_all_resources()
        for srv_name, resources in all_resources.items():
            for resource in resources:
                if resource["uri"] == resource_uri:
                    return await self.client.get_resource(srv_name, resource_uri)
        
        raise ValueError(f"Resource '{resource_uri}' not found in any server")
    
    def list_available_tools(self) -> List[Dict[str, Any]]:
        """List all available tools across all servers."""
        all_tools = []
        server_tools = self.client.get_all_tools()
        
        for server_name, tools in server_tools.items():
            for tool in tools:
                tool_info = tool.copy()
                tool_info["server"] = server_name
                all_tools.append(tool_info)
        
        return all_tools
    
    def list_available_resources(self) -> List[Dict[str, Any]]:
        """List all available resources across all servers."""
        all_resources = []
        server_resources = self.client.get_all_resources()
        
        for server_name, resources in server_resources.items():
            for resource in resources:
                resource_info = resource.copy()
                resource_info["server"] = server_name
                all_resources.append(resource_info)
        
        return all_resources
    
    async def _health_monitor_loop(self):
        """Background task to monitor server health."""
        self.logger.info("Starting MCP server health monitor")
        
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)
                await self._check_server_health()
                
            except asyncio.CancelledError:
                self.logger.info("Health monitor cancelled")
                break
            except Exception as e:
                self.logger.error(f"Health monitor error: {e}")
                await asyncio.sleep(5)  # Brief pause before continuing
    
    async def _check_server_health(self):
        """Check health of all servers and restart failed ones."""
        status = self.client.get_server_status()
        
        for server_name, server_status in status.items():
            if server_status == "error":
                self.logger.warning(f"Server {server_name} is in error state, attempting restart")
                
                # Check if we should attempt restart
                restart_count = self._server_restart_counts.get(server_name, 0)
                if restart_count < self.max_restart_attempts:
                    await asyncio.sleep(self.restart_delay)
                    await self.restart_server(server_name)
                else:
                    self.logger.error(f"Server {server_name} exceeded max restart attempts, giving up")
    
    async def _safe_callback(self, callback: Callable, *args, **kwargs):
        """Safely execute a callback without affecting the main flow."""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(*args, **kwargs)
            else:
                callback(*args, **kwargs)
        except Exception as e:
            self.logger.error(f"Callback error: {e}")
    
    def set_permission_handler(self, handler: Callable[[str, str, Dict], bool]):
        """Set the permission handler for security checks."""
        self.client.set_permission_handler(handler)
    
    def set_callbacks(self, 
                     on_started: Optional[Callable] = None,
                     on_stopped: Optional[Callable] = None,
                     on_error: Optional[Callable] = None):
        """Set event callbacks."""
        if on_started:
            self.on_server_started = on_started
        if on_stopped:
            self.on_server_stopped = on_stopped
        if on_error:
            self.on_server_error = on_error
    
    async def reload_configurations(self) -> bool:
        """Reload configurations and restart affected servers."""
        self.logger.info("Reloading MCP configurations")
        
        # Stop all servers
        await self.stop_all_servers()
        
        # Clear existing configurations
        self.client.servers.clear()
        self._server_restart_counts.clear()
        self._last_restart_times.clear()
        
        # Reload configurations
        success = await self.load_configurations()
        if success:
            # Start servers with new configurations
            await self.start_all_servers()
        
        return success
    
    async def shutdown(self):
        """Gracefully shutdown the MCP manager."""
        self.logger.info("Shutting down MCP Server Manager")
        
        # Cancel health monitor
        if self._health_monitor_task:
            self._health_monitor_task.cancel()
            try:
                await self._health_monitor_task
            except asyncio.CancelledError:
                pass
        
        # Stop all servers
        await self.stop_all_servers()
        
        # Cleanup client
        await self.client.cleanup()
        
        self.logger.info("MCP Server Manager shutdown complete")