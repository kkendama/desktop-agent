# Test the integration
import asyncio
from core.tool_executor import ToolExecutor

async def test_integration():
    executor = ToolExecutor()
    
    test_text = '<tool_use> name: get_current_time parameters: {\"timezone\": \"Asia/Tokyo\"} </tool_use>'
    print(f'Testing: {test_text}')
    
    tool_results, cleaned_text = await executor.execute_tools_in_text(test_text)
    
    print(f'Tool results: {len(tool_results)}')
    for result in tool_results:
        print(f'  - Success: {result.success}')
        print(f'  - Content: {result.content[:100]}...')
        if result.error:
            print(f'  - Error: {result.error}')
    
    print(f'Cleaned text: {cleaned_text}')

asyncio.run(test_integration())