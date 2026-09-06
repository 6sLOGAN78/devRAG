import logging
from typing import Any, Dict, Optional
import litellm
from jinja2.sandbox import SandboxedEnvironment
from jinja2 import StrictUndefined, TemplateError

from RestrictedPython import compile_restricted
from RestrictedPython.Guards import safe_builtins, full_write_guard
from RestrictedPython.Eval import default_guarded_getitem, default_guarded_getiter

from .base import AgentNode, NodeResult

logger = logging.getLogger(__name__)

class SwitchNode(AgentNode):
    """
    Evaluates a Jinja2 expression to determine the routing path.
    """
    def __init__(self, node_id: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(node_id, config)
        self.expression = self.config.get("expression", "")
        self._jinja_env = SandboxedEnvironment(undefined=StrictUndefined)
        
    def execute(self, resolved_inputs: Dict[str, Any]) -> NodeResult:
        if not self.expression:
            raise ValueError(f"SwitchNode {self.id} requires an 'expression' config.")
            
        try:
            template = self._jinja_env.from_string(self.expression)
            route = template.render(**resolved_inputs).strip()
            if not route:
                route = None
            return NodeResult(output={"route": route}, route=route)
        except TemplateError as e:
            raise ValueError(f"Template rendering failed in SwitchNode {self.id}: {str(e)}")

class CategorizeNode(AgentNode):
    """
    Uses an LLM to classify the input into one of the predefined categories.
    """
    def __init__(self, node_id: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(node_id, config)
        self.categories = self.config.get("categories", [])
        self.prompt_template = self.config.get("prompt", "")
        self.model = self.config.get("model", "gpt-3.5-turbo")
        self._jinja_env = SandboxedEnvironment(undefined=StrictUndefined)
        
    def execute(self, resolved_inputs: Dict[str, Any]) -> NodeResult:
        if not self.categories:
            raise ValueError(f"CategorizeNode {self.id} requires a 'categories' list.")
            
        try:
            template = self._jinja_env.from_string(self.prompt_template)
            rendered_prompt = template.render(**resolved_inputs)
        except TemplateError as e:
            raise ValueError(f"Template rendering failed in CategorizeNode {self.id}: {str(e)}")
            
        cats_str = ", ".join(self.categories)
        system_prompt = (
            f"You are a strict routing assistant. Classify the user's input into EXACTLY ONE "
            f"of the following categories: [{cats_str}]. Reply with ONLY the category name. "
            f"Do not add any extra text or punctuation."
        )
        
        try:
            response = litellm.completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": rendered_prompt}
                ],
                temperature=0.0
            )
            
            output_text = response.choices[0].message.content.strip()
            
            route = output_text
            if route not in self.categories:
                logger.warning(f"CategorizeNode {self.id} produced invalid category: '{route}'.")
                
            return NodeResult(output={"category": route}, route=route)
        except Exception as e:
            logger.error(f"LLM API failure in CategorizeNode {self.id}: {e}")
            raise e

class CodeNode(AgentNode):
    """
    Executes restricted Python code for safe data transformation.
    Code should read from `inputs` (dict) and assign to `output` (dict).
    """
    def __init__(self, node_id: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(node_id, config)
        self.code = self.config.get("code", "")
        
    def execute(self, resolved_inputs: Dict[str, Any]) -> Any:
        if not self.code:
            raise ValueError(f"CodeNode {self.id} requires 'code' config.")
            
        try:
            byte_code = compile_restricted(self.code, '<inline>', 'exec')
            
            loc = {'inputs': resolved_inputs, 'output': {}}
            
            globs = {
                '__builtins__': safe_builtins,
                '_write_': full_write_guard,
                '_getattr_': getattr,
                '_getitem_': default_guarded_getitem,
                '_getiter_': default_guarded_getiter,
            }
            
            exec(byte_code, globs, loc)
            
            return loc.get('output', {})
        except Exception as e:
            logger.error(f"Code execution failed in CodeNode {self.id}: {e}")
            raise RuntimeError(f"Restricted code execution failed: {str(e)}")
