import logging
from typing import Any, Dict, Optional
import litellm
from jinja2.sandbox import SandboxedEnvironment
from jinja2 import StrictUndefined, TemplateError

from .base import AgentNode
from common.settings import load_config

logger = logging.getLogger(__name__)

class LLMNode(AgentNode):
    """
    Executes an LLM chat completion using the provided configuration and prompt.
    Supports secure template rendering via Sandboxed Jinja2.
    """
    def __init__(self, node_id: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(node_id, config)
        self.model = self.config.get("model", "gpt-3.5-turbo")
        self.system_prompt = self.config.get("system_prompt", "")
        self.prompt_template = self.config.get("prompt", "")
        self.stream = self.config.get("stream", False)
        self.temperature = self.config.get("temperature", 0.7)
        self.max_tokens = self.config.get("max_tokens", None)
        
        # Use a sandboxed environment to prevent arbitrary code execution,
        # and StrictUndefined to raise errors for missing template variables.
        self._jinja_env = SandboxedEnvironment(undefined=StrictUndefined)
        
    def _render_template(self, template_str: str, resolved_inputs: Dict[str, Any]) -> str:
        if not template_str:
            return ""
        try:
            template = self._jinja_env.from_string(template_str)
            return template.render(**resolved_inputs)
        except TemplateError as e:
            raise ValueError(f"Template rendering failed in node {self.id}: {str(e)}")
            
    def execute(self, resolved_inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Renders the prompt templates, executes the LLM completion via LiteLLM,
        and returns the generated text.
        """
        if not self.model:
            raise ValueError(f"Node {self.id} is missing a model configuration")
            
        rendered_prompt = self._render_template(self.prompt_template, resolved_inputs)
        rendered_system = self._render_template(self.system_prompt, resolved_inputs)
            
        messages = []
        if rendered_system:
            messages.append({"role": "system", "content": rendered_system})
            
        if rendered_prompt:
            messages.append({"role": "user", "content": rendered_prompt})
            
        if not messages:
            raise ValueError(f"Node {self.id} generated empty prompt messages")
            
        # Load user_default_llm configuration
        cfg = load_config("conf/service_conf.yaml")
        chat_cfg = cfg.user_default_llm.default_models.chat_model
        # Fallback to configured default if model is not set or we want to use defaults
        actual_model = self.model
        if chat_cfg.name and ("/" not in actual_model):
            actual_model = f"{chat_cfg.factory}/{chat_cfg.name}"

        litellm_kwargs = {
            "model": actual_model,
            "api_key": chat_cfg.api_key if chat_cfg.api_key else None,
            "api_base": chat_cfg.base_url if chat_cfg.base_url else None,
            "messages": messages,
            "stream": self.stream,
        }
        
        if self.temperature is not None:
            litellm_kwargs["temperature"] = self.temperature
        if self.max_tokens is not None:
            litellm_kwargs["max_tokens"] = self.max_tokens
            
        logger.info(f"Invoking LLM for node {self.id} with model {self.model} (stream={self.stream})")
        
        try:
            response = litellm.completion(**litellm_kwargs)
            
            if self.stream:
                accumulated_text = ""
                # Accumulate the stream synchronously since graph runner is synchronous
                stream_callback = resolved_inputs.get("__stream_callback__")
                for chunk in response:
                    # Litellm handles OpenAI and Anthropic stream chunks uniformly
                    delta = chunk.choices[0].delta.content
                    if delta:
                        accumulated_text += delta
                        if stream_callback:
                            stream_callback(delta)
                        
                output_text = accumulated_text
                usage = None  # Usage not universally tracked on standard streamed chunks without callbacks
            else:
                output_text = response.choices[0].message.content or ""
                # Safely extract usage if available
                usage = None
                if hasattr(response, "usage") and response.usage:
                    usage = dict(response.usage)
                
            return {
                "text": output_text,
                "usage": usage
            }
            
        except Exception as e:
            logger.error(f"LLM API failure in node {self.id}: {e}")
            raise e
