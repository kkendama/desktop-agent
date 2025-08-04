"""
Core module for Desktop Agent.
"""

from .config import ConfigManager, DesktopAgentConfig, PromptTemplates

__all__ = [
    "ConfigManager",
    "DesktopAgentConfig", 
    "PromptTemplates"
]