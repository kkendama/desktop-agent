"""
Main CLI interface for Desktop Agent.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt
from rich.markdown import Markdown
from rich.live import Live
from rich.spinner import Spinner

# Add parent directory to path to import core modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import ConfigManager
from core.llm.manager import LLMManager
from core.llm.base import LLMMessage
from core.mcp import MCPIntegration
from core.tool_executor import ToolExecutor
from core.mcp.manager import MCPServerManager


class DesktopAgentCLI:
    """Main CLI application for Desktop Agent."""
    
    def __init__(self):
        self.console = Console()
        self.config_manager = ConfigManager()
        self.llm_manager = LLMManager()
        self.mcp_integration = MCPIntegration()
        self.mcp_manager = MCPServerManager()
        self.tool_executor = ToolExecutor(self.mcp_manager)
        self.conversation_history = []
        self.running = False
    
    async def initialize(self) -> bool:
        """Initialize the CLI application."""
        try:
            # Validate configurations
            if not self.config_manager.validate_configs():
                self.console.print("[red]Configuration validation failed![/red]")
                return False
            
            # Initialize LLM manager
            await self.llm_manager.initialize()
            
            # Test LLM connection
            if not await self.llm_manager.health_check():
                self.console.print("[red]LLM health check failed![/red]")
                return False
            
            # Initialize MCP integration
            if await self.mcp_integration.initialize():
                self.console.print("[green]MCP integration initialized successfully.[/green]")
            else:
                self.console.print("[yellow]MCP integration failed to initialize (continuing without MCP).[/yellow]")
            
            # Initialize MCP server manager
            if await self.mcp_manager.initialize():
                self.console.print("[green]MCP servers initialized successfully.[/green]")
                await self.mcp_manager.start_all_servers()
            else:
                self.console.print("[yellow]MCP server manager failed to initialize (continuing without MCP servers).[/yellow]")
            
            return True
            
        except Exception as e:
            self.console.print(f"[red]Initialization failed: {e}[/red]")
            return False
    
    def display_welcome(self):
        """Display welcome message."""
        welcome_text = self.config_manager.get_user_greeting()
        
        # Get provider info
        provider_info = self.llm_manager.get_provider_info()
        
        welcome_panel = Panel(
            welcome_text,
            title="🤖 Desktop Agent",
            subtitle=f"Provider: {provider_info.get('provider', 'unknown')} | Model: {provider_info.get('model', 'unknown')}",
            border_style="blue"
        )
        
        self.console.print(welcome_panel)
        self.console.print()
    
    def display_help(self):
        """Display help information."""
        help_text = """
**Available Commands:**
- `/help` - Show this help message
- `/quit` or `/exit` - Exit the application
- `/clear` - Clear conversation history
- `/status` - Show system status
- `/reload` - Reload configuration
- `/mcp` - Show MCP status and management
- `/tools` - List available MCP tools
- `/approvals` - Show pending approval requests
- Any other input will be sent to the AI agent

**Tips:**
- Use natural language to interact with the agent
- The agent can help with code execution, web search, file operations, and more
- MCP servers provide extended functionality through tools and resources
- Type your questions or requests and press Enter
        """
        
        help_panel = Panel(
            Markdown(help_text),
            title="📖 Help",
            border_style="green"
        )
        
        self.console.print(help_panel)
    
    async def display_status(self):
        """Display system status."""
        # Get LLM status
        llm_healthy = await self.llm_manager.health_check()
        provider_info = self.llm_manager.get_provider_info()
        
        # Get MCP status
        mcp_status = self.mcp_integration.get_status()
        
        status_text = f"""
**LLM Status:** {'🟢 Healthy' if llm_healthy else '🔴 Unhealthy'}
**Provider:** {provider_info.get('provider', 'Unknown')}
**Model:** {provider_info.get('model', 'Unknown')}
**Endpoint:** {provider_info.get('endpoint', 'Unknown')}
**Conversation Messages:** {len(self.conversation_history)}
**Available Providers:** {', '.join(self.llm_manager.list_available_providers())}

