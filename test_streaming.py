#!/usr/bin/env python3
"""
Test script for streaming functionality.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from core.llm.manager import LLMManager
from core.llm.base import LLMMessage


async def test_streaming():
    """Test streaming functionality."""
    print("🧪 Testing Desktop Agent Streaming Functionality")
    print("=" * 50)
    
    # Test configuration file
    config_path = "config/system.yaml"
    
    if not Path(config_path).exists():
        print(f"❌ Configuration file not found: {config_path}")
        print("Please ensure the configuration file exists and is properly configured.")
        return False
    
    try:
        # Initialize LLM Manager
        print("🔧 Initializing LLM Manager...")
        llm_manager = LLMManager(config_path)
        await llm_manager.initialize()
        
        # Check health
        print("🩺 Checking LLM health...")
        if not await llm_manager.health_check():
            print("❌ LLM health check failed!")
            return False
        
        provider_info = llm_manager.get_provider_info()
        print(f"✅ LLM healthy - Provider: {provider_info['provider']}, Model: {provider_info['model']}")
        print()
        
        # Test messages
        test_messages = [
            LLMMessage(role="system", content="You are a helpful assistant. Keep your responses concise."),
            LLMMessage(role="user", content="Please count from 1 to 5 slowly, with a brief explanation for each number.")
        ]
        
        # Test non-streaming first
        print("📝 Testing Non-Streaming Response:")
        print("-" * 30)
        
        response = await llm_manager.generate(test_messages)
        print(f"Content: {response.content}")
        if response.usage:
            print(f"Usage: {response.usage}")
        print()
        
        # Test streaming
        print("🌊 Testing Streaming Response:")
        print("-" * 30)
        
        chunk_count = 0
        accumulated_content = ""
        
        async for chunk in llm_manager.generate_stream(test_messages):
            chunk_count += 1
            if chunk.content:
                accumulated_content += chunk.content
                print(f"Chunk {chunk_count}: '{chunk.content}' (finished: {chunk.finished})")
            
            if chunk.finished:
                if chunk.usage:
                    print(f"Final usage: {chunk.usage}")
                break
        
        print(f"\n📊 Streaming Summary:")
        print(f"  - Total chunks: {chunk_count}")
        print(f"  - Accumulated content length: {len(accumulated_content)}")
        print(f"  - Content preview: {accumulated_content[:100]}...")
        
        # Clean up
        await llm_manager.close_engine()
        
        print("\n✅ All streaming tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_error_handling():
    """Test error handling in streaming."""
    print("\n🛠️ Testing Error Handling:")
    print("-" * 30)
    
    try:
        # Test with invalid configuration
        invalid_manager = LLMManager("nonexistent_config.yaml")
        
        try:
            await invalid_manager.initialize()
            print("❌ Expected initialization to fail with invalid config")
        except FileNotFoundError:
            print("✅ Properly handled missing configuration file")
        except Exception as e:
            print(f"✅ Properly handled initialization error: {e}")
        
        # Test with uninitialized manager
        uninit_manager = LLMManager()
        try:
            async for chunk in uninit_manager.generate_stream([]):
                pass
            print("❌ Expected uninitialized manager to fail")
        except RuntimeError as e:
            print(f"✅ Properly handled uninitialized manager: {e}")
        
        print("✅ Error handling tests passed!")
        
    except Exception as e:
        print(f"❌ Error handling test failed: {e}")


if __name__ == "__main__":
    async def main():
        success = await test_streaming()
        await test_error_handling()
        
        if success:
            print("\n🎉 All tests completed successfully!")
            print("\nTo test the CLI streaming:")
            print("1. Run: python -m cli.main")
            print("2. Use `/stream` to toggle streaming mode")
            print("3. Ask any question to see streaming in action")
        else:
            print("\n💥 Tests failed - please check your configuration")
            sys.exit(1)
    
    asyncio.run(main())