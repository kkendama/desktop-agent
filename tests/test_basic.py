"""
Basic tests for Desktop Agent.
"""

import pytest
import asyncio
from pathlib import Path
import sys

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import ConfigManager
from core.llm.base import LLMConfig, LLMMessage, LLMResponse
from core.llm.manager import LLMManager


class TestConfigManager:
    """Test configuration management."""
    
    def test_config_loading(self):
        """Test loading configuration files."""
        config_manager = ConfigManager()
        
        # Test system config loading
        system_config = config_manager.load_system_config()
        assert system_config is not None
        assert hasattr(system_config, 'llm')
        assert hasattr(system_config, 'mcp')
        
        # Test prompt templates loading
        prompt_templates = config_manager.load_prompt_templates()
        assert prompt_templates is not None
        assert hasattr(prompt_templates, 'system')
        assert hasattr(prompt_templates, 'tools')
    
    def test_prompt_formatting(self):
        """Test prompt template formatting."""
        config_manager = ConfigManager()
        config_manager.load_prompt_templates()
        
        # Test system prompt formatting
        system_prompt = config_manager.format_prompt(
            "system", "base",
            current_datetime="2024-01-01 12:00:00",
            workspace_path="/test/path"
        )
        
        assert "2024-01-01 12:00:00" in system_prompt
        assert "/test/path" in system_prompt
    
    def test_config_validation(self):
        """Test configuration validation."""
        config_manager = ConfigManager()
        
        # Should return True for valid configs
        is_valid = config_manager.validate_configs()
        assert is_valid is True


class TestLLMConfig:
    """Test LLM configuration classes."""
    
    def test_llm_message_creation(self):
        """Test LLM message creation."""
        message = LLMMessage(role="user", content="Hello, AI!")
        
        assert message.role == "user"
        assert message.content == "Hello, AI!"
        assert message.metadata is None
    
    def test_llm_response_creation(self):
        """Test LLM response creation."""
        response = LLMResponse(
            content="Hello, human!",
            usage={"tokens": 10},
            finished=True
        )
        
        assert response.content == "Hello, human!"
        assert response.usage["tokens"] == 10
        assert response.finished is True
    
    def test_llm_config_creation(self):
        """Test LLM config creation."""
        config = LLMConfig(
            provider="ollama",
            model="qwen3:latest",
            endpoint="http://localhost:11434",
            temperature=0.7,
            max_tokens=4096
        )
        
        assert config.provider == "ollama"
        assert config.model == "qwen3:latest"
        assert config.endpoint == "http://localhost:11434"
        assert config.temperature == 0.7
        assert config.max_tokens == 4096


@pytest.mark.asyncio
class TestLLMManager:
    """Test LLM manager functionality."""
    
    async def test_llm_manager_initialization(self):
        """Test LLM manager initialization."""
        manager = LLMManager()
        
        # Test configuration loading
        await manager.load_config()
        assert manager.config is not None
        assert manager.config.provider in ["ollama", "vllm"]
    
    async def test_provider_info(self):
        """Test getting provider information."""
        manager = LLMManager()
        await manager.load_config()
        
        info = manager.get_provider_info()
        assert "provider" in info
        assert "model" in info
        assert "endpoint" in info
    
    def test_available_providers(self):
        """Test listing available providers."""
        providers = LLMManager.list_available_providers()
        assert "ollama" in providers
        assert "vllm" in providers


if __name__ == "__main__":
    pytest.main([__file__])