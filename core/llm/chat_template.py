"""
Chat Template Manager for handling different LLM chat formats.
"""

import re
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from .base import LLMMessage


@dataclass
class ChatTemplate:
    """Chat template configuration."""
    name: str
    description: str
    model_family: str
    format: Dict[str, Optional[str]]
    stop_tokens: List[str]
    defaults: Dict[str, Any]
    completion: Dict[str, Any]
    compatible_models: List[str]


class ChatTemplateManager:
    """
    Manager for chat templates.
    Handles loading, parsing, and applying chat templates for different LLM models.
    """
    
    def __init__(self, templates_dir: str = "config/chat_templates"):
        self.templates_dir = Path(templates_dir)
        self._templates: Dict[str, ChatTemplate] = {}
        self._loaded = False
    
    def load_templates(self) -> None:
        """Load all chat templates from the templates directory."""
        if not self.templates_dir.exists():
            raise FileNotFoundError(f"Chat templates directory not found: {self.templates_dir}")
        
        self._templates.clear()
        
        for template_file in self.templates_dir.glob("*.yaml"):
            try:
                template = self._load_template_file(template_file)
                self._templates[template.name] = template
            except Exception as e:
                print(f"Warning: Failed to load template {template_file}: {e}")
        
        if not self._templates:
            raise RuntimeError("No chat templates found. Please ensure template files exist.")
        
        self._loaded = True
    
    def _load_template_file(self, template_file: Path) -> ChatTemplate:
        """Load a single template file."""
        with open(template_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        # Validate required fields
        required_fields = ['name', 'description', 'format', 'stop_tokens', 'defaults']
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Missing required field '{field}' in template {template_file}")
        
        return ChatTemplate(
            name=data['name'],
            description=data['description'],
            model_family=data.get('model_family', data['name']),
            format=data['format'],
            stop_tokens=data['stop_tokens'],
            defaults=data['defaults'],
            completion=data.get('completion', {'enabled': False}),
            compatible_models=data.get('compatible_models', [])
        )
    
    def get_template(self, template_name: str) -> ChatTemplate:
        """Get a specific template by name."""
        if not self._loaded:
            self.load_templates()
        
        if template_name not in self._templates:
            available = list(self._templates.keys())
            raise ValueError(f"Template '{template_name}' not found. Available: {available}")
        
        return self._templates[template_name]
    
    def auto_detect_template(self, model_name: str) -> str:
        """Auto-detect the best template for a given model name."""
        if not self._loaded:
            self.load_templates()
        
        # Try to match model name against compatible models
        for template_name, template in self._templates.items():
            for pattern in template.compatible_models:
                if re.search(pattern, model_name, re.IGNORECASE):
                    return template_name
        
        # Default fallback
        if "chatml" in self._templates:
            return "chatml"
        elif "openai" in self._templates:
            return "openai"
        else:
            # Return first available template
            return list(self._templates.keys())[0]
    
    def list_templates(self) -> List[str]:
        """List all available template names."""
        if not self._loaded:
            self.load_templates()
        return list(self._templates.keys())
    
    def format_messages(
        self,
        messages: List[LLMMessage],
        template_name: str,
        add_generation_prompt: Optional[bool] = None
    ) -> str:
        """
        Format messages using the specified template.
        
        Args:
            messages: List of messages to format
            template_name: Name of the template to use
            add_generation_prompt: Whether to add generation prompt
            
        Returns:
            Formatted string ready for completion
        """
        template = self.get_template(template_name)
        
        if add_generation_prompt is None:
            add_generation_prompt = template.defaults.get('add_generation_prompt', True)
        
        formatted_parts = []
        
        for message in messages:
            role = message.role
            content = message.content
            
            # Get template for this role
            role_template = template.format.get(role)
            if role_template is None:
                # Handle special case for OpenAI-style templates
                if template.name == "openai":
                    # OpenAI templates use structured messages, not string formatting
                    continue
                else:
                    raise ValueError(f"No template found for role '{role}' in template '{template_name}'")
            
            # Format the message
            formatted_message = role_template.format(content=content)
            formatted_parts.append(formatted_message)
        
        # Join all parts
        result = "".join(formatted_parts)
        
        # Add generation prompt if requested
        if add_generation_prompt and template.format.get('generation_prompt'):
            result += template.format['generation_prompt']
        
        return result
    
    def format_messages_for_api(
        self,
        messages: List[LLMMessage],
        template_name: str
    ) -> Union[str, List[Dict[str, str]]]:
        """
        Format messages for API calls.
        
        For string-based templates (like ChatML), returns formatted string.
        For API-based templates (like OpenAI), returns list of message dicts.
        
        Args:
            messages: List of messages to format
            template_name: Name of the template to use
            
        Returns:
            Either formatted string or list of message dictionaries
        """
        template = self.get_template(template_name)
        
        # Check if this is an API-style template (like OpenAI)
        if template.name == "openai" or template.format.get('system') is None:
            # Return structured messages for API calls
            return [{"role": msg.role, "content": msg.content} for msg in messages]
        else:
            # Return formatted string for completion-style APIs
            return self.format_messages(messages, template_name, add_generation_prompt=False)
    
    def get_stop_tokens(self, template_name: str) -> List[str]:
        """Get stop tokens for the specified template."""
        template = self.get_template(template_name)
        return template.stop_tokens.copy()
    
    def supports_completion(self, template_name: str) -> bool:
        """Check if the template supports completion mode."""
        template = self.get_template(template_name)
        return template.completion.get('enabled', False)
    
    def format_for_completion(
        self,
        partial_content: str,
        template_name: str
    ) -> str:
        """
        Format partial content for completion mode.
        
        Args:
            partial_content: Partial assistant response content
            template_name: Name of the template to use
            
        Returns:
            Formatted string for completion
        """
        template = self.get_template(template_name)
        
        if not self.supports_completion(template_name):
            raise ValueError(f"Template '{template_name}' does not support completion mode")
        
        completion_template = template.completion.get('continue_template', '{partial_content}')
        return completion_template.format(partial_content=partial_content)
    
    def get_completion_stop_tokens(self, template_name: str) -> List[str]:
        """Get stop tokens for completion mode."""
        template = self.get_template(template_name)
        return template.completion.get('completion_stop_tokens', template.stop_tokens).copy()