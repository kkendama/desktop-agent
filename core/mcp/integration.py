"""
MCP Integration for Desktop Agent.

This module provides the main integration point for MCP functionality,
coordinating between the manager, security, and configuration components.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable

from .manager import MCPServerManager
from .security import MCPSecurityManager, OperationType
from .config import MCPConfigManager


class MCPIntegration:
    """
    Main MCP integration class for Desktop Agent.
    
    This class serves as the primary interface for all MCP functionality,
    coordinating between configuration, security, and server management.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        self.logger = logging.getLogger(__name__)
        
        # Initialize components
        self.config_manager = MCPConfigManager(config_path or "config/system.yaml")
        self.server_manager = MCPServerManager(config_path or "config/system.yaml")
        self.security_manager: Optional[MCPSecurityManager] = None
        
        # State
        self.is_initialized = False
        self.auto_approve_callback: Optional[Callable] = None
        
        # Integration callbacks
        self.on_tool_call: Optional[Callable] = None
        self.on_resource_access: Optional[Callable] = None
        self.on_server_event: Optional[Callable] = None
    
    async def initialize(self) -> bool:
        """Initialize the MCP integration system."""
        try:
            self.logger.info("Initializing MCP Integration")
            
            # Load configuration
            if not self.config_manager.load_config():
                self.logger.error("Failed to load MCP configuration")
                return False
            
            # Check if MCP is enabled
            if not self.config_manager.is_enabled():
                self.logger.info("MCP is disabled in configuration")
                return True
            
            # Initialize security manager with configuration
            security_config = self.config_manager.get_security_config()
            self.security_manager = MCPSecurityManager(security_config)
            
            # Set up security approval callback
            if self.auto_approve_callback:
                self.security_manager.set_approval_callback(self._handle_approval_request)
            
            # Set up server manager with security
            self.server_manager.set_permission_handler(self._permission_handler)
            
            # Set up server event callbacks
            self.server_manager.set_callbacks(
                on_started=self._on_server_started,
                on_stopped=self._on_server_stopped,
                on_error=self._on_server_error
            )
            
            # Initialize server manager
            if not await self.server_manager.initialize():
                self.logger.error("Failed to initialize MCP server manager")
                return False
            
            # Start all configured servers
            start_results = await self.server_manager.start_all_servers()
            successful_starts = sum(1 for success in start_results.values() if success)
            
            self.logger.info(f"MCP Integration initialized: {successful_starts}/{len(start_results)} servers started")
            self.is_initialized = True
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize MCP integration: {e}")
            return False
    
    async def call_tool(self, 
                       tool_name: str, 
                       arguments: Dict[str, Any], 
                       server_name: Optional[str] = None,
                       context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Call an MCP tool with security checks.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Arguments to pass to the tool
            server_name: Specific server to use (auto-detect if None)
            context: Additional context for security evaluation
            
        Returns:
            Dictionary with result or error information
        """
        if not self.is_initialized:
            return {"success": False, "error": "MCP not initialized"}
        
        try:
            # Determine server if not specified
            if not server_name:
                all_tools = self.server_manager.list_available_tools()
                matching_tools = [t for t in all_tools if t["name"] == tool_name]
                if not matching_tools:
                    return {"success": False, "error": f"Tool '{tool_name}' not found"}
                server_name = matching_tools[0]["server"]
            
            # Security check
            if self.security_manager:
                permission_result = await self.security_manager.check_permission(
                    OperationType.TOOL_CALL,
                    server_name,
                    tool_name=tool_name,
                    arguments=arguments,
                    context=context
                )
                
                if not permission_result["allowed"]:
                    if permission_result["requires_approval"]:
                        return {
                            "success": False,
                            "requires_approval": True,
                            "approval_id": permission_result["approval_id"],
                            "message": "Operation requires approval"
                        }
                    else:
                        return {
                            "success": False,
                            "error": permission_result["reason"]
                        }
            
            # Call the tool
            result = await self.server_manager.call_tool(tool_name, arguments, server_name)
            
            # Trigger callback if set
            if self.on_tool_call:
                await self._safe_callback(self.on_tool_call, tool_name, arguments, result)
            
            return result
            
        except Exception as e:
            self.logger.error(f"Tool call failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_resource(self, 
                          resource_uri: str, 
                          server_name: Optional[str] = None,
                          context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Get an MCP resource with security checks.
        
        Args:
            resource_uri: URI of the resource to access
            server_name: Specific server to use (auto-detect if None)
            context: Additional context for security evaluation
            
        Returns:
            Dictionary with resource contents or error information
        """
        if not self.is_initialized:
            return {"success": False, "error": "MCP not initialized"}
        
        try:
            # Determine server if not specified
            if not server_name:
                all_resources = self.server_manager.list_available_resources()
                matching_resources = [r for r in all_resources if r["uri"] == resource_uri]
                if not matching_resources:
                    return {"success": False, "error": f"Resource '{resource_uri}' not found"}
                server_name = matching_resources[0]["server"]
            
            # Security check
            if self.security_manager:
                permission_result = await self.security_manager.check_permission(
                    OperationType.RESOURCE_READ,
                    server_name,
                    resource_uri=resource_uri,
                    context=context
                )
                
                if not permission_result["allowed"]:
                    if permission_result["requires_approval"]:
                        return {
                            "success": False,
                            "requires_approval": True,
                            "approval_id": permission_result["approval_id"],
                            "message": "Operation requires approval"
                        }
                    else:
                        return {
                            "success": False,
                            "error": permission_result["reason"]
                        }
            
            # Get the resource
            result = await self.server_manager.get_resource(resource_uri, server_name)
            
            # Trigger callback if set
            if self.on_resource_access:
                await self._safe_callback(self.on_resource_access, resource_uri, result)
            
            return result
            
        except Exception as e:
            self.logger.error(f"Resource access failed: {e}")
            return {"success": False, "error": str(e)}
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools across all servers."""
        if not self.is_initialized:
            return []
        
        return self.server_manager.list_available_tools()
    
    def list_resources(self) -> List[Dict[str, Any]]:
        """List all available resources across all servers."""
        if not self.is_initialized:
            return []
        
        return self.server_manager.list_available_resources()
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status of the MCP system."""
        if not self.is_initialized:
            return {"status": "not_initialized"}
        
        status = {
            "status": "initialized",
            "config": self.config_manager.get_config_summary(),
            "servers": self.server_manager.get_server_info(),
            "tools": len(self.list_tools()),
            "resources": len(self.list_resources())
        }
        
        if self.security_manager:
            status["security"] = self.security_manager.get_security_status()
        
        return status
    
    async def approve_pending_request(self, approval_id: str, user_id: Optional[str] = None) -> bool:
        """Approve a pending security request."""
        if not self.security_manager:
            return False
        
        return await self.security_manager.approve_request(approval_id, user_id)
    
    async def reject_pending_request(self, approval_id: str, reason: str = "", user_id: Optional[str] = None) -> bool:
        """Reject a pending security request."""
        if not self.security_manager:
            return False
        
        return await self.security_manager.reject_request(approval_id, reason, user_id)
    
    def get_pending_approvals(self) -> List[Dict[str, Any]]:
        """Get all pending approval requests."""
        if not self.security_manager:
            return []
        
        approvals = self.security_manager.get_pending_approvals()
        return [approval.model_dump() for approval in approvals]
    
    def get_audit_log(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get audit log entries."""
        if not self.security_manager:
            return []
        
        entries = self.security_manager.get_audit_log(limit)
        return [entry.model_dump() for entry in entries]
    
    async def restart_server(self, server_name: str) -> bool:
        """Restart a specific MCP server."""
        if not self.is_initialized:
            return False
        
        return await self.server_manager.restart_server(server_name)
    
    async def reload_configuration(self) -> bool:
        """Reload MCP configuration and restart servers."""
        if not self.is_initialized:
            return False
        
        try:
            self.logger.info("Reloading MCP configuration")
            
            # Reload configuration
            if not self.config_manager.reload_config():
                return False
            
            # Check if still enabled
            if not self.config_manager.is_enabled():
                await self.shutdown()
                return True
            
            # Reload server manager
            success = await self.server_manager.reload_configurations()
            
            # Update security manager
            if self.security_manager:
                security_config = self.config_manager.get_security_config()
                self.security_manager.__init__(security_config)
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to reload configuration: {e}")
            return False
    
    def set_callbacks(self,
                     on_tool_call: Optional[Callable] = None,
                     on_resource_access: Optional[Callable] = None,
                     on_server_event: Optional[Callable] = None,
                     auto_approve_callback: Optional[Callable] = None):
        """Set integration callbacks."""
        if on_tool_call:
            self.on_tool_call = on_tool_call
        if on_resource_access:
            self.on_resource_access = on_resource_access
        if on_server_event:
            self.on_server_event = on_server_event
        if auto_approve_callback:
            self.auto_approve_callback = auto_approve_callback
    
    async def _permission_handler(self, server_name: str, operation_type: str, context: Dict[str, Any]) -> bool:
        """Handle permission checks for the server manager."""
        if not self.security_manager:
            return True  # Allow if no security manager
        
        try:
            # Convert operation type
            if operation_type == "tool":
                op_type = OperationType.TOOL_CALL
            elif operation_type == "resource":
                op_type = OperationType.RESOURCE_READ
            else:
                return True  # Unknown operation type, allow by default
            
            # Check permission
            result = await self.security_manager.check_permission(
                op_type, server_name, context=context
            )
            
            return result["allowed"]
            
        except Exception as e:
            self.logger.error(f"Permission check failed: {e}")
            return False
    
    async def _handle_approval_request(self, approval):
        """Handle approval requests through callback."""
        if self.auto_approve_callback:
            try:
                should_approve = await self.auto_approve_callback(approval.model_dump())
                if should_approve:
                    await self.security_manager.approve_request(approval.id)
                else:
                    await self.security_manager.reject_request(approval.id, "Auto-rejected")
            except Exception as e:
                self.logger.error(f"Auto-approval callback failed: {e}")
    
    async def _on_server_started(self, server_name: str):
        """Handle server started event."""
        self.logger.info(f"MCP server started: {server_name}")
        if self.on_server_event:
            await self._safe_callback(self.on_server_event, "started", server_name)
    
    async def _on_server_stopped(self, server_name: str):
        """Handle server stopped event."""
        self.logger.info(f"MCP server stopped: {server_name}")
        if self.on_server_event:
            await self._safe_callback(self.on_server_event, "stopped", server_name)
    
    async def _on_server_error(self, server_name: str, error: str):
        """Handle server error event."""
        self.logger.error(f"MCP server error: {server_name} - {error}")
        if self.on_server_event:
            await self._safe_callback(self.on_server_event, "error", server_name, error)
    
    async def _safe_callback(self, callback: Callable, *args, **kwargs):
        """Safely execute a callback without affecting the main flow."""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(*args, **kwargs)
            else:
                callback(*args, **kwargs)
        except Exception as e:
            self.logger.error(f"Callback error: {e}")
    
    async def shutdown(self):
        """Gracefully shutdown the MCP integration."""
        self.logger.info("Shutting down MCP Integration")
        
        if self.server_manager:
            await self.server_manager.shutdown()
        
        self.is_initialized = False
        self.logger.info("MCP Integration shutdown complete")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self.is_initialized:
            asyncio.create_task(self.shutdown())
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.shutdown()