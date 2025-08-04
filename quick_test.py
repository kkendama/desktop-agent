#!/usr/bin/env python3
"""
Quick test script to verify basic functionality.
"""

import sys
import asyncio
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import ConfigManager
from core.llm.manager import LLMManager
from core.llm.base import LLMMessage


async def test_basic_functionality():
    """Test basic functionality without requiring LLM server."""
    
    print("🔧 Testing Desktop Agent Basic Functionality")
    print("=" * 50)
    
    # Test 1: Configuration Loading
    print("\n1️⃣  Testing configuration loading...")
    try:
        config_manager = ConfigManager()
        config_valid = config_manager.validate_configs()
        print(f"   ✅ Configuration validation: {config_valid}")
        
        # Test specific config loading
        system_config = config_manager.get_system_config()
        llm_config = config_manager.get_llm_config()
        print(f"   ✅ LLM Provider: {llm_config.get('provider', 'unknown')}")
        print(f"   ✅ LLM Model: {llm_config.get('model', 'unknown')}")
        
    except Exception as e:
        print(f"   ❌ Configuration test failed: {e}")
        return False
    
    # Test 2: Prompt Template Formatting
    print("\n2️⃣  Testing prompt templates...")
    try:
        greeting = config_manager.get_user_greeting()
        print(f"   ✅ User greeting loaded: {len(greeting)} characters")
        
        system_prompt = config_manager.get_system_prompt(
            current_datetime="2024-01-01 12:00:00",
            workspace_path="/test/workspace"
        )
        print(f"   ✅ System prompt formatted: {len(system_prompt)} characters")
        
    except Exception as e:
        print(f"   ❌ Prompt template test failed: {e}")
        return False
    
    # Test 3: LLM Manager Initialization (without server)
    print("\n3️⃣  Testing LLM manager...")
    try:
        llm_manager = LLMManager()
        await llm_manager.load_config()
        
        provider_info = llm_manager.get_provider_info()
        print(f"   ✅ Provider info: {provider_info}")
        
        available_providers = llm_manager.list_available_providers()
        print(f"   ✅ Available providers: {available_providers}")
        
    except Exception as e:
        print(f"   ❌ LLM manager test failed: {e}")
        return False
    
    # Test 4: Message Objects
    print("\n4️⃣  Testing message objects...")
    try:
        user_msg = LLMMessage(role="user", content="Hello, AI!")
        assistant_msg = LLMMessage(role="assistant", content="Hello, human!")
        
        print(f"   ✅ User message: {user_msg.role} - {user_msg.content}")
        print(f"   ✅ Assistant message: {assistant_msg.role} - {assistant_msg.content}")
        
    except Exception as e:
        print(f"   ❌ Message objects test failed: {e}")
        return False
    
    print("\n🎉 All basic tests passed!")
    print("\n📋 Next Steps:")
    print("   1. Start Ollama server: `ollama serve`")
    print("   2. Pull Qwen3 model: `ollama pull qwen3:latest`")
    print("   3. Run Desktop Agent: `python cli/main.py`")
    
    return True


if __name__ == "__main__":
    success = asyncio.run(test_basic_functionality())
    sys.exit(0 if success else 1)