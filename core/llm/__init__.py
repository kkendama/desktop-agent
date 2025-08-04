"""
LLM inference engine module for Desktop Agent.
"""

from .base import (
    BaseLLMEngine,
    LLMConfig,
    LLMMessage,
    LLMResponse,
    LLMEngineFactory
)
from .manager import LLMManager
from .ollama_engine import OllamaEngine
from .vllm_engine import VLLMEngine

__all__ = [
    "BaseLLMEngine",
    "LLMConfig", 
    "LLMMessage",
    "LLMResponse",
    "LLMEngineFactory",
    "LLMManager",
    "OllamaEngine",
    "VLLMEngine"
]