**MCP Status:** {'🟢 Initialized' if mcp_status.get('status') == 'initialized' else '🔴 Not Initialized'}
**MCP Tools:** {mcp_status.get('tools', 0)}
**MCP Resources:** {mcp_status.get('resources', 0)}
**MCP Servers:** {len(mcp_status.get('servers', {}))} configured
        """
        
        status_panel = Panel(
            Markdown(status_text),
            title="📊 System Status",
            border_style="yellow"
        )
        
        self.console.print(status_panel)
    
    async def handle_user_input(self, user_input: str):
        """Handle user input and generate response."""
        # Add user message to history
        user_message = LLMMessage(role="user", content=user_input)
        self.conversation_history.append(user_message)
        
        # Prepare messages for LLM
        messages = []
        
        # Add system message
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        workspace_path = Path.cwd()
        
        system_prompt = self.config_manager.get_system_prompt(
            current_datetime=current_time,
            workspace_path=str(workspace_path)
        )
        
        messages.append(LLMMessage(role="system", content=system_prompt))
        
        # Add conversation history (limit to last N messages)
        max_history = self.config_manager.get_cli_config().get("max_history", 20)
        recent_history = self.conversation_history[-max_history:]
        messages.extend(recent_history)
        
        # Generate response with tool execution loop
        max_tool_iterations = 5  # Prevent infinite loops
        iteration = 0
        
        while iteration < max_tool_iterations:
            # Generate response with loading indicator
            status_text = "[bold green]Thinking..." if iteration == 0 else f"[bold green]Processing tools (iteration {iteration})..."
            
            with self.console.status(status_text, spinner="dots"):
                try:
                    response = await self.llm_manager.generate(messages)
                    
                    # Debug: Print what LLM generated
                    self.console.print(f"[dim]DEBUG - Iteration {iteration}: LLM Response:[/dim]")
                    self.console.print(f"[dim]{response.content[:200]}...[/dim]")
                    
                    # Check if response contains tool calls
                    if self.tool_executor.has_tool_calls(response.content):
                        self.console.print(f"[dim]DEBUG - Found tool calls in iteration {iteration}[/dim]")
                        
                        # Execute tools and get results
                        tool_results, cleaned_content = await self.tool_executor.execute_tools_in_text(response.content)
                        
                        # Add assistant message with cleaned content (without tool_use tags)
                        if cleaned_content.strip():
                            assistant_message = LLMMessage(role="assistant", content=cleaned_content)
                            self.conversation_history.append(assistant_message)
                            messages.append(assistant_message)
                        
                        # Add tool results to conversation history and messages
                        for tool_result in tool_results:
                            function_message = LLMMessage(
                                role="tool",
                                content=tool_result.content if tool_result.success else f"Error: {tool_result.error}",
                                name=tool_result.name
                            )
                            self.conversation_history.append(function_message)
                            messages.append(function_message)
                            

                        
                        # Continue loop for next iteration
                        iteration += 1
                        continue
                    else:
                        # No tool calls, this is the final response
                        assistant_message = LLMMessage(role="assistant", content=response.content)
                        self.conversation_history.append(assistant_message)
                        
                        # Display final response
                        response_panel = Panel(
                            Markdown(response.content),
                            title="🤖 Desktop Agent",
                            border_style="blue"
                        )
                        self.console.print(response_panel)
                        
                        # Display usage info if available
                        if response.usage:
                            self._display_usage_info(response.usage)
                        
                        # Exit loop
                        break
                
                except Exception as e:
                    error_panel = Panel(
                        f"[red]Error generating response: {e}[/red]",
                        title="❌ Error",
                        border_style="red"
                    )
                    self.console.print(error_panel)
                    break  # Exit loop on error
        
        # Check if we hit max iterations
        if iteration >= max_tool_iterations:
            warning_panel = Panel(
                f"[yellow]Tool execution reached maximum iterations ({max_tool_iterations}). Stopping to prevent infinite loops.[/yellow]",
                title="⚠️ Warning",
                border_style="yellow"
            )
            self.console.print(warning_panel)
    
    def _display_usage_info(self, usage: dict):
        """Display usage information."""
        usage_text = Text()
        usage_text.append("Usage: ", style="dim")
        
        if "total_tokens" in usage:
            usage_text.append(f"Tokens: {usage['total_tokens']} ", style="dim cyan")
        elif "eval_count" in usage:
            usage_text.append(f"Tokens: {usage['eval_count']} ", style="dim cyan")
        
        if "total_duration" in usage:
            duration_ms = usage["total_duration"] / 1_000_000  # Convert to ms
            usage_text.append(f"Time: {duration_ms:.1f}ms", style="dim cyan")
        
        self.console.print(usage_text)
    
    async def run(self):
        """Main CLI loop."""
        # Initialize
        if not await self.initialize():
            return
        
        # Display welcome
        self.display_welcome()
        
        self.running = True
        cli_config = self.config_manager.get_cli_config()
        prompt_text = cli_config.get("prompt", "Desktop Agent> ")
        
        while self.running:
            try:
                # Get user input
                user_input = Prompt.ask(prompt_text).strip()
                
                if not user_input:
                    continue
                
                # Handle commands
                if user_input.startswith('/'):
                    await self.handle_command(user_input)
                else:
                    # Handle normal conversation
                    await self.handle_user_input(user_input)
                
                self.console.print()  # Add spacing
                
            except KeyboardInterrupt:
                self.console.print("\n[yellow]Use /quit to exit gracefully.[/yellow]")
            except EOFError:
                break
        
        # Cleanup
        await self.llm_manager.close_engine()
        await self.mcp_integration.shutdown()
        self.console.print("[green]Goodbye! 👋[/green]")
    
    async def handle_command(self, command: str):
        """Handle CLI commands."""
        command = command.lower().strip()
        
        if command in ['/quit', '/exit']:
            self.running = False
        
        elif command == '/help':
            self.display_help()
        
        elif command == '/clear':
            self.conversation_history.clear()
            self.console.print("[green]Conversation history cleared.[/green]")
        
        elif command == '/status':
            await self.display_status()
        
        elif command == '/reload':
            try:
                self.config_manager.reload_configs()
                await self.llm_manager.reload_config()
                await self.mcp_integration.reload_configuration()
                self.console.print("[green]Configuration reloaded successfully.[/green]")
            except Exception as e:
                self.console.print(f"[red]Failed to reload configuration: {e}[/red]")
        
        elif command == '/mcp':
            await self.display_mcp_status()
        
        elif command == '/tools':
            await self.display_mcp_tools()
        
        elif command == '/approvals':
            await self.display_pending_approvals()
        
        else:
            self.console.print(f"[yellow]Unknown command: {command}[/yellow]")
            self.console.print("[dim]Type /help for available commands.[/dim]")
    
    async def display_mcp_status(self):
        """Display detailed MCP status."""
        mcp_status = self.mcp_integration.get_status()
        
        if mcp_status.get('status') == 'not_initialized':
            self.console.print("[red]MCP is not initialized.[/red]")
            return
        
        # Server status
        servers = mcp_status.get('servers', {})
        server_info = []
        for server_name, info in servers.items():
            status_emoji = "🟢" if info.get('status') == 'running' else "🔴"
            server_info.append(f"- {status_emoji} **{server_name}**: {info.get('status', 'unknown')} ({info.get('tools', 0)} tools, {info.get('resources', 0)} resources)")
        
        # Security status
        security = mcp_status.get('security', {})
        
        status_text = f"""
