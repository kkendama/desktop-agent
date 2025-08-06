#!/usr/bin/env python3
"""
MCP Integration Example for Desktop Agent

This example demonstrates how to use the MCP integration functionality
to call tools and access resources through MCP servers.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path to import core modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.mcp import MCPIntegration


async def main():
    """Main example function."""
    print("🤖 Desktop Agent MCP Integration Example")
    print("=" * 50)
    
    # Initialize MCP integration
    mcp = MCPIntegration()
    
    try:
        # Initialize the MCP system
        print("📡 Initializing MCP integration...")
        success = await mcp.initialize()
        
        if not success:
            print("❌ Failed to initialize MCP integration")
            print("💡 Make sure you have MCP servers configured in config/system.yaml")
            return
        
        print("✅ MCP integration initialized successfully!")
        print()
        
        # Display system status
        print("📊 System Status:")
        status = mcp.get_status()
        print(f"   Status: {status.get('status', 'unknown')}")
        print(f"   Tools: {status.get('tools', 0)}")
        print(f"   Resources: {status.get('resources', 0)}")
        print(f"   Servers: {len(status.get('servers', {}))}")
        print()
        
        # List available tools
        print("🛠️  Available Tools:")
        tools = mcp.list_tools()
        if tools:
            for tool in tools:
                print(f"   - {tool['name']} (from {tool['server']})")
                print(f"     Description: {tool.get('description', 'No description')}")
        else:
            print("   No tools available")
        print()
        
        # List available resources
        print("📚 Available Resources:")
        resources = mcp.list_resources()
        if resources:
            for resource in resources:
                print(f"   - {resource['uri']} (from {resource['server']})")
                print(f"     Name: {resource.get('name', 'Unnamed')}")
        else:
            print("   No resources available")
        print()
        
        # Example tool calls (these will only work if appropriate servers are configured)
        await example_tool_calls(mcp)
        
        # Example resource access
        await example_resource_access(mcp)
        
        # Show security status
        await show_security_status(mcp)
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    finally:
        # Cleanup
        print("🧹 Cleaning up...")
        await mcp.shutdown()
        print("👋 Example completed!")


async def example_tool_calls(mcp: MCPIntegration):
    """Demonstrate tool calling."""
    print("🔧 Example Tool Calls:")
    print("-" * 20)
    
    # Example 1: File reading (if file-ops server is available)
    try:
        result = await mcp.call_tool(
            "read_file",
            {"path": "README.md"},
            context={"example": "file reading"}
        )
        
        if result["success"]:
            content = result["result"][:200] + "..." if len(str(result["result"])) > 200 else result["result"]
            print(f"✅ Read file successfully: {content}")
        elif result.get("requires_approval"):
            print(f"⏳ File read requires approval (ID: {result['approval_id']})")
        else:
            print(f"❌ File read failed: {result.get('error', 'Unknown error')}")
    
    except Exception as e:
        print(f"❌ Tool call example failed: {e}")
    
    # Example 2: Calculator (if available)
    try:
        result = await mcp.call_tool(
            "add",
            {"a": 10, "b": 5},
            context={"example": "calculator"}
        )
        
        if result["success"]:
            print(f"✅ Calculator result: {result['result']}")
        else:
            print(f"❌ Calculator failed: {result.get('error', 'Tool not available')}")
    
    except Exception as e:
        print(f"❌ Calculator example failed: {e}")
    
    print()


async def example_resource_access(mcp: MCPIntegration):
    """Demonstrate resource access."""
    print("📖 Example Resource Access:")
    print("-" * 25)
    
    # Example resource access
    try:
        result = await mcp.get_resource(
            "file://README.md",
            context={"example": "resource access"}
        )
        
        if result["success"]:
            print("✅ Resource access successful")
        elif result.get("requires_approval"):
            print(f"⏳ Resource access requires approval (ID: {result['approval_id']})")
        else:
            print(f"❌ Resource access failed: {result.get('error', 'Resource not available')}")
    
    except Exception as e:
        print(f"❌ Resource access example failed: {e}")
    
    print()


async def show_security_status(mcp: MCPIntegration):
    """Show security and audit information."""
    print("🔒 Security Status:")
    print("-" * 18)
    
    # Get pending approvals
    approvals = mcp.get_pending_approvals()
    print(f"   Pending approvals: {len(approvals)}")
    
    if approvals:
        for approval in approvals[:3]:  # Show first 3
            print(f"   - {approval['operation_type']} on {approval['server_name']}")
    
    # Get recent audit log
    audit_log = mcp.get_audit_log(limit=5)
    print(f"   Recent audit entries: {len(audit_log)}")
    
    if audit_log:
        for entry in audit_log:
            timestamp = entry['timestamp'][:19]  # Remove microseconds
            print(f"   - [{timestamp}] {entry['operation_type']} -> {entry['result']}")
    
    print()


def show_configuration_example():
    """Show an example configuration."""
    print("⚙️  Example Configuration (config/system.yaml):")
    print("-" * 45)
    
    config_example = '''
mcp:
  enabled: true
  servers:
    - name: "example-calculator"
      description: "Simple calculator tools"
      command: ["python", "-m", "example_calculator_server"]
      env: {}
      permissions:
        execute: true
      enabled: true
    
    - name: "file-operations"
      description: "File system operations"
      command: ["python", "-m", "mcp_file_server"]
      env: {}
      permissions:
        read: true
        write: false  # Requires approval
      enabled: true

  security:
    audit_file: "data/logs/mcp_audit.log"
    rate_limits:
      calls_per_minute: 60
      calls_per_hour: 1000
    rules:
      - name: "allow-safe-operations"
        operation_type: "tool_call"
        tool_pattern: "add|subtract|multiply|divide|read.*"
        permission: "allowed"
      - name: "require-approval-dangerous"
        operation_type: "tool_call"
        tool_pattern: "delete.*|format.*"
        permission: "require_approval"
'''
    
    print(config_example)


if __name__ == "__main__":
    # Show configuration example first
    show_configuration_example()
    
    # Run the main example
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️  Example interrupted by user")
    except Exception as e:
        print(f"💥 Example failed: {e}")
        sys.exit(1)