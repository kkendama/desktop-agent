"""
LLM Manager for handling multiple LLM engines and configurations.
"""

import yaml
import asyncio
from typing import Dict, Any, Optional, List
from pathlib import Path
from .base import BaseLLMEngine, LLMConfig, LLMMessage, LLMResponse, LLMEngineFactory
from .ollama_engine import OllamaEngine
from .vllm_engine import VLLMEngine


class LLMManager:
    """
    Manager class for LLM engines.
    Handles configuration loading, engine initialization, and message routing.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or "config/system.yaml"
        self.engine: Optional[BaseLLMEngine] = None
        self.config: Optional[LLMConfig] = None
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
            stream: Whether to stream the response (currently returns complete response)
            **kwargs: Additional generation parameters
            
        Returns:
            LLM response
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