**MCP Status:** {'🟢 Active' if mcp_status.get('status') == 'initialized' else '🔴 Inactive'}
**Total Tools:** {mcp_status.get('tools', 0)}
**Total Resources:** {mcp_status.get('resources', 0)}

**Servers:**
{chr(10).join(server_info) if server_info else "No servers configured"}

**Security:**
- **Pending Approvals:** {security.get('pending_approvals', 0)}
- **Security Rules:** {security.get('rules_count', 0)}
- **Blocked Entities:** {security.get('blocked_servers', 0)} servers, {security.get('blocked_tools', 0)} tools
        """
        
        mcp_panel = Panel(
            Markdown(status_text),
            title="🔧 MCP Status",
            border_style="cyan"
        )
        
        self.console.print(mcp_panel)
    
    async def display_mcp_tools(self):
        """Display available MCP tools."""
        tools = self.mcp_integration.list_tools()
        
        if not tools:
            self.console.print("[yellow]No MCP tools available.[/yellow]")
            return
        
        tool_info = []
        for tool in tools:
            tool_info.append(f"- **{tool['name']}** (from {tool['server']}): {tool.get('description', 'No description')}")
        
        tools_text = f"""
**Available Tools ({len(tools)} total):**

{chr(10).join(tool_info)}

**Usage:** Include tool usage requests in your natural language input to the agent.
        """
        
        tools_panel = Panel(
            Markdown(tools_text),
            title="🛠️ MCP Tools",
            border_style="green"
        )
        
        self.console.print(tools_panel)
    
    async def display_pending_approvals(self):
        """Display pending approval requests."""
        approvals = self.mcp_integration.get_pending_approvals()
        
        if not approvals:
            self.console.print("[green]No pending approval requests.[/green]")
            return
        
        approval_info = []
        for approval in approvals:
            timestamp = approval['timestamp']
            operation = approval['operation_type']
            server = approval['server_name']
            tool = approval.get('tool_name', 'N/A')
            
            approval_info.append(f"- **ID**: {approval['id'][:8]}... | **Operation**: {operation} | **Server**: {server} | **Tool**: {tool} | **Time**: {timestamp}")
        
        approvals_text = f"""
**Pending Approvals ({len(approvals)} total):**

{chr(10).join(approval_info)}

**Note:** Approvals are currently handled automatically based on security rules.
Future versions will support manual approval workflows.
        """
        
        approvals_panel = Panel(
            Markdown(approvals_text),
            title="⏳ Pending Approvals",
            border_style="orange"
        )
        
        self.console.print(approvals_panel)


@click.command()
@click.option('--config-dir', default='config', help='Configuration directory path')
@click.option('--debug', is_flag=True, help='Enable debug mode')
def main(config_dir: str, debug: bool):
    """Desktop Agent CLI - Your AI assistant for desktop tasks."""
    
    if debug:
        import logging
        logging.basicConfig(level=logging.DEBUG)
    
    # Create CLI instance
    cli = DesktopAgentCLI()
    cli.config_manager = ConfigManager(config_dir)
    
    # Run the CLI
    try:
        asyncio.run(cli.run())
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()