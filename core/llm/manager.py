"""
LLM Manager for handling multiple LLM engines and configurations.
"""

import yaml
import asyncio
from typing import Dict, Any, Optional, List
from pathlib import Path
from .base import BaseLLMEngine, LLMConfig, LLMMessage, LLMResponse, CompletionRequest, LLMEngineFactory
from .ollama_engine import OllamaEngine
from .vllm_engine import VLLMEngine
from .chat_template import ChatTemplateManager


class LLMManager:
    """
    Manager class for LLM engines.
    Handles configuration loading, engine initialization, and message routing.
    """
    
    def __init__(self, config_path: Optional[str] = None, templates_dir: Optional[str] = None):
        self.config_path = config_path or "config/system.yaml"
        self.templates_dir = templates_dir or "config/chat_templates"
        self.engine: Optional[BaseLLMEngine] = None
        self.config: Optional[LLMConfig] = None
        self.chat_template_manager = ChatTemplateManager(self.templates_dir)
        self.current_template: Optional[str] = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the LLM manager and engine."""
        await self.load_config()
        await self.create_engine()
        self._initialized = True
    
    async def load_config(self) -> None:
        """Load configuration from YAML file."""
        config_file = Path(self.config_path)
        
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        with open(config_file, 'r', encoding='utf-8') as f:
            full_config = yaml.safe_load(f)
        
        llm_config = full_config.get("llm", {})
        
        # Create LLMConfig object
        self.config = LLMConfig(
            provider=llm_config.get("provider", "ollama"),
            model=llm_config.get("model", "qwen3:latest"),
            endpoint=llm_config.get("endpoint", "http://localhost:11434"),
            temperature=llm_config.get("temperature", 0.7),
            max_tokens=llm_config.get("max_tokens", 4096),
            timeout=llm_config.get("timeout", 60),
            provider_config=llm_config
        )
        
        # Load chat template configuration
        await self._load_chat_template_config(llm_config)
    
    async def create_engine(self) -> None:
        """Create and initialize the LLM engine."""
        if not self.config:
            raise RuntimeError("Configuration not loaded. Call load_config() first.")
        
        # Close existing engine if any
        if self.engine:
            await self.close_engine()
        
        # Create new engine
        self.engine = LLMEngineFactory.create_engine(self.config)
        await self.engine.initialize()
    
    async def close_engine(self) -> None:
        """Close the current engine."""
        if self.engine and hasattr(self.engine, 'close'):
            await self.engine.close()
        self.engine = None
    
    async def ensure_initialized(self) -> None:
        """Ensure the manager is initialized."""
        if not self._initialized:
            await self.initialize()
    
    async def generate(
        self,
        messages: List[LLMMessage],
        stream: bool = False,
        **kwargs
    ) -> LLMResponse:
        """
        Generate response using the configured LLM engine.
        
        Args:
            messages: List of messages for the conversation
            stream: Whether to stream the response (returns complete response)
            **kwargs: Additional generation parameters
            
        Returns:
            LLM response (non-streaming mode only)
        """
        await self.ensure_initialized()
        
        if not self.engine:
            raise RuntimeError("LLM engine not initialized")
        
        response = await self.engine.generate(messages, stream=False, **kwargs)
        
        if isinstance(response, LLMResponse):
            return response
        else:
            # If it's a generator, collect all responses
            content_parts = []
            async for chunk in response:
                content_parts.append(chunk.content)
            
            return LLMResponse(
                content="".join(content_parts),
                finished=True
            )
    
    async def generate_stream(
        self,
        messages: List[LLMMessage],
        **kwargs
    ):
        """
        Generate streaming response using the configured LLM engine.
        
        Args:
            messages: List of messages for the conversation
            **kwargs: Additional generation parameters
            
        Yields:
            LLMResponse chunks for streaming
        """
        await self.ensure_initialized()
        
        if not self.engine:
            raise RuntimeError("LLM engine not initialized")
        
        try:
            response = await self.engine.generate(messages, stream=True, **kwargs)
            
            if isinstance(response, LLMResponse):
                # Non-streaming response, yield as single chunk
                yield response
            else:
                # Streaming response, yield each chunk
                async for chunk in response:
                    yield chunk
        except Exception as e:
            # Wrap engine-specific errors with context
            raise RuntimeError(f"Streaming generation failed with {self.config.provider}: {str(e)}") from e
    
    async def generate_single(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Convenience method for single prompt generation.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            **kwargs: Additional generation parameters
            
        Returns:
            LLM response
        """
        await self.ensure_initialized()
        
        if not self.engine:
            raise RuntimeError("LLM engine not initialized")
        
        return await self.engine.generate_single(prompt, system_prompt, **kwargs)
    
    async def health_check(self) -> bool:
        """Check if the LLM engine is healthy."""
        await self.ensure_initialized()
        
        if not self.engine:
            return False
        
        return await self.engine.health_check()
    
    def get_provider_info(self) -> Dict[str, Any]:
        """Get information about the current provider and configuration."""
        if not self.config:
            return {}
        
        return {
            "provider": self.config.provider,
            "model": self.config.model,
            "endpoint": self.config.endpoint,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
        }
    
    async def _load_chat_template_config(self, llm_config: Dict[str, Any]) -> None:
        """Load chat template configuration."""
        try:
            # Load all available templates
            self.chat_template_manager.load_templates()
            
            template_config = llm_config.get("chat_template", {})
            template_name = template_config.get("template", "auto")
            auto_detect = template_config.get("auto_detect", True)
            
            # Determine which template to use
            if template_name == "auto" or auto_detect:
                self.current_template = self.chat_template_manager.auto_detect_template(self.config.model)
            else:
                self.current_template = template_name
            
            # Validate template exists
            self.chat_template_manager.get_template(self.current_template)
            
        except Exception as e:
            print(f"Warning: Failed to load chat template configuration: {e}")
            # Fallback to first available template
            available = self.chat_template_manager.list_templates()
            if available:
                self.current_template = available[0]
            else:
                raise RuntimeError("No chat templates available")
    
    async def completion(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        stop: Optional[List[str]] = None,
        stream: bool = False,
        **kwargs
    ) -> LLMResponse:
        """
        Generate completion from a prompt.
        
        Args:
            prompt: The prompt text
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation
            stop: Stop tokens
            stream: Whether to stream the response
            **kwargs: Additional generation parameters
            
        Returns:
            LLM response
        """
        await self.ensure_initialized()
        
        if not self.engine:
            raise RuntimeError("LLM engine not initialized")
        
        request = CompletionRequest(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop,
            stream=stream
        )
        
        response = await self.engine.completion(request, **kwargs)
        
        if isinstance(response, LLMResponse):
            return response
        else:
            # If it's a generator, collect all responses
            content_parts = []
            async for chunk in response:
                content_parts.append(chunk.content)
            
            return LLMResponse(
                content="".join(content_parts),
                finished=True
            )
    
    async def completion_stream(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        stop: Optional[List[str]] = None,
        **kwargs
    ):
        """
        Generate streaming completion from a prompt.
        
        Args:
            prompt: The prompt text
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation
            stop: Stop tokens
            **kwargs: Additional generation parameters
            
        Yields:
            LLMResponse chunks for streaming
        """
        await self.ensure_initialized()
        
        if not self.engine:
            raise RuntimeError("LLM engine not initialized")
        
        request = CompletionRequest(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop,
            stream=True
        )
        
        response = await self.engine.completion(request, **kwargs)
        
        if isinstance(response, LLMResponse):
            # Non-streaming response, yield as single chunk
            yield response
        else:
            # Streaming response, yield each chunk
            async for chunk in response:
                yield chunk
    
    def format_chat_messages(
        self,
        messages: List[LLMMessage],
        add_generation_prompt: Optional[bool] = None
    ) -> str:
        """
        Format chat messages using the current template.
        
        Args:
            messages: List of messages to format
            add_generation_prompt: Whether to add generation prompt
            
        Returns:
            Formatted prompt string
        """
        if not self.current_template:
            raise RuntimeError("No chat template loaded")
        
        return self.chat_template_manager.format_messages(
            messages, 
            self.current_template, 
            add_generation_prompt
        )
    
    def format_for_completion_continuation(
        self,
        messages: List[LLMMessage],
        partial_assistant_content: str
    ) -> str:
        """
        Format messages for completion continuation.
        Used to continue generation after tool/code execution.
        
        Args:
            messages: Previous conversation messages
            partial_assistant_content: Partial assistant response content
            
        Returns:
            Formatted prompt for completion
        """
        if not self.current_template:
            raise RuntimeError("No chat template loaded")
        
        if not self.chat_template_manager.supports_completion(self.current_template):
            raise ValueError(f"Template '{self.current_template}' does not support completion mode")
        
        # Format the full conversation first
        full_conversation = self.format_chat_messages(messages, add_generation_prompt=True)
        
        # Add the partial assistant content
        full_conversation += partial_assistant_content
        
        return full_conversation
    
    def get_template_stop_tokens(self, completion_mode: bool = False) -> List[str]:
        """
        Get stop tokens for the current template.
        
        Args:
            completion_mode: Whether to get completion-specific stop tokens
            
        Returns:
            List of stop tokens
        """
        if not self.current_template:
            raise RuntimeError("No chat template loaded")
        
        if completion_mode:
            return self.chat_template_manager.get_completion_stop_tokens(self.current_template)
        else:
            return self.chat_template_manager.get_stop_tokens(self.current_template)
    
    def get_template_info(self) -> Dict[str, Any]:
        """Get information about the current template."""
        if not self.current_template:
            return {}
        
        try:
            template = self.chat_template_manager.get_template(self.current_template)
            return {
                "name": template.name,
                "description": template.description,
                "model_family": template.model_family,
                "supports_completion": template.completion.get("enabled", False),
                "stop_tokens": template.stop_tokens,
            }
        except Exception:
            return {}
    
    @classmethod
    def list_available_providers(cls) -> List[str]:
        """List all available LLM providers."""
        return LLMEngineFactory.list_providers()
    
    async def reload_config(self) -> None:
        """Reload configuration and recreate engine."""
        await self.load_config()
        await self.create_engine()
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close_engine()