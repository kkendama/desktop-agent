"""
MCP Configuration Manager for Desktop Agent.

This module handles loading and managing MCP configurations from system.yaml,
providing dynamic configuration updates and validation.
"""

import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
import yaml

from pydantic import BaseModel, validator

from .client import MCPServerConfig
from .security import SecurityRule, PermissionLevel, OperationType


class MCPConfig(BaseModel):
    """Main MCP configuration."""
    enabled: bool = True
    servers: List[MCPServerConfig] = []
    security: Dict[str, Any] = {}
    global_settings: Dict[str, Any] = {}


class MCPConfigManager:
    """
    Manages MCP configuration loading and validation.
    
    Features:
    - Load configurations from system.yaml
    - Validate configuration structure
    - Hot-reload configuration changes
    - Provide configuration to other MCP components
    """
    
    def __init__(self, config_path: str = "config/system.yaml"):
        self.logger = logging.getLogger(__name__)
        self.config_path = Path(config_path)
        self.config: Optional[MCPConfig] = None
        
        # Configuration validation rules
        self.required_server_fields = ["name", "command"]
        self.valid_permission_operations = [op.value for op in OperationType]
        self.valid_permission_levels = [level.value for level in PermissionLevel]
        
    def load_config(self) -> bool:
        """Load MCP configuration from file."""
        try:
            if not self.config_path.exists():
                self.logger.error(f"Configuration file not found: {self.config_path}")
                return False
            
            self.logger.info(f"Loading MCP configuration from {self.config_path}")
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                full_config = yaml.safe_load(f)
            
            mcp_section = full_config.get('mcp', {})
            
            # Parse and validate configuration
            self.config = self._parse_config(mcp_section)
            
            if self.config:
                self.logger.info(f"Loaded MCP configuration: {len(self.config.servers)} servers")
                return True
            else:
                self.logger.error("Failed to parse MCP configuration")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to load MCP configuration: {e}")
            return False
    
    def _parse_config(self, mcp_config: Dict[str, Any]) -> Optional[MCPConfig]:
        """Parse and validate MCP configuration."""
        try:
            # Parse basic settings
            enabled = mcp_config.get('enabled', True)
            
            # Parse server configurations
            servers = []
            servers_config = mcp_config.get('servers', [])
            
            for i, server_data in enumerate(servers_config):
                try:
                    # Validate required fields
                    for field in self.required_server_fields:
                        if field not in server_data:
                            raise ValueError(f"Missing required field '{field}' in server config {i}")
                    
                    # Create server config
                    server_config = MCPServerConfig(**server_data)
                    servers.append(server_config)
                    
                    self.logger.debug(f"Parsed server config: {server_config.name}")
                    
                except Exception as e:
                    self.logger.error(f"Failed to parse server config {i}: {e}")
                    continue
            
            # Parse security configuration
            security_config = mcp_config.get('security', {})
            validated_security = self._validate_security_config(security_config)
            
            # Parse global settings
            global_settings = mcp_config.get('global_settings', {})
            
            return MCPConfig(
                enabled=enabled,
                servers=servers,
                security=validated_security,
                global_settings=global_settings
            )
            
        except Exception as e:
            self.logger.error(f"Failed to parse MCP configuration: {e}")
            return None
    
    def _validate_security_config(self, security_config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate security configuration."""
        validated = {}
        
        # Validate audit settings
        if 'audit_file' in security_config:
            audit_file = Path(security_config['audit_file'])
            try:
                # Ensure directory exists
                audit_file.parent.mkdir(parents=True, exist_ok=True)
                validated['audit_file'] = str(audit_file)
            except Exception as e:
                self.logger.warning(f"Invalid audit file path: {e}")
        
        # Validate rate limits
        rate_limits = security_config.get('rate_limits', {})
        if rate_limits:
            validated_rate_limits = {}
            
            if 'calls_per_minute' in rate_limits:
                try:
                    validated_rate_limits['calls_per_minute'] = int(rate_limits['calls_per_minute'])
                except ValueError:
                    self.logger.warning("Invalid calls_per_minute value, using default")
            
            if 'calls_per_hour' in rate_limits:
                try:
                    validated_rate_limits['calls_per_hour'] = int(rate_limits['calls_per_hour'])
                except ValueError:
                    self.logger.warning("Invalid calls_per_hour value, using default")
            
            if validated_rate_limits:
                validated['rate_limits'] = validated_rate_limits
        
        # Validate blocked entities
        for entity_type in ['blocked_servers', 'blocked_tools', 'blocked_resources']:
            if entity_type in security_config:
                entity_list = security_config[entity_type]
                if isinstance(entity_list, list):
                    validated[entity_type] = [str(item) for item in entity_list]
                else:
                    self.logger.warning(f"Invalid {entity_type} format, expected list")
        
        # Validate security rules
        rules_config = security_config.get('rules', [])
        if rules_config:
            validated_rules = []
            
            for i, rule_data in enumerate(rules_config):
                try:
                    validated_rule = self._validate_security_rule(rule_data)
                    if validated_rule:
                        validated_rules.append(validated_rule)
                except Exception as e:
                    self.logger.error(f"Failed to validate security rule {i}: {e}")
            
            if validated_rules:
                validated['rules'] = validated_rules
        
        return validated
    
    def _validate_security_rule(self, rule_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Validate a single security rule."""
        required_fields = ['name', 'operation_type', 'permission']
        
        # Check required fields
        for field in required_fields:
            if field not in rule_data:
                raise ValueError(f"Missing required field '{field}' in security rule")
        
        # Validate operation type
        operation_type = rule_data['operation_type']
        if operation_type not in self.valid_permission_operations:
            raise ValueError(f"Invalid operation_type: {operation_type}")
        
        # Validate permission level
        permission = rule_data['permission']
        if permission not in self.valid_permission_levels:
            raise ValueError(f"Invalid permission level: {permission}")
        
        # Build validated rule
        validated_rule = {
            'name': str(rule_data['name']),
            'operation_type': operation_type,
            'permission': permission
        }
        
        # Add optional fields
        for optional_field in ['server_pattern', 'tool_pattern', 'resource_pattern', 'description']:
            if optional_field in rule_data:
                validated_rule[optional_field] = str(rule_data[optional_field])
        
        return validated_rule
    
    def get_config(self) -> Optional[MCPConfig]:
        """Get the current configuration."""
        return self.config
    
    def get_servers_config(self) -> List[MCPServerConfig]:
        """Get server configurations."""
        if self.config:
            return self.config.servers
        return []
    
    def get_security_config(self) -> Dict[str, Any]:
        """Get security configuration."""
        if self.config:
            return self.config.security
        return {}
    
    def get_global_settings(self) -> Dict[str, Any]:
        """Get global settings."""
        if self.config:
            return self.config.global_settings
        return {}
    
    def is_enabled(self) -> bool:
        """Check if MCP is enabled."""
        if self.config:
            return self.config.enabled
        return False
    
    def validate_server_config(self, server_config: Dict[str, Any]) -> List[str]:
        """Validate a server configuration and return any errors."""
        errors = []
        
        # Check required fields
        for field in self.required_server_fields:
            if field not in server_config:
                errors.append(f"Missing required field: {field}")
        
        # Validate name
        if 'name' in server_config:
            name = server_config['name']
            if not isinstance(name, str) or not name.strip():
                errors.append("Server name must be a non-empty string")
        
        # Validate command
        if 'command' in server_config:
            command = server_config['command']
            if not isinstance(command, list) or not command:
                errors.append("Command must be a non-empty list")
            elif not all(isinstance(item, str) for item in command):
                errors.append("All command items must be strings")
        
        # Validate environment variables
        if 'env' in server_config:
            env = server_config['env']
            if not isinstance(env, dict):
                errors.append("Environment variables must be a dictionary")
            elif not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
                errors.append("All environment variable keys and values must be strings")
        
        # Validate permissions
        if 'permissions' in server_config:
            permissions = server_config['permissions']
            if not isinstance(permissions, dict):
                errors.append("Permissions must be a dictionary")
            else:
                for key, value in permissions.items():
                    if not isinstance(value, bool):
                        errors.append(f"Permission '{key}' must be a boolean value")
        
        return errors
    
    def reload_config(self) -> bool:
        """Reload configuration from file."""
        self.logger.info("Reloading MCP configuration")
        return self.load_config()
    
    def watch_config_file(self, callback: Optional[callable] = None):
        """Watch configuration file for changes (basic implementation)."""
        # This is a basic implementation - in production, you might want to use
        # a proper file watching library like watchdog
        import time
        import threading
        
        def watch_loop():
            last_modified = None
            while True:
                try:
                    if self.config_path.exists():
                        current_modified = self.config_path.stat().st_mtime
                        if last_modified is not None and current_modified > last_modified:
                            self.logger.info("Configuration file changed, reloading...")
                            if self.reload_config() and callback:
                                callback()
                        last_modified = current_modified
                    time.sleep(5)  # Check every 5 seconds
                except Exception as e:
                    self.logger.error(f"Error watching config file: {e}")
                    time.sleep(10)
        
        # Run in background thread
        thread = threading.Thread(target=watch_loop, daemon=True)
        thread.start()
        self.logger.info("Started watching configuration file for changes")
    
    def export_config_template(self, output_path: str) -> bool:
        """Export a configuration template file."""
        template = {
            'mcp': {
                'enabled': True,
                'servers': [
                    {
                        'name': 'example-server',
                        'description': 'Example MCP server',
                        'command': ['python', '-m', 'example_mcp_server'],
                        'env': {},
                        'permissions': {
                            'read': True,
                            'write': False,
                            'execute': True
                        },
                        'enabled': True
                    }
                ],
                'security': {
                    'audit_file': 'data/logs/mcp_audit.log',
                    'rate_limits': {
                        'calls_per_minute': 60,
                        'calls_per_hour': 1000
                    },
                    'blocked_servers': [],
                    'blocked_tools': [],
                    'blocked_resources': [],
                    'rules': [
                        {
                            'name': 'allow-read-operations',
                            'operation_type': 'resource_read',
                            'permission': 'allowed',
                            'description': 'Allow all resource read operations'
                        },
                        {
                            'name': 'require-approval-for-file-write',
                            'operation_type': 'tool_call',
                            'tool_pattern': '.*write.*|.*delete.*',
                            'permission': 'require_approval',
                            'description': 'Require approval for file write/delete operations'
                        }
                    ]
                },
                'global_settings': {
                    'default_timeout': 30,
                    'max_concurrent_calls': 10
                }
            }
        }
        
        try:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                yaml.dump(template, f, default_flow_style=False, sort_keys=False)
            
            self.logger.info(f"Exported configuration template to {output_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to export configuration template: {e}")
            return False
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Get a summary of the current configuration."""
        if not self.config:
            return {"status": "not_loaded"}
        
        return {
            "status": "loaded",
            "enabled": self.config.enabled,
            "servers_count": len(self.config.servers),
            "enabled_servers": len([s for s in self.config.servers if s.enabled]),
            "security_rules": len(self.config.security.get('rules', [])),
            "has_audit_logging": 'audit_file' in self.config.security,
            "blocked_entities": {
                "servers": len(self.config.security.get('blocked_servers', [])),
                "tools": len(self.config.security.get('blocked_tools', [])),
                "resources": len(self.config.security.get('blocked_resources', []))
            }
        }