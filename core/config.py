"""
Configuration management for Desktop Agent.
"""

import yaml
import toml
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic import BaseModel


class DesktopAgentConfig(BaseModel):
    """Main configuration class for Desktop Agent."""
    
    # LLM Configuration
    llm: Dict[str, Any]
    
    # MCP Configuration
    mcp: Dict[str, Any]
    
    # Sandbox Configuration
    sandbox: Dict[str, Any]
    
    # Security Configuration
    security: Dict[str, Any]
    
    # Storage Configuration
    storage: Dict[str, Any]
    
    # Chat Configuration
    chat: Dict[str, Any]
    
    # Logging Configuration
    logging: Dict[str, Any]
    
    # CLI Configuration
    cli: Dict[str, Any]
    
    # API Configuration
    api: Dict[str, Any]


class PromptTemplates(BaseModel):
    """Prompt templates configuration."""
    
    system: Dict[str, str]
    tools: Dict[str, str]
    memory: Dict[str, str]
    responses: Dict[str, str]
    personality: Dict[str, str]


class ConfigManager:
    """Configuration manager for Desktop Agent."""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.system_config_path = self.config_dir / "system.yaml"
        self.prompts_config_path = self.config_dir / "prompts.toml"
        
        self._system_config: Optional[DesktopAgentConfig] = None
        self._prompt_templates: Optional[PromptTemplates] = None
    
    def load_system_config(self) -> DesktopAgentConfig:
        """Load system configuration from YAML file."""
        if not self.system_config_path.exists():
            raise FileNotFoundError(f"System config not found: {self.system_config_path}")
        
        with open(self.system_config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        
        self._system_config = DesktopAgentConfig(**config_data)
        return self._system_config
    
    def load_prompt_templates(self) -> PromptTemplates:
        """Load prompt templates from TOML file."""
        if not self.prompts_config_path.exists():
            raise FileNotFoundError(f"Prompts config not found: {self.prompts_config_path}")
        
        with open(self.prompts_config_path, 'r', encoding='utf-8') as f:
            prompts_data = toml.load(f)
        
        self._prompt_templates = PromptTemplates(**prompts_data)
        return self._prompt_templates
    
    def get_system_config(self) -> DesktopAgentConfig:
        """Get cached system configuration or load it."""
        if self._system_config is None:
            self.load_system_config()
        return self._system_config
    
    def get_prompt_templates(self) -> PromptTemplates:
        """Get cached prompt templates or load them."""
        if self._prompt_templates is None:
            self.load_prompt_templates()
        return self._prompt_templates
    
    def reload_configs(self) -> None:
        """Reload all configurations."""
        self._system_config = None
        self._prompt_templates = None
        self.load_system_config()
        self.load_prompt_templates()
    
    def get_llm_config(self) -> Dict[str, Any]:
        """Get LLM configuration."""
        config = self.get_system_config()
        return config.llm
    
    def get_mcp_config(self) -> Dict[str, Any]:
        """Get MCP configuration."""
        config = self.get_system_config()
        return config.mcp
    
    def get_cli_config(self) -> Dict[str, Any]:
        """Get CLI configuration."""
        config = self.get_system_config()
        return config.cli
    
    def get_sandbox_config(self) -> Dict[str, Any]:
        """Get sandbox configuration."""
        config = self.get_system_config()
        return config.sandbox
    
    def get_security_config(self) -> Dict[str, Any]:
        """Get security configuration."""
        config = self.get_system_config()
        return config.security
    
    def format_prompt(
        self, 
        template_category: str, 
        template_name: str, 
        **kwargs
    ) -> str:
        """
        Format a prompt template with provided variables.
        
        Args:
            template_category: Category of the template (e.g., "system", "tools")
            template_name: Name of the template within the category
            **kwargs: Variables to substitute in the template
            
        Returns:
            Formatted prompt string
        """
        templates = self.get_prompt_templates()
        
        category_templates = getattr(templates, template_category, {})
        if not isinstance(category_templates, dict):
            raise ValueError(f"Invalid template category: {template_category}")
        
        template = category_templates.get(template_name)
        if not template:
            raise ValueError(f"Template not found: {template_category}.{template_name}")
        
        try:
            return template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Missing template variable: {e}")
    
    def get_available_tools_description(self) -> str:
        """Generate description of available MCP tools for system prompt."""
        mcp_config = self.get_mcp_config()
        
        if not mcp_config.get("enabled", False):
            return "No external tools are currently available."
        
        servers = mcp_config.get("servers", [])
        if not servers:
            return "No MCP servers are configured."
        
        tools_description = "Available Functions:\n"
        
        for server in servers:
            server_name = server.get("name", "Unknown")
            server_desc = server.get("description", "")
            tools = server.get("tools", [])
            
            if tools:
                tools_description += f"\n## {server_name.title()} Server\n"
                if server_desc:
                    tools_description += f"Description: {server_desc}\n\n"
                
                for tool in tools:
                    if tool.get("type") == "function":
                        func = tool.get("function", {})
                        func_name = func.get("name", "unknown")
                        func_desc = func.get("description", "No description")
                        
                        tools_description += f"### {func_name}\n"
                        tools_description += f"- **Description**: {func_desc}\n"
                        
                        # Add parameters information
                        params = func.get("parameters", {})
                        if params and params.get("properties"):
                            tools_description += "- **Parameters**:\n"
                            for param_name, param_info in params["properties"].items():
                                param_desc = param_info.get("description", "No description")
                                param_type = param_info.get("type", "unknown")
                                required = param_name in params.get("required", [])
                                req_marker = " (required)" if required else " (optional)"
                                tools_description += f"  - `{param_name}` ({param_type}){req_marker}: {param_desc}\n"
                        
                        tools_description += "\n"
        
        return tools_description.strip()
    
    def get_system_prompt(self, **kwargs) -> str:
        """Get formatted system prompt with available tools."""
        # Add available tools description to kwargs
        kwargs["available_tools"] = self.get_available_tools_description()
        
        return self.format_prompt("system", "base", **kwargs)
    
    def get_user_greeting(self) -> str:
        """Get user greeting message."""
        return self.format_prompt("system", "user_greeting")
    
    def validate_configs(self) -> bool:
        """Validate all configurations."""
        try:
            self.get_system_config()
            self.get_prompt_templates()
            return True
        except Exception as e:
            print(f"Configuration validation failed: {e}")
            return False