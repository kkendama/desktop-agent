"""
Ollama LLM engine implementation.
"""

import json
import asyncio
from typing import List, Dict, Any, Optional, AsyncGenerator
import httpx
from .base import BaseLLMEngine, LLMConfig, LLMMessage, LLMResponse, LLMEngineFactory


class OllamaEngine(BaseLLMEngine):
    """Ollama LLM engine implementation."""
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.client = None
        self.base_url = config.endpoint.rstrip('/')
    
    async def initialize(self) -> None:
        """Initialize the Ollama client."""
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.config.timeout),
            base_url=self.base_url
        )
        
        # Test connection
        try:
            await self.health_check()
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Ollama at {self.base_url}: {e}")
    
    async def health_check(self) -> bool:
        """Check if Ollama is running and accessible."""
        try:
            response = await self.client.get("/api/tags")
            return response.status_code == 200
        except Exception:
            return False
    
    async def generate(
        self,
        messages: List[LLMMessage],
        stream: bool = False,
        **kwargs
    ) -> LLMResponse | AsyncGenerator[LLMResponse, None]:
        """Generate response using Ollama API."""
        await self.ensure_initialized()
        
        # Convert messages to Ollama format
        ollama_messages = []
        for msg in messages:
            ollama_messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        # Prepare request payload
        payload = {
            "model": self.config.model,
            "messages": ollama_messages,
            "stream": stream,
            "options": {
                "temperature": kwargs.get("temperature", self.config.temperature),
                "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
            }
        }
        
        # Add provider-specific options
        if self.config.provider_config:
            payload["options"].update(self.config.provider_config.get("options", {}))
        
        if stream:
            return self._stream_generate(payload)
        else:
            return await self._single_generate(payload)
    
    async def _single_generate(self, payload: Dict[str, Any]) -> LLMResponse:
        """Generate a single response."""
        try:
            response = await self.client.post("/api/chat", json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            return LLMResponse(
                content=result.get("message", {}).get("content", ""),
                usage={
                    "prompt_eval_count": result.get("prompt_eval_count", 0),
                    "eval_count": result.get("eval_count", 0),
                    "total_duration": result.get("total_duration", 0),
                },
                metadata={
                    "model": result.get("model"),
                    "created_at": result.get("created_at"),
                    "done": result.get("done", True),
                },
                finished=True
            )
            
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Ollama API error: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            raise RuntimeError(f"Ollama generation failed: {e}")
    
    async def _stream_generate(self, payload: Dict[str, Any]) -> AsyncGenerator[LLMResponse, None]:
        """Generate streaming responses."""
        try:
            async with self.client.stream("POST", "/api/chat", json=payload) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.strip():
                        try:
                            chunk = json.loads(line)
                            
                            message = chunk.get("message", {})
                            content = message.get("content", "")
                            done = chunk.get("done", False)
                            
                            yield LLMResponse(
                                content=content,
                                usage={
                                    "prompt_eval_count": chunk.get("prompt_eval_count", 0),
                                    "eval_count": chunk.get("eval_count", 0),
                                } if done else None,
                                metadata={
                                    "model": chunk.get("model"),
                                    "created_at": chunk.get("created_at"),
                                },
                                finished=done
                            )
                            
                            if done:
                                break
                                
                        except json.JSONDecodeError:
                            continue
                            
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Ollama streaming error: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            raise RuntimeError(f"Ollama streaming failed: {e}")
    
    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()


# Register the engine
LLMEngineFactory.register_engine("ollama", OllamaEngine)