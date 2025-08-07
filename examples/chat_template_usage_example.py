#!/usr/bin/env python3
"""
Example usage of Chat Template and Continuation functionality.
This demonstrates how to use the new features for tool/code result integration.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.llm.manager import LLMManager
from core.llm.continuation import ContinuationManager, ConversationState
from core.llm.base import LLMMessage


async def example_tool_integration():
    """Example: Integrating tool execution results."""
    print("=== Example: Tool Integration ===")
    
    # Initialize
    llm_manager = LLMManager()
    await llm_manager.initialize()
    
    continuation_manager = ContinuationManager(llm_manager)
    state = ConversationState()
    
    # Setup conversation
    state.add_message(LLMMessage(role="system", content="You are a helpful assistant."))
    state.add_message(LLMMessage(role="user", content="What's the current time in Tokyo?"))
    
    # Assistant starts responding
    state.start_assistant_response("I'll check the current time in Tokyo for you.")
    
    # Simulate tool execution
    tool_result = "2024-01-15 14:30:00 JST"
    
    # Continue generation with tool result
    try:
        continued_response = await continuation_manager.continue_with_tool_result(
            conversation_messages=state.get_conversation_copy(),
            partial_assistant_response=state.current_assistant_response,
            tool_name="get_current_time",
            tool_result=tool_result,
            max_continuation_tokens=200
        )
        
        print(f"Full response: {continued_response.content}")
        
    except Exception as e:
        print(f"⚠️  Tool integration example failed (server may not be running): {e}")
    
    await llm_manager.close_engine()


async def example_code_integration():
    """Example: Integrating code execution results."""
    print("\n=== Example: Code Integration ===")
    
    # Initialize
    llm_manager = LLMManager()
    await llm_manager.initialize()
    
    continuation_manager = ContinuationManager(llm_manager)
    state = ConversationState()
    
    # Setup conversation
    state.add_message(LLMMessage(role="system", content="You are a helpful assistant."))
    state.add_message(LLMMessage(role="user", content="Calculate the factorial of 5"))
    
    # Assistant starts responding
    state.start_assistant_response("I'll calculate the factorial of 5 for you:\n\n```python\nimport math\nresult = math.factorial(5)\nprint(f'5! = {result}')\n```")
    
    # Simulate code execution
    code = "import math\nresult = math.factorial(5)\nprint(f'5! = {result}')"
    code_output = "5! = 120"
    
    # Continue generation with code result
    try:
        continued_response = await continuation_manager.continue_with_code_result(
            conversation_messages=state.get_conversation_copy(),
            partial_assistant_response=state.current_assistant_response,
            code=code,
            code_output=code_output,
            max_continuation_tokens=150
        )
        
        print(f"Full response: {continued_response.content}")
        
    except Exception as e:
        print(f"⚠️  Code integration example failed (server may not be running): {e}")
    
    await llm_manager.close_engine()


async def example_custom_template():
    """Example: Using custom chat templates."""
    print("\n=== Example: Custom Chat Template ===")
    
    # Initialize
    llm_manager = LLMManager()
    await llm_manager.initialize()
    
    # Check current template
    template_info = llm_manager.get_template_info()
    print(f"Current template: {template_info['name']}")
    print(f"Description: {template_info['description']}")
    print(f"Supports completion: {template_info['supports_completion']}")
    
    # Format messages
    messages = [
        LLMMessage(role="system", content="You are a coding assistant."),
        LLMMessage(role="user", content="Write a Python function to reverse a string."),
    ]
    
    formatted = llm_manager.format_chat_messages(messages)
    print(f"\nFormatted conversation:\n{formatted}")
    
    # Get template-specific stop tokens
    stop_tokens = llm_manager.get_template_stop_tokens()
    print(f"\nStop tokens: {stop_tokens}")
    
    await llm_manager.close_engine()


async def example_streaming_continuation():
    """Example: Streaming continuation."""
    print("\n=== Example: Streaming Continuation ===")
    
    # Initialize
    llm_manager = LLMManager()
    await llm_manager.initialize()
    
    continuation_manager = ContinuationManager(llm_manager)
    
    # Setup basic conversation
    messages = [
        LLMMessage(role="system", content="You are a helpful assistant."),
        LLMMessage(role="user", content="Explain machine learning"),
    ]
    
    partial_response = "Machine learning is a subset of artificial intelligence that"
    
    try:
        # Stream continuation
        print("Streaming continuation:")
        async for chunk in continuation_manager._stream_continuation(
            completion_prompt=llm_manager.format_for_completion_continuation(messages, partial_response),
            stop_tokens=llm_manager.get_template_stop_tokens(completion_mode=True),
            max_continuation_tokens=100
        ):
            print(chunk.content, end="", flush=True)
        print()  # New line after streaming
        
    except Exception as e:
        print(f"⚠️  Streaming example failed (server may not be running): {e}")
    
    await llm_manager.close_engine()


async def main():
    """Run all examples."""
    print("🚀 Chat Template and Continuation Usage Examples")
    print("=" * 60)
    
    print("Note: Some examples may fail if the LLM server is not running.")
    print("This is expected and demonstrates the functionality structure.\n")
    
    await example_tool_integration()
    await example_code_integration()
    await example_custom_template()
    await example_streaming_continuation()
    
    print("\n" + "=" * 60)
    print("🎉 All examples completed!")
    print("\nNext steps:")
    print("1. Start your LLM server (vLLM or Ollama)")
    print("2. Run the examples again to see full functionality")
    print("3. Integrate these patterns into your agent implementation")


if __name__ == "__main__":
    asyncio.run(main())