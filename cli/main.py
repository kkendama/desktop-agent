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
from core.llm.continuation import ContinuationManager
from core.mcp import MCPIntegration
from core.tool_executor import ToolExecutor
from core.code_executor import CodeExecutor
from core.mcp.manager import MCPServerManager


class DesktopAgentCLI:
    """Main CLI application for Desktop Agent."""
    
    def __init__(self):
        self.console = Console()
        self.config_manager = ConfigManager()
        self.llm_manager = LLMManager()
        self.continuation_manager = None  # Will be initialized after LLM manager
        self.mcp_integration = MCPIntegration()
        self.mcp_manager = MCPServerManager()
        self.tool_executor = ToolExecutor(self.mcp_manager)
        self.code_executor = None  # Will be initialized after config is loaded
        self.conversation_history = []
        self.running = False
        self.streaming_enabled = True  # Enable streaming by default
    
    async def initialize(self) -> bool:
        """Initialize the CLI application."""
        try:
            # Validate configurations
            if not self.config_manager.validate_configs():
                self.console.print("[red]Configuration validation failed![/red]")
                return False
            
            # Initialize LLM manager
            await self.llm_manager.initialize()
            
            # Initialize continuation manager
            self.continuation_manager = ContinuationManager(self.llm_manager)
            
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
            
            # Initialize Code Executor with sandbox configuration
            sandbox_config = self.config_manager.get_sandbox_config()
            self.code_executor = CodeExecutor(sandbox_config)
            self.console.print("[green]Code executor initialized successfully.[/green]")
            
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
- `/stream` - Toggle streaming mode on/off
- Any other input will be sent to the AI agent

**Tips:**
- Use natural language to interact with the agent
- The agent can help with code execution, web search, file operations, and more
- MCP servers provide extended functionality through tools and resources
- Type your questions or requests and press Enter
- Streaming mode provides real-time response updates
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
**Streaming Mode:** {'🟢 Enabled' if self.streaming_enabled else '🔴 Disabled'}
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
    
    async def handle_user_input(self, user_input: str, use_streaming: bool = True):
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
        
        if use_streaming:
            await self._handle_streaming_response(messages)
        else:
            await self._handle_non_streaming_response(messages)
    
    async def _handle_streaming_response(self, messages):
        """Handle streaming response generation with tool execution loop."""
        max_tool_iterations = 5  # Prevent infinite loops
        iteration = 0
        
        while iteration < max_tool_iterations:
            # Generate streaming response
            status_text = "[bold green]Thinking..." if iteration == 0 else f"[bold green]Processing tools (iteration {iteration})..."
            
            try:
                # Show initial status
                self.console.print(f"\n{status_text}")
                
                # Create a panel for streaming output
                accumulated_content = ""
                response_panel = Panel(
                    "",
                    title="🤖 Desktop Agent",
                    border_style="blue"
                )
                
                # Stream the response
                with Live(response_panel, console=self.console, refresh_per_second=10) as live:
                    async for chunk in self.llm_manager.generate_stream(messages):
                        if chunk.content:
                            accumulated_content += chunk.content
                            
                            # Check for completed code blocks and execute them
                            if self.code_executor and "</code>" in accumulated_content:
                                modified_content, code_executed = await self.code_executor.extract_and_execute_completed_code_async(accumulated_content)
                                if code_executed:
                                    accumulated_content = modified_content
                            
                            # Update the live panel
                            updated_panel = Panel(
                                Markdown(accumulated_content),
                                title="🤖 Desktop Agent",
                                border_style="blue"
                            )
                            live.update(updated_panel)
                        
                        # Check if this is the final chunk
                        if chunk.finished:
                            # Display usage info if available
                            if chunk.usage:
                                live.stop()
                                self._display_usage_info(chunk.usage)
                            break
                
                # Check for code execution continuation after streaming ends
                if self.code_executor and "</code_output>" in accumulated_content:
                    # Check if we should continue generation after code execution
                    continuation_result = await self._handle_code_continuation(messages, accumulated_content)
                    if continuation_result:
                        accumulated_content = continuation_result
                
                # Process only tool calls (not code execution, as that's handled during streaming)
                if self.tool_executor.has_tool_calls(accumulated_content):
                    # Execute tools and get results
                    tool_results, cleaned_content = await self.tool_executor.execute_tools_in_text(accumulated_content)
                    
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
                    assistant_message = LLMMessage(role="assistant", content=accumulated_content)
                    self.conversation_history.append(assistant_message)
                    
                    # Exit loop
                    break
            
            except asyncio.CancelledError:
                # Handle cancellation gracefully
                self.console.print("\n[yellow]Streaming cancelled by user.[/yellow]")
                break
            except Exception as e:
                # Log the detailed error for debugging
                import traceback
                error_details = traceback.format_exc()
                
                error_panel = Panel(
                    f"[red]Error generating streaming response: {str(e)}[/red]\n[dim]Use `/stream` to toggle to non-streaming mode if this persists.[/dim]",
                    title="❌ Streaming Error",
                    border_style="red"
                )
                self.console.print(error_panel)
                
                # Optionally print debug info
                self.console.print(f"[dim]Debug info: {error_details[:300]}...[/dim]")
                
                # Try to fallback to non-streaming for this response
                try:
                    self.console.print("[yellow]Attempting fallback to non-streaming mode...[/yellow]")
                    await self._handle_non_streaming_response(messages)
                    break
                except Exception as fallback_error:
                    self.console.print(f"[red]Fallback also failed: {fallback_error}[/red]")
                    break
        
        # Check if we hit max iterations
        if iteration >= max_tool_iterations:
            warning_panel = Panel(
                f"[yellow]Tool execution reached maximum iterations ({max_tool_iterations}). Stopping to prevent infinite loops.[/yellow]",
                title="⚠️ Warning",
                border_style="yellow"
            )
            self.console.print(warning_panel)
    
    async def _handle_non_streaming_response(self, messages):
        """Handle non-streaming response generation (fallback mode)."""
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
                    
                    # Process tools and code execution
                    processed_content, has_executable_content = await self._process_executable_content(response.content, iteration)
                    
                    if has_executable_content:
                        # Continue loop for next iteration
                        messages.extend(processed_content)
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
    
    async def _process_executable_content(self, content: str, iteration: int):
        """
        Process both tool calls and code blocks in the content.
        
        Returns:
            Tuple of (processed_messages, has_executable_content)
        """
        processed_messages = []
        has_executable_content = False
        
        # First, process code blocks
        if self.code_executor and self.code_executor.has_code_blocks(content):
            self.console.print(f"[dim]DEBUG - Found code blocks in iteration {iteration}[/dim]")
            
            # Execute code blocks and get results with modified content
            code_results, content_after_code = await self.code_executor.execute_code_blocks_in_text(content)
            content = content_after_code  # Update content with execution results
            
            # We consider code execution as executable content but don't add separate messages
            # The results are already integrated into the content
            has_executable_content = True
        
        # Then, process tool calls
        if self.tool_executor.has_tool_calls(content):
            self.console.print(f"[dim]DEBUG - Found tool calls in iteration {iteration}[/dim]")
            
            # Execute tools and get results
            tool_results, cleaned_content = await self.tool_executor.execute_tools_in_text(content)
            
            # Add assistant message with cleaned content (without tool_use tags)
            if cleaned_content.strip():
                assistant_message = LLMMessage(role="assistant", content=cleaned_content)
                self.conversation_history.append(assistant_message)
                processed_messages.append(assistant_message)
            
            # Add tool results to conversation history and messages
            for tool_result in tool_results:
                function_message = LLMMessage(
                    role="tool",
                    content=tool_result.content if tool_result.success else f"Error: {tool_result.error}",
                    name=tool_result.name
                )
                self.conversation_history.append(function_message)
                processed_messages.append(function_message)
            
            has_executable_content = True
        elif has_executable_content:
            # Only code blocks were executed, add the modified content as assistant message
            assistant_message = LLMMessage(role="assistant", content=content)
            self.conversation_history.append(assistant_message)
            processed_messages.append(assistant_message)
        
        return processed_messages, has_executable_content
    
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
                    await self.handle_user_input(user_input, use_streaming=self.streaming_enabled)
                
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
        
        elif command == '/stream':
            self.streaming_enabled = not self.streaming_enabled
            status = "enabled" if self.streaming_enabled else "disabled"
            self.console.print(f"[green]Streaming mode {status}.[/green]")
        
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
    
    async def _handle_code_continuation(self, messages, content_with_code_output):
        """
        Handle continuation generation after code execution.
        
        Args:
            messages: Current conversation messages
            content_with_code_output: Assistant content including <code_output>
            
        Returns:
            Extended content with continuation, or None if no continuation needed
        """
        try:
            # Check if continuation is supported
            if not self.continuation_manager or not self.continuation_manager.supports_continuation():
                return None
            
            # Extract code and output for continuation
            import re
            
            # Find the last code block and its output
            code_pattern = r'<code>\s*```python\s*(.*?)\s*```\s*</code>'
            output_pattern = r'<code_output>\s*(.*?)\s*</code_output>'
            
            code_matches = list(re.finditer(code_pattern, content_with_code_output, re.DOTALL))
            output_matches = list(re.finditer(output_pattern, content_with_code_output, re.DOTALL))
            
            if not code_matches or not output_matches:
                return None
            
            # Get the last code and output
            last_code = code_matches[-1].group(1).strip()
            last_output = output_matches[-1].group(1).strip()
            
            # Check if the content contains </code_output> (indicating code was executed)
            if '</code_output>' not in content_with_code_output:
                return None
            
            # Show subtle continuation status
            self.console.print("[dim]...[/dim]", end="")
            
            # Generate continuation
            continuation_response = await self.continuation_manager.continue_with_code_result(
                conversation_messages=messages,
                partial_assistant_response=content_with_code_output,
                code=last_code,
                code_output=last_output,
                max_continuation_tokens=300,  # Limit continuation length
                stream=False
            )
            
            # Display the continuation
            if continuation_response and continuation_response.content != content_with_code_output:
                # Extract only the new content (after the original)
                if continuation_response.content.startswith(content_with_code_output):
                    new_content = continuation_response.content[len(content_with_code_output):]
                    if new_content.strip():
                        # Clean up the new content formatting
                        cleaned_new_content = self._clean_continuation_content(new_content)
                        
                        if cleaned_new_content:
                            # Display the continuation seamlessly (without showing it's a continuation)
                            self.console.print(Markdown(cleaned_new_content))
                            
                            # Display usage info if available
                            if continuation_response.usage:
                                self._display_usage_info(continuation_response.usage)
                        
                        return continuation_response.content
            
            return None
            
        except Exception as e:
            self.console.print(f"[yellow]Warning: Code continuation failed: {e}[/yellow]")
            return None
    
    def _clean_continuation_content(self, content: str) -> str:
        """
        Clean up continuation content for better display.
        
        Args:
            content: Raw continuation content
            
        Returns:
            Cleaned content for display
        """
        # Remove leading/trailing whitespace
        content = content.strip()
        
        # Remove redundant "Code Execution Output:" sections since we already showed the output
        import re
        
        # Remove patterns like "**Code Execution Output:**\n```\noutput\n```\n"
        content = re.sub(r'\*\*Code Execution Output:\*\*\s*\n```[^`]*?```\s*\n?', '', content)
        
        # Remove patterns like "Code Execution Output:\noutput"
        content = re.sub(r'Code Execution Output:\s*\n[^\n]*\n?', '', content)
        
        # Remove any remaining **Code Execution Output:** patterns
        content = re.sub(r'\*\*Code Execution Output:\*\*[^\n]*\n?', '', content)
        
        # Remove excessive newlines
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        # Clean up the start of the content
        content = content.lstrip('\n')
        
        # If content starts with just a summary or answer, make it more natural
        if content and not content.startswith(('**', '#', '-', '*')):
            # Add a small separator for natural flow
            content = '\n' + content
        
        return content.strip()


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