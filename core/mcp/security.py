"""
MCP Security Manager for Desktop Agent.

This module provides security and permission management for MCP operations,
including access control, approval workflows, and audit logging.
"""

import logging
from typing import Dict, List, Optional, Any, Callable, Set
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import json
from pathlib import Path

from pydantic import BaseModel


class PermissionLevel(Enum):
    """Permission levels for MCP operations."""
    DENIED = "denied"
    REQUIRE_APPROVAL = "require_approval"
    ALLOWED = "allowed"


class OperationType(Enum):
    """Types of MCP operations."""
    TOOL_CALL = "tool_call"
    RESOURCE_READ = "resource_read"
    SERVER_START = "server_start"
    SERVER_STOP = "server_stop"


class SecurityRule(BaseModel):
    """Security rule for MCP operations."""
    name: str
    operation_type: OperationType
    server_pattern: Optional[str] = None  # regex pattern for server names
    tool_pattern: Optional[str] = None    # regex pattern for tool names
    resource_pattern: Optional[str] = None  # regex pattern for resource URIs
    permission: PermissionLevel
    description: str = ""


class AuditLogEntry(BaseModel):
    """Audit log entry for MCP operations."""
    timestamp: datetime
    operation_type: OperationType
    server_name: str
    tool_name: Optional[str] = None
    resource_uri: Optional[str] = None
    arguments: Optional[Dict[str, Any]] = None
    result: str  # "allowed", "denied", "approved", "rejected"
    user_id: Optional[str] = None
    reason: Optional[str] = None


class PendingApproval(BaseModel):
    """Pending approval request."""
    id: str
    timestamp: datetime
    operation_type: OperationType
    server_name: str
    tool_name: Optional[str] = None
    resource_uri: Optional[str] = None
    arguments: Optional[Dict[str, Any]] = None
    context: Dict[str, Any] = {}
    expires_at: datetime


