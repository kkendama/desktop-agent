"""
vLLM LLM engine implementation.
"""

import json
from typing import List, Dict, Any, Optional, AsyncGenerator
import httpx
from .base import BaseLLMEngine, LLMConfig, LLMMessage, LLMResponse, CompletionRequest, LLMEngineFactory


class VLLMEngine(BaseLLMEngine):
    """vLLM LLM engine implementation using OpenAI-compatible API."""
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.client = None
        self.base_url = config.endpoint.rstrip('/')
        
        # Extract vLLM-specific config
        self.api_key = None
        self.served_model_name = None
        if config.provider_config:
            vllm_config = config.provider_config.get("vllm", {})
            self.api_key = vllm_config.get("api_key")
            self.served_model_name = vllm_config.get("served_model_name")
    
    async def initialize(self) -> None:
        """Initialize the vLLM client."""
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.config.timeout),
            base_url=self.base_url,
            headers=headers
        )
        
        # Test connection
        try:
            await self.health_check()
        except Exception as e:
            raise ConnectionError(f"Failed to connect to vLLM at {self.base_url}: {e}")
    
    async def health_check(self) -> bool:
        """Check if vLLM is running and accessible."""
        try:
            response = await self.client.get("/v1/models")
            return response.status_code == 200
        except Exception:
            return False
    
    async def generate(
        self,
        messages: List[LLMMessage],
        stream: bool = False,
        **kwargs
    ) -> LLMResponse | AsyncGenerator[LLMResponse, None]:
        """Generate response using vLLM OpenAI-compatible API."""
        await self.ensure_initialized()
        
        # Convert messages to OpenAI format
        openai_messages = []
        for msg in messages:
            openai_messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        # Determine model name to use
        model_name = self.served_model_name or self.config.model
        
        # Prepare request payload
        payload = {
            "model": model_name,
            "messages": openai_messages,
            "stream": stream,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
        }
        
        # Add provider-specific options
        if self.config.provider_config:
            extra_options = self.config.provider_config.get("options", {})
            payload.update(extra_options)
        
        if stream:
            return self._stream_generate(payload)
        else:
            return await self._single_generate(payload)
    
    async def _single_generate(self, payload: Dict[str, Any]) -> LLMResponse:
        """Generate a single response."""
        try:
            response = await self.client.post("/v1/chat/completions", json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            # Extract response content
            choices = result.get("choices", [])
            if not choices:
                raise RuntimeError("No choices returned from vLLM")
            
            message = choices[0].get("message", {})
            content = message.get("content", "")
            
            # Extract usage information
            usage = result.get("usage", {})
            
            return LLMResponse(
                content=content,
                usage={
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
                metadata={
                    "model": result.get("model"),
                    "created": result.get("created"),
                    "finish_reason": choices[0].get("finish_reason"),
                },
                finished=True
            )
            
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"vLLM API error: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            raise RuntimeError(f"vLLM generation failed: {e}")
    
    async def _stream_generate(self, payload: Dict[str, Any]) -> AsyncGenerator[LLMResponse, None]:
        """Generate streaming responses."""
        try:
            async with self.client.stream("POST", "/v1/chat/completions", json=payload) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    line = line.strip()
                    
                    # Skip empty lines and non-data lines
                    if not line or not line.startswith("data: "):
                        continue
                    
                    # Remove "data: " prefix
                    data = line[6:]
                    
                    # Check for end of stream
                    if data == "[DONE]":
                        break
                    
                    try:
                        chunk = json.loads(data)
                        
                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        finish_reason = choices[0].get("finish_reason")
                        
                        usage = chunk.get("usage")
                        
                        yield LLMResponse(
                            content=content,
                            usage={
                                "prompt_tokens": usage.get("prompt_tokens", 0),
                                "completion_tokens": usage.get("completion_tokens", 0),
                                "total_tokens": usage.get("total_tokens", 0),
                            } if usage else None,
                            metadata={
                                "model": chunk.get("model"),
                                "created": chunk.get("created"),
                                "finish_reason": finish_reason,
                            },
                            finished=finish_reason is not None
                        )
                        
                        if finish_reason:
                            break
                            
                    except json.JSONDecodeError:
                        continue
                        
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"vLLM streaming error: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            raise RuntimeError(f"vLLM streaming failed: {e}")
    
    async def completion(
        self,
        request: CompletionRequest,
        **kwargs
    ) -> LLMResponse | AsyncGenerator[LLMResponse, None]:
        """
        Generate completion using vLLM completions API.
        
        Args:
            request: Completion request parameters
            **kwargs: Additional generation parameters
            
        Returns:
            LLMResponse for non-streaming, AsyncGenerator for streaming
        """
        await self.ensure_initialized()
        
        # Build completion payload
        payload = {
            "model": self.served_model_name or self.config.model,
            "prompt": request.prompt,
            "max_tokens": request.max_tokens or self.config.max_tokens,
            "temperature": request.temperature or self.config.temperature,
            "stream": request.stream,
        }
        
        if request.stop:
            payload["stop"] = request.stop
        
        # Add any additional parameters
        payload.update(kwargs)
        
        if request.stream:
            return self._stream_completion(payload)
        else:
            return await self._single_completion(payload)
    
    async def _single_completion(self, payload: Dict[str, Any]) -> LLMResponse:
        """Generate a single completion response."""
        try:
            response = await self.client.post("/v1/completions", json=payload)
            response.raise_for_status()
            
            result = response.json()
            
            # Extract response content
            choices = result.get("choices", [])
            if not choices:
                raise RuntimeError("No choices returned from vLLM completion")
            
            text = choices[0].get("text", "")
            
            # Extract usage information
            usage = result.get("usage", {})
            
            return LLMResponse(
                content=text,
                usage={
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
                metadata={
                    "model": result.get("model"),
                    "created": result.get("created"),
                    "finish_reason": choices[0].get("finish_reason"),
                },
                finished=True
            )
            
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"vLLM completion API error: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            raise RuntimeError(f"vLLM completion failed: {e}")
    
    async def _stream_completion(self, payload: Dict[str, Any]) -> AsyncGenerator[LLMResponse, None]:
        """Generate streaming completion responses."""
        try:
            async with self.client.stream("POST", "/v1/completions", json=payload) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    line = line.strip()
                    
                    # Skip empty lines and non-data lines
                    if not line or not line.startswith("data: "):
                        continue
                    
                    # Remove "data: " prefix
                    data = line[6:]
                    
                    # Check for end of stream
                    if data == "[DONE]":
                        break
                    
                    try:
                        chunk = json.loads(data)
                        
                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        
                        text = choices[0].get("text", "")
                        finish_reason = choices[0].get("finish_reason")
                        
                        # Yield the chunk
                        yield LLMResponse(
                            content=text,
                            usage=chunk.get("usage"),
                            metadata={
                                "model": chunk.get("model"),
                                "created": chunk.get("created"),
                                "finish_reason": finish_reason,
                            },
                            finished=finish_reason is not None
                        )
                        
                        if finish_reason:
                            break
                            
                    except json.JSONDecodeError:
                        continue
                        
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"vLLM completion streaming error: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            raise RuntimeError(f"vLLM completion streaming failed: {e}")

    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()


# Register the engine
LLMEngineFactory.register_engine("vllm", VLLMEngine)