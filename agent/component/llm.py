import logging
from typing import Any, Dict, Optional
import litellm
from jinja2.sandbox import SandboxedEnvironment
from jinja2 import StrictUndefined, TemplateError

from .base import AgentNode

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
            
        litellm_kwargs = {
            "model": self.model,
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
                "model": self.model,
                "usage": usage
            }
            
        except Exception as e:
            logger.error(f"LLM API failure in node {self.id}: {e}")
            raise e
