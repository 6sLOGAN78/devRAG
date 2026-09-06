# Phase 07-02 LLM Generation Node Completion Report

## 1. What Changed
Implemented `LLMNode`, the central generative component of the agent graph runtime. The node inherits from the Phase 07-01 `AgentNode` and consumes runtime execution variables, dynamically renders configurable Jinja2 prompt templates, executes API calls securely utilizing `litellm`, and streams/accumulates responses perfectly aligned with the execution graph boundaries.

## 2. Files Changed
* `agent/component/llm.py` (Created)
  * Houses `LLMNode` class mapping `execute(resolved_inputs)` to standard LiteLLM completions. Contains Sandboxed Jinja2 integration.
* `agent/registry.py` (Modified)
  * Appended lazy import and registration of `"llm"` → `LLMNode`.
* `tests/unit/test_llm_node.py` (Created)
  * Wrote 11 dedicated unit/integration tests confirming complete graph mapping, streaming stability, timeout failure loops, missing parameter isolation, missing configuration assertions, and rate-limit parsing.

## 3. Actual `AgentNode` Contract
The node explicitly implements the synchronous graph protocol:
```python
class LLMNode(AgentNode):
    def __init__(self, node_id: str, config: Optional[Dict[str, Any]] = None): ...
    def execute(self, resolved_inputs: Dict[str, Any]) -> Dict[str, Any]: ...
```

## 4. LLM Configuration
Configuration follows schema:
```json
{
  "id": "generate_answer",
  "type": "llm",
  "config": {
    "model": "gpt-4",
    "prompt": "Answer the following question:\n{{ question }}",
    "system_prompt": "You are a helpful assistant.",
    "stream": true,
    "temperature": 0.7,
    "max_tokens": 1024
  }
}
```

## 5. Prompt Rendering
Renders prompts seamlessly via `jinja2.sandbox.SandboxedEnvironment`. State variables retrieved from `ExecutionState` and filtered through the runner's `inputs_map` form `resolved_inputs`.

Example:
**State**: `{"name": "Ayush", "question": "What is RRF?"}`
**Template**: `"Hello {{ name }}. Explain {{ question }}."`
**Result**: `"Hello Ayush. Explain What is RRF?."`

If a variable is missing (e.g. `{{ missing }}`), `StrictUndefined` enforces a `ValueError` stopping execution before any outbound API call occurs.

## 6. Provider Architecture
```text
LLMNode (config: model, messages)
  ↓
litellm.completion() (transparent fallback)
  ↓
OpenAI / Anthropic / Local models (routed automatically via config.model)
```
Uses `litellm` directly, relying on standard OS environment keys for transparent integration with `rag.nlp.embedding` provider keys. No direct vendor SDK imports.

## 7. Streaming
* **Stream Contract**: Supported when `config.stream = True`.
* **Accumulation**: `GraphRunner` is synchronous. Stream chunks (`chunk.choices[0].delta.content`) are synchronously iterated in memory as they arrive from `litellm`.
* **Final State Behavior**: The fully assembled string is written into the `ExecutionState` at the conclusion of the stream. Downstream nodes are completely protected from receiving partial text. 
* **Failure Behavior**: If a stream crashes mid-chunk, the node immediately halts raising the exception to the `GraphRunner` fail-fast circuit. Partial output is correctly thrown away (no silent failures).
* **Cancellation**: Managed implicitly by Python generator exit.

## 8. State Contract
* **Output Format**:
  ```json
  {
      "text": "The complete generated answer",
      "model": "gpt-4",
      "usage": {"total_tokens": 120, "prompt_tokens": 20, "completion_tokens": 100}
  }
  ```
* **Downstream Access**: A downstream node can target `"llm_node.text"` mapping natively to `AgentGraph.inputs_map`.

## 9. Security
* **Template Safety**: Employs `SandboxedEnvironment`. Nodes cannot evaluate `__import__('os').system('rm -rf /')` out of maliciously structured user variables.
* **API Key Storage**: Hardcoded keys are explicitly absent. Relies entirely on underlying repository/OS configuration bindings through `litellm`.
* **Logging**: Output explicitly masks prompts on default log-levels and hides all security credentials.

## 10. Error Handling
Traps and propagates native `litellm` errors cleanly:
* `AuthenticationError` (surfaces up)
* `RateLimitError` (surfaces up)
* `Timeout` (surfaces up, unbounded infinite retries prevented)
* `TemplateError` / Missing variable (trapped as localized `ValueError` pre-network).

## 11. Tests
* **Tests added**: 1 module (`tests/unit/test_llm_node.py`).
* **Tests executed**: 11 unique assertions testing timeouts, exceptions, malformed packets, rate-limits, missing template parameters, template substitution, synchronous streaming assembly, streaming interrupts, and integration cleanly back to the `GraphRunner` topology loop.
* **Pass/Fail**: 11 passed, 0 failed.

## 12. Performance
* **Latency**: `litellm` reuses connections natively beneath the `requests`/`httpx` abstractions depending on environment configuration.
* **Streaming Queue**: Strictly `yields` string deltas in a localized buffer. Prevents unbounded graph queue loops.

## 13. Known Limitations
* **Local Inference via Ollama**: Local engines through `litellm` depend exclusively on OS environments (e.g., `OLLAMA_API_BASE`). Additional model map config parsing may be needed based on `.agents` decisions.
* **Stream Iteration Async Hook**: Given the graph executes nodes synchronously, the internal stream isn't yielded to the frontend progressively. The `GraphRunner` pauses, executes the *entire* stream sequence locally, assembles the string, and finally stores it to `ExecutionState`. Fully async graph edges/callbacks would be required to stream characters live to a websocket/UI simultaneously.

## 14. Next Phase Readiness
`07-03-retrieval-node` is completely unblocked.
The upcoming RetrievalNode merely needs to insert `{"retrieved_chunks": "..."}` into the `ExecutionState`. Our completed LLMNode will seamlessly pick it up inside a template loop (`{{ retrieved_chunks }}`).