class MCPSecurityManager:
    """
    Manages security and permissions for MCP operations.
    
    Features:
    - Rule-based access control
    - Approval workflows for sensitive operations
    - Audit logging
    - Rate limiting
    - Security policy enforcement
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.logger = logging.getLogger(__name__)
        self.config = config or {}
        
        # Security rules
        self.rules: List[SecurityRule] = []
        self.default_permission = PermissionLevel.REQUIRE_APPROVAL
        
        # Approval system
        self.pending_approvals: Dict[str, PendingApproval] = {}
        self.approval_timeout = timedelta(minutes=30)
        self.approval_callback: Optional[Callable] = None
        
        # Audit logging
        self.audit_log: List[AuditLogEntry] = []
        self.max_audit_entries = 10000
        self.audit_file: Optional[Path] = None
        
        # Rate limiting
        self.rate_limits: Dict[str, Dict[str, Any]] = {}  # server_name -> rate limit info
        self.default_rate_limit = {"calls_per_minute": 60, "calls_per_hour": 1000}
        
        # Blocked entities
        self.blocked_servers: Set[str] = set()
        self.blocked_tools: Set[str] = set()
        self.blocked_resources: Set[str] = set()
        
        self._load_security_config()
    
    def _load_security_config(self):
        """Load security configuration."""
        security_config = self.config.get("security", {})
        
        # Load audit file path
        audit_file_path = security_config.get("audit_file")
        if audit_file_path:
            self.audit_file = Path(audit_file_path)
            self.audit_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load rate limits
        self.default_rate_limit.update(security_config.get("rate_limits", {}))
        
        # Load blocked entities
        self.blocked_servers.update(security_config.get("blocked_servers", []))
        self.blocked_tools.update(security_config.get("blocked_tools", []))
        self.blocked_resources.update(security_config.get("blocked_resources", []))
        
        # Load security rules
        rules_config = security_config.get("rules", [])
        for rule_data in rules_config:
            try:
                rule = SecurityRule(**rule_data)
                self.rules.append(rule)
                self.logger.info(f"Loaded security rule: {rule.name}")
            except Exception as e:
                self.logger.error(f"Failed to load security rule: {e}")
    
    def add_security_rule(self, rule: SecurityRule):
        """Add a new security rule."""
        self.rules.append(rule)
        self.logger.info(f"Added security rule: {rule.name}")
    
    def remove_security_rule(self, rule_name: str) -> bool:
        """Remove a security rule by name."""
        for i, rule in enumerate(self.rules):
            if rule.name == rule_name:
                del self.rules[i]
                self.logger.info(f"Removed security rule: {rule_name}")
                return True
        return False
    
    async def check_permission(self, 
                             operation_type: OperationType,
                             server_name: str,
                             tool_name: Optional[str] = None,
                             resource_uri: Optional[str] = None,
                             arguments: Optional[Dict[str, Any]] = None,
                             context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Check if an operation is permitted.
        
        Returns:
            Dict with keys: 'allowed', 'requires_approval', 'reason', 'approval_id'
        """
        
        # Check if entities are blocked
        if server_name in self.blocked_servers:
            await self._log_audit(operation_type, server_name, tool_name, resource_uri, 
                                 arguments, "denied", reason="Server blocked")
            return {"allowed": False, "requires_approval": False, "reason": "Server is blocked"}
        
        if tool_name and tool_name in self.blocked_tools:
            await self._log_audit(operation_type, server_name, tool_name, resource_uri, 
                                 arguments, "denied", reason="Tool blocked")
            return {"allowed": False, "requires_approval": False, "reason": "Tool is blocked"}
        
        if resource_uri and resource_uri in self.blocked_resources:
            await self._log_audit(operation_type, server_name, tool_name, resource_uri, 
                                 arguments, "denied", reason="Resource blocked")
            return {"allowed": False, "requires_approval": False, "reason": "Resource is blocked"}
        
        # Check rate limits
        if not self._check_rate_limit(server_name):
            await self._log_audit(operation_type, server_name, tool_name, resource_uri, 
                                 arguments, "denied", reason="Rate limit exceeded")
            return {"allowed": False, "requires_approval": False, "reason": "Rate limit exceeded"}
        
        # Check security rules
        permission = self._evaluate_rules(operation_type, server_name, tool_name, resource_uri, arguments)
        
        if permission == PermissionLevel.ALLOWED:
            await self._log_audit(operation_type, server_name, tool_name, resource_uri, 
                                 arguments, "allowed")
            return {"allowed": True, "requires_approval": False}
        
        elif permission == PermissionLevel.DENIED:
            await self._log_audit(operation_type, server_name, tool_name, resource_uri, 
                                 arguments, "denied", reason="Permission denied by rule")
            return {"allowed": False, "requires_approval": False, "reason": "Permission denied by security rule"}
        
        elif permission == PermissionLevel.REQUIRE_APPROVAL:
            # Create approval request
            approval_id = await self._create_approval_request(
                operation_type, server_name, tool_name, resource_uri, arguments, context or {}
            )
            return {"allowed": False, "requires_approval": True, "approval_id": approval_id}
        
        # Default to requiring approval
        approval_id = await self._create_approval_request(
            operation_type, server_name, tool_name, resource_uri, arguments, context or {}
        )
        return {"allowed": False, "requires_approval": True, "approval_id": approval_id}
    
    def _evaluate_rules(self, 
                       operation_type: OperationType,
                       server_name: str,
                       tool_name: Optional[str] = None,
                       resource_uri: Optional[str] = None,
                       arguments: Optional[Dict[str, Any]] = None) -> PermissionLevel:
        """Evaluate security rules to determine permission level."""
        import re
        
        for rule in self.rules:
            # Check operation type
            if rule.operation_type != operation_type:
                continue
            
            # Check server pattern
            if rule.server_pattern:
                if not re.match(rule.server_pattern, server_name):
                    continue
            
            # Check tool pattern
            if rule.tool_pattern and tool_name:
                if not re.match(rule.tool_pattern, tool_name):
                    continue
            
            # Check resource pattern
            if rule.resource_pattern and resource_uri:
                if not re.match(rule.resource_pattern, resource_uri):
                    continue
            
            # Rule matches, return its permission
            self.logger.debug(f"Security rule '{rule.name}' matched, permission: {rule.permission.value}")
            return rule.permission
        
        # No rule matched, return default
        return self.default_permission
    
    def _check_rate_limit(self, server_name: str) -> bool:
        """Check if the server is within rate limits."""
        now = datetime.now()
        
        if server_name not in self.rate_limits:
            self.rate_limits[server_name] = {
                "minute_calls": [],
                "hour_calls": []
            }
        
        rate_info = self.rate_limits[server_name]
        
        # Clean old entries
        minute_ago = now - timedelta(minutes=1)
        hour_ago = now - timedelta(hours=1)
        
        rate_info["minute_calls"] = [call_time for call_time in rate_info["minute_calls"] if call_time > minute_ago]
        rate_info["hour_calls"] = [call_time for call_time in rate_info["hour_calls"] if call_time > hour_ago]
        
        # Check limits
        if len(rate_info["minute_calls"]) >= self.default_rate_limit["calls_per_minute"]:
            return False
        
        if len(rate_info["hour_calls"]) >= self.default_rate_limit["calls_per_hour"]:
            return False
        
        # Record this call
        rate_info["minute_calls"].append(now)
        rate_info["hour_calls"].append(now)
        
        return True
    
    async def _create_approval_request(self,
                                     operation_type: OperationType,
                                     server_name: str,
                                     tool_name: Optional[str] = None,
                                     resource_uri: Optional[str] = None,
                                     arguments: Optional[Dict[str, Any]] = None,
                                     context: Dict[str, Any] = None) -> str:
        """Create a new approval request."""
        request_data = {
            "operation_type": operation_type.value,
            "server_name": server_name,
            "tool_name": tool_name,
            "resource_uri": resource_uri,
            "arguments": arguments,
            "context": context,
            "timestamp": datetime.now().isoformat()
        }
        
        # Generate unique ID
        request_json = json.dumps(request_data, sort_keys=True)
        approval_id = hashlib.sha256(request_json.encode()).hexdigest()[:16]
        
        # Create approval request
        approval = PendingApproval(
            id=approval_id,
            timestamp=datetime.now(),
            operation_type=operation_type,
            server_name=server_name,
            tool_name=tool_name,
            resource_uri=resource_uri,
            arguments=arguments,
            context=context or {},
            expires_at=datetime.now() + self.approval_timeout
        )
        
        self.pending_approvals[approval_id] = approval
        
        # Trigger approval callback if set
        if self.approval_callback:
            try:
                await self.approval_callback(approval)
            except Exception as e:
                self.logger.error(f"Approval callback error: {e}")
        
        self.logger.info(f"Created approval request: {approval_id}")
        return approval_id
    
    async def approve_request(self, approval_id: str, user_id: Optional[str] = None) -> bool:
        """Approve a pending request."""
        if approval_id not in self.pending_approvals:
            return False
        
        approval = self.pending_approvals[approval_id]
        
        # Check if expired
        if datetime.now() > approval.expires_at:
            del self.pending_approvals[approval_id]
            return False
        
        # Log approval
        await self._log_audit(
            approval.operation_type,
            approval.server_name,
            approval.tool_name,
            approval.resource_uri,
            approval.arguments,
            "approved",
            user_id=user_id
        )
        
        del self.pending_approvals[approval_id]
        self.logger.info(f"Approved request: {approval_id}")
        return True
    
    async def reject_request(self, approval_id: str, reason: str = "", user_id: Optional[str] = None) -> bool:
        """Reject a pending request."""
        if approval_id not in self.pending_approvals:
            return False
        
        approval = self.pending_approvals[approval_id]
        
        # Log rejection
        await self._log_audit(
            approval.operation_type,
            approval.server_name,
            approval.tool_name,
            approval.resource_uri,
            approval.arguments,
            "rejected",
            user_id=user_id,
            reason=reason
        )
        
        del self.pending_approvals[approval_id]
        self.logger.info(f"Rejected request: {approval_id} - {reason}")
        return True
    
    def get_pending_approvals(self) -> List[PendingApproval]:
        """Get all pending approval requests."""
        # Clean expired requests
        now = datetime.now()
        expired_ids = [aid for aid, approval in self.pending_approvals.items() if now > approval.expires_at]
        for aid in expired_ids:
            del self.pending_approvals[aid]
        
        return list(self.pending_approvals.values())
    
    async def _log_audit(self,
                        operation_type: OperationType,
                        server_name: str,
                        tool_name: Optional[str] = None,
                        resource_uri: Optional[str] = None,
                        arguments: Optional[Dict[str, Any]] = None,
                        result: str = "",
                        user_id: Optional[str] = None,
                        reason: Optional[str] = None):
        """Log an audit entry."""
        entry = AuditLogEntry(
            timestamp=datetime.now(),
            operation_type=operation_type,
            server_name=server_name,
            tool_name=tool_name,
            resource_uri=resource_uri,
            arguments=arguments,
            result=result,
            user_id=user_id,
            reason=reason
        )
        
        self.audit_log.append(entry)
        
        # Trim audit log if it gets too large
        if len(self.audit_log) > self.max_audit_entries:
            self.audit_log = self.audit_log[-self.max_audit_entries:]
        
        # Write to audit file if configured
        if self.audit_file:
            try:
                with open(self.audit_file, 'a', encoding='utf-8') as f:
                    f.write(entry.model_dump_json() + '\n')
            except Exception as e:
                self.logger.error(f"Failed to write audit log: {e}")
        
        self.logger.debug(f"Audit: {operation_type.value} on {server_name} - {result}")
    
    def get_audit_log(self, limit: Optional[int] = None) -> List[AuditLogEntry]:
        """Get audit log entries."""
        if limit:
            return self.audit_log[-limit:]
        return self.audit_log.copy()
    
    def set_approval_callback(self, callback: Callable):
        """Set callback function for approval requests."""
        self.approval_callback = callback
    
    def block_server(self, server_name: str):
        """Block a server."""
        self.blocked_servers.add(server_name)
        self.logger.warning(f"Blocked server: {server_name}")
    
    def unblock_server(self, server_name: str):
        """Unblock a server."""
        self.blocked_servers.discard(server_name)
        self.logger.info(f"Unblocked server: {server_name}")
    
    def block_tool(self, tool_name: str):
        """Block a tool."""
        self.blocked_tools.add(tool_name)
        self.logger.warning(f"Blocked tool: {tool_name}")
    
    def unblock_tool(self, tool_name: str):
        """Unblock a tool."""
        self.blocked_tools.discard(tool_name)
        self.logger.info(f"Unblocked tool: {tool_name}")
    
    def get_security_status(self) -> Dict[str, Any]:
        """Get current security status."""
        return {
            "rules_count": len(self.rules),
            "pending_approvals": len(self.pending_approvals),
            "blocked_servers": len(self.blocked_servers),
            "blocked_tools": len(self.blocked_tools),
            "blocked_resources": len(self.blocked_resources),
            "audit_entries": len(self.audit_log)
        }