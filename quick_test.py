from core.config import ConfigManager
import datetime

# Test the system prompt generation
config_manager = ConfigManager()
current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
workspace_path = '/mnt/c/Users/KK/llm/desktop-agent'

try:
    system_prompt = config_manager.get_system_prompt(
        current_datetime=current_time,
        workspace_path=workspace_path
    )
    print('✅ System prompt generation successful!')
    print('Length:', len(system_prompt))
except Exception as e:
    print('❌ Error:', e)