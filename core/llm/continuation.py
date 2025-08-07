"""
LLM Continuation Manager for handling tool/code execution result integration.
"""

from typing import List, Dict, Any, Optional, AsyncGenerator
from .base import LLMMessage, LLMResponse
from .manager import LLMManager


class ContinuationManager:
    """
    Manager for handling LLM response continuation after tool/code execution.
    This allows the assistant to continue its response after incorporating execution results.
    """
    
    def __init__(self, llm_manager: LLMManager):
        self.llm_manager = llm_manager
    
    async def continue_with_tool_result(
        self,
        conversation_messages: List[LLMMessage],
        partial_assistant_response: str,
        tool_name: str,
        tool_result: str,
        max_continuation_tokens: Optional[int] = None,
        stream: bool = False
    ) -> LLMResponse:
        """
        Continue assistant response after tool execution.
        
        Args:
            conversation_messages: Previous conversation messages
            partial_assistant_response: Assistant's response before tool execution
            tool_name: Name of the executed tool
            tool_result: Result from tool execution
            max_continuation_tokens: Maximum tokens for continuation
            stream: Whether to stream the continuation
            
        Returns:
            Continued LLM response
        """
        # Format tool result for inclusion
        tool_result_formatted = self._format_tool_result(tool_name, tool_result)
        
        # Create the continuation prompt
        continuation_content = partial_assistant_response + tool_result_formatted
        
        return await self._continue_generation(
            conversation_messages,
            continuation_content,
            max_continuation_tokens,
            stream
        )
    
    async def continue_with_code_result(
        self,
        conversation_messages: List[LLMMessage],
        partial_assistant_response: str,
        code: str,
        code_output: str,
        max_continuation_tokens: Optional[int] = None,
        stream: bool = False
    ) -> LLMResponse:
        """
        Continue assistant response after code execution.
        
        Args:
            conversation_messages: Previous conversation messages
            partial_assistant_response: Assistant's response before code execution
            code: The executed code
            code_output: Output from code execution
            max_continuation_tokens: Maximum tokens for continuation
            stream: Whether to stream the continuation
            
        Returns:
            Continued LLM response
        """
        # Format code result for inclusion
        code_result_formatted = self._format_code_result(code, code_output)
        
        # Create the continuation prompt
        continuation_content = partial_assistant_response + code_result_formatted
        
        return await self._continue_generation(
            conversation_messages,
            continuation_content,
            max_continuation_tokens,
            stream
        )
    
    async def continue_with_custom_content(
        self,
        conversation_messages: List[LLMMessage],
        partial_assistant_response: str,
        additional_content: str,
        max_continuation_tokens: Optional[int] = None,
        stream: bool = False
    ) -> LLMResponse:
        """
        Continue assistant response with custom content.
        
        Args:
            conversation_messages: Previous conversation messages
            partial_assistant_response: Assistant's response so far
            additional_content: Additional content to include
            max_continuation_tokens: Maximum tokens for continuation
            stream: Whether to stream the continuation
            
        Returns:
            Continued LLM response
        """
        continuation_content = partial_assistant_response + additional_content
        
        return await self._continue_generation(
            conversation_messages,
            continuation_content,
            max_continuation_tokens,
            stream
        )
    
    async def _continue_generation(
        self,
        conversation_messages: List[LLMMessage],
        continuation_content: str,
        max_continuation_tokens: Optional[int],
        stream: bool
    ) -> LLMResponse:
        """Internal method to handle continuation generation."""
        
        # Format the conversation for completion continuation
        completion_prompt = self.llm_manager.format_for_completion_continuation(
            conversation_messages,
            continuation_content
        )
        
        # Get template-specific stop tokens for completion mode
        stop_tokens = self.llm_manager.get_template_stop_tokens(completion_mode=True)
        
        # Generate continuation using completion API
        if stream:
            return await self._stream_continuation(
                completion_prompt,
                stop_tokens,
                max_continuation_tokens
            )
        else:
            response = await self.llm_manager.completion(
                prompt=completion_prompt,
                max_tokens=max_continuation_tokens,
                stop=stop_tokens,
                stream=False
            )
            
            # Combine original content with continuation
            full_content = continuation_content + response.content
            
            return LLMResponse(
                content=full_content,
                usage=response.usage,
                metadata=response.metadata,
                finished=response.finished
            )
    
    async def _stream_continuation(
        self,
        completion_prompt: str,
        stop_tokens: List[str],
        max_continuation_tokens: Optional[int]
    ) -> AsyncGenerator[LLMResponse, None]:
        """Stream continuation generation."""
        async for chunk in self.llm_manager.completion_stream(
            prompt=completion_prompt,
            max_tokens=max_continuation_tokens,
            stop=stop_tokens
        ):
            yield chunk
    
    def _format_tool_result(self, tool_name: str, tool_result: str) -> str:
        """Format tool execution result for continuation."""
        return f"\n\n**Tool Execution Result ({tool_name}):**\n{tool_result}\n\n"
    
    def _format_code_result(self, code: str, code_output: str) -> str:
        """Format code execution result for continuation."""
        return f"\n\n**Code Execution Output:**\n```\n{code_output}\n```\n\n"
    
    def supports_continuation(self) -> bool:
        """Check if the current template supports continuation."""
        template_info = self.llm_manager.get_template_info()
        return template_info.get("supports_completion", False)
    
    def get_continuation_settings(self) -> Dict[str, Any]:
        """Get settings for continuation mode."""
        template_info = self.llm_manager.get_template_info()
        return {
            "template_name": template_info.get("name"),
            "supports_continuation": template_info.get("supports_completion", False),
            "stop_tokens": self.llm_manager.get_template_stop_tokens(completion_mode=True),
            "model_family": template_info.get("model_family"),
        }


class ConversationState:
    """
    Helper class to track conversation state for continuation.
    """
    
    def __init__(self):
        self.messages: List[LLMMessage] = []
        self.current_assistant_response: str = ""
        self.pending_tool_results: List[Dict[str, Any]] = []
        self.pending_code_results: List[Dict[str, Any]] = []
    
    def add_message(self, message: LLMMessage) -> None:
        """Add a message to the conversation."""
        self.messages.append(message)
    
    def start_assistant_response(self, content: str = "") -> None:
        """Start tracking an assistant response."""
        self.current_assistant_response = content
    
    def append_to_assistant_response(self, content: str) -> None:
        """Append content to the current assistant response."""
        self.current_assistant_response += content
    
    def add_tool_result(self, tool_name: str, result: str) -> None:
        """Add a tool execution result."""
        self.pending_tool_results.append({
            "tool_name": tool_name,
            "result": result
        })
    
    def add_code_result(self, code: str, output: str) -> None:
        """Add a code execution result."""
        self.pending_code_results.append({
            "code": code,
            "output": output
        })
    
    def finalize_assistant_response(self) -> LLMMessage:
        """Finalize the current assistant response and add it to messages."""
        message = LLMMessage(
            role="assistant",
            content=self.current_assistant_response
        )
        self.messages.append(message)
        self.current_assistant_response = ""
        self.pending_tool_results.clear()
        self.pending_code_results.clear()
        return message
    
    def get_conversation_copy(self) -> List[LLMMessage]:
        """Get a copy of the conversation messages."""
        return self.messages.copy()
    
    def has_pending_results(self) -> bool:
        """Check if there are pending tool or code results."""
        return bool(self.pending_tool_results or self.pending_code_results)