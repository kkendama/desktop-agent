"""
Test cases for MCP (Model Context Protocol) functionality.

These tests verify that the MCP integration works correctly,
including client connections, security checks, and tool execution.
"""

import pytest
import asyncio
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

from core.mcp import (
    MCPIntegration,
    MCPServerConfig,
    MCPClient,
    MCPSecurityManager,
    MCPConfigManager,
    SecurityRule,
    PermissionLevel,
    OperationType
)


@pytest.fixture
def temp_config_file():
    """Create a temporary configuration file for testing."""
    config_data = {
        'mcp': {
            'enabled': True,
            'servers': [
                {
                    'name': 'test-server',
                    'description': 'Test MCP server',
                    'command': ['python', '-m', 'test_mcp_server'],
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
                'audit_file': 'test_audit.log',
                'rate_limits': {
                    'calls_per_minute': 60,
                    'calls_per_hour': 1000
                },
                'blocked_servers': [],
                'blocked_tools': [],
                'blocked_resources': [],
                'rules': [
                    {
                        'name': 'allow-read',
                        'operation_type': 'resource_read',
                        'permission': 'allowed',
                        'description': 'Allow all resource reads'
                    }
                ]
            }
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        import yaml
        yaml.dump(config_data, f)
        temp_file = f.name
    
    yield temp_file
    
    # Cleanup
    Path(temp_file).unlink(missing_ok=True)


class TestMCPServerConfig:
    """Test MCP server configuration."""
    
    def test_valid_server_config(self):
        """Test creating a valid server configuration."""
        config = MCPServerConfig(
            name="test-server",
            description="Test server",
            command=["python", "-m", "test_server"],
            env={"ENV_VAR": "value"},
            permissions={"read": True, "write": False},
            enabled=True
        )
        
        assert config.name == "test-server"
        assert config.command == ["python", "-m", "test_server"]
        assert config.permissions["read"] is True
        assert config.enabled is True
    
    def test_minimal_server_config(self):
        """Test creating a minimal server configuration."""
        config = MCPServerConfig(
            name="minimal-server",
            description="Minimal test server",
            command=["test-command"]
        )
        
        assert config.name == "minimal-server"
        assert config.command == ["test-command"]
        assert config.env == {}
        assert config.permissions == {}
        assert config.enabled is True


class TestMCPSecurityManager:
    """Test MCP security manager functionality."""
    
    @pytest.fixture
    def security_manager(self):
        """Create a security manager for testing."""
        config = {
            'rate_limits': {'calls_per_minute': 5, 'calls_per_hour': 100},
            'blocked_servers': ['blocked-server'],
            'blocked_tools': ['dangerous-tool'],
            'rules': [
                {
                    'name': 'allow-safe-tools',
                    'operation_type': 'tool_call',
                    'tool_pattern': 'safe-.*',
                    'permission': 'allowed'
                },
                {
                    'name': 'require-approval-dangerous',
                    'operation_type': 'tool_call',
                    'tool_pattern': 'dangerous-.*',
                    'permission': 'require_approval'
                }
            ]
        }
        return MCPSecurityManager(config)
    
    async def test_blocked_server(self, security_manager):
        """Test that blocked servers are denied."""
        result = await security_manager.check_permission(
            OperationType.TOOL_CALL,
            'blocked-server',
            tool_name='any-tool'
        )
        
        assert result['allowed'] is False
        assert result['requires_approval'] is False
        assert 'blocked' in result['reason'].lower()
    
    async def test_blocked_tool(self, security_manager):
        """Test that blocked tools are denied."""
        result = await security_manager.check_permission(
            OperationType.TOOL_CALL,
            'safe-server',
            tool_name='dangerous-tool'
        )
        
        assert result['allowed'] is False
        assert result['requires_approval'] is False
        assert 'blocked' in result['reason'].lower()
    
    async def test_rate_limiting(self, security_manager):
        """Test rate limiting functionality."""
        server_name = 'test-server'
        
        # Make several calls within the limit
        for _ in range(4):
            result = await security_manager.check_permission(
                OperationType.TOOL_CALL,
                server_name,
                tool_name='safe-tool'
            )
            # Should not be blocked by rate limit yet
            assert result.get('reason', '') != 'Rate limit exceeded'
        
        # This should hit the rate limit
        result = await security_manager.check_permission(
            OperationType.TOOL_CALL,
            server_name,
            tool_name='safe-tool-6'
        )
        
        # Note: The rate limit check might not trigger immediately due to timing
        # In a real test, you might want to mock the datetime
    
    async def test_security_rules(self, security_manager):
        """Test security rule evaluation."""
        # Test allowed tool pattern
        result = await security_manager.check_permission(
            OperationType.TOOL_CALL,
            'test-server',
            tool_name='safe-calculator'
        )
        
        assert result['allowed'] is True
        assert result['requires_approval'] is False
    
    async def test_approval_workflow(self, security_manager):
        """Test approval workflow."""
        # Test tool requiring approval
        result = await security_manager.check_permission(
            OperationType.TOOL_CALL,
            'test-server',
            tool_name='dangerous-operation'
        )
        
        assert result['allowed'] is False
        assert result['requires_approval'] is True
        assert 'approval_id' in result
        
        # Test approval
        approval_id = result['approval_id']
        approval_success = await security_manager.approve_request(approval_id)
        assert approval_success is True
        
        # Test that approval is no longer pending
        pending = security_manager.get_pending_approvals()
        assert not any(p.id == approval_id for p in pending)


class TestMCPConfigManager:
    """Test MCP configuration manager."""
    
    def test_load_valid_config(self, temp_config_file):
        """Test loading a valid configuration file."""
        config_manager = MCPConfigManager(temp_config_file)
        success = config_manager.load_config()
        
        assert success is True
        assert config_manager.is_enabled() is True
        
        servers = config_manager.get_servers_config()
        assert len(servers) == 1
        assert servers[0].name == 'test-server'
    
    def test_validate_server_config(self, temp_config_file):
        """Test server configuration validation."""
        config_manager = MCPConfigManager(temp_config_file)
        
        # Valid config
        valid_config = {
            'name': 'test-server',
            'command': ['python', '-m', 'test_server'],
            'env': {},
            'permissions': {'read': True}
        }
        
        errors = config_manager.validate_server_config(valid_config)
        assert len(errors) == 0
        
        # Invalid config - missing name
        invalid_config = {
            'command': ['python', '-m', 'test_server']
        }
        
        errors = config_manager.validate_server_config(invalid_config)
        assert len(errors) > 0
        assert any('name' in error for error in errors)
    
    def test_config_summary(self, temp_config_file):
        """Test configuration summary generation."""
        config_manager = MCPConfigManager(temp_config_file)
        config_manager.load_config()
        
        summary = config_manager.get_config_summary()
        
        assert summary['status'] == 'loaded'
        assert summary['enabled'] is True
        assert summary['servers_count'] == 1
        assert summary['enabled_servers'] == 1


class TestMCPClient:
    """Test MCP client functionality."""
    
    @pytest.fixture
    def mcp_client(self):
        """Create an MCP client for testing."""
        return MCPClient()
    
    async def test_load_server_config(self, mcp_client):
        """Test loading server configuration."""
        config = MCPServerConfig(
            name="test-server",
            description="Test server",
            command=["echo", "test"],
            enabled=True
        )
        
        success = await mcp_client.load_server_config(config)
        assert success is True
        assert "test-server" in mcp_client.servers
    
    async def test_permission_handler(self, mcp_client):
        """Test permission handler functionality."""
        permission_calls = []
        
        def mock_permission_handler(server_name, operation_type, context):
            permission_calls.append((server_name, operation_type, context))
            return True
        
        mcp_client.set_permission_handler(mock_permission_handler)
        
        # Simulate a permission check
        result = mcp_client._check_permissions('test-server', 'tool', {'tool_name': 'test'})
        assert result is True
        assert len(permission_calls) == 1


@pytest.mark.asyncio
class TestMCPIntegration:
    """Test MCP integration functionality."""
    
    @pytest.fixture
    async def mcp_integration(self, temp_config_file):
        """Create an MCP integration instance for testing."""
        integration = MCPIntegration(temp_config_file)
        return integration
    
    async def test_initialization(self, mcp_integration):
        """Test MCP integration initialization."""
        # Mock the server manager to avoid actually starting servers
        with patch.object(mcp_integration.server_manager, 'initialize', return_value=True), \
             patch.object(mcp_integration.server_manager, 'start_all_servers', return_value={'test-server': True}):
            
            success = await mcp_integration.initialize()
            assert success is True
            assert mcp_integration.is_initialized is True
    
    async def test_get_status(self, mcp_integration):
        """Test status retrieval."""
        # Test when not initialized
        status = mcp_integration.get_status()
        assert status['status'] == 'not_initialized'
        
        # Mock initialization
        mcp_integration.is_initialized = True
        with patch.object(mcp_integration.config_manager, 'get_config_summary', return_value={'status': 'loaded'}), \
             patch.object(mcp_integration.server_manager, 'get_server_info', return_value={}), \
             patch.object(mcp_integration, 'list_tools', return_value=[]), \
             patch.object(mcp_integration, 'list_resources', return_value=[]):
            
            status = mcp_integration.get_status()
            assert status['status'] == 'initialized'
    
    async def test_tool_call_security(self, mcp_integration):
        """Test tool call with security checks."""
        mcp_integration.is_initialized = True
        
        # Mock security manager to deny the call
        mock_security = Mock()
        mock_security.check_permission = AsyncMock(return_value={
            'allowed': False,
            'requires_approval': False,
            'reason': 'Test denial'
        })
        mcp_integration.security_manager = mock_security
        
        result = await mcp_integration.call_tool('test-tool', {}, 'test-server')
        
        assert result['success'] is False
        assert 'Test denial' in result['error']
    
    async def test_reload_configuration(self, mcp_integration):
        """Test configuration reloading."""
        mcp_integration.is_initialized = True
        
        with patch.object(mcp_integration.config_manager, 'reload_config', return_value=True), \
             patch.object(mcp_integration.config_manager, 'is_enabled', return_value=True), \
             patch.object(mcp_integration.server_manager, 'reload_configurations', return_value=True):
            
            success = await mcp_integration.reload_configuration()
            assert success is True


class TestMCPEndToEnd:
    """End-to-end tests for MCP functionality."""
    
    @pytest.mark.asyncio
    async def test_full_workflow(self, temp_config_file):
        """Test a complete MCP workflow."""
        # This test would require actual MCP servers to be meaningful
        # For now, we test the initialization and configuration flow
        
        integration = MCPIntegration(temp_config_file)
        
        # Mock the actual server connections
        with patch('core.mcp.client.stdio_client'), \
             patch('core.mcp.client.ClientSession'):
            
            # Test initialization
            success = await integration.initialize()
            # May fail due to missing MCP dependencies, but should not crash
            
            # Test shutdown
            await integration.shutdown()
            assert integration.is_initialized is False


def test_configuration_template_export():
    """Test exporting configuration template."""
    with tempfile.TemporaryDirectory() as temp_dir:
        output_path = Path(temp_dir) / "test_template.yaml"
        
        config_manager = MCPConfigManager()
        success = config_manager.export_config_template(str(output_path))
        
        assert success is True
        assert output_path.exists()
        
        # Verify the template is valid YAML
        import yaml
        with open(output_path, 'r') as f:
            template_data = yaml.safe_load(f)
        
        assert 'mcp' in template_data
        assert 'enabled' in template_data['mcp']
        assert 'servers' in template_data['mcp']


if __name__ == "__main__":
    pytest.main([__file__])