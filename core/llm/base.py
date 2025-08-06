"""
Base classes for LLM inference engines.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, AsyncGenerator
from pydantic import BaseModel
import asyncio


class LLMMessage(BaseModel):
    """Standard message format for LLM communication."""
    role: str  # "system", "user", "assistant", "tool"
    content: str
    name: Optional[str] = None  # Tool name for tool role
    metadata: Optional[Dict[str, Any]] = None


class LLMResponse(BaseModel):
    """Standard response format from LLM."""
    content: str
    usage: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    finished: bool = True


class LLMConfig(BaseModel):
    """Configuration for LLM engines."""
    provider: str  # "ollama" or "vllm"
    model: str
    endpoint: str
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 60
    
    # Provider-specific configs
    provider_config: Optional[Dict[str, Any]] = None


class BaseLLMEngine(ABC):
    """Abstract base class for LLM engines."""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self._initialized = False
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the LLM engine."""
        pass
    
    @abstractmethod
    async def generate(
        self,
        messages: List[LLMMessage],
        stream: bool = False,
        **kwargs
    ) -> LLMResponse | AsyncGenerator[LLMResponse, None]:
        """
        Generate response from the LLM.
        
        Args:
            messages: List of messages for the conversation
            stream: Whether to stream the response
            **kwargs: Additional generation parameters
            
        Returns:
            LLMResponse for non-streaming, AsyncGenerator for streaming
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the LLM engine is healthy and responsive."""
        pass
    
    async def ensure_initialized(self):
        """Ensure the engine is initialized."""
        if not self._initialized:
            await self.initialize()
            self._initialized = True
    
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
        messages = []
        
        if system_prompt:
            messages.append(LLMMessage(role="system", content=system_prompt))
        
        messages.append(LLMMessage(role="user", content=prompt))
        
        response = await self.generate(messages, stream=False, **kwargs)
        
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


class LLMEngineFactory:
    """Factory for creating LLM engines."""
    
    _engines = {}
    
    @classmethod
    def register_engine(cls, provider: str, engine_class: type):
        """Register an LLM engine for a provider."""
        cls._engines[provider] = engine_class
    
    @classmethod
    def create_engine(cls, config: LLMConfig) -> BaseLLMEngine:
        """Create an LLM engine based on configuration."""
        if config.provider not in cls._engines:
            raise ValueError(f"Unknown LLM provider: {config.provider}")
        
        engine_class = cls._engines[config.provider]
        return engine_class(config)
    
    @classmethod
    def list_providers(cls) -> List[str]:
        """List available providers."""
        return list(cls._engines.keys())