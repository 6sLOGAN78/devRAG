## Objective
Implement the LLM generation node, handling streaming API calls to providers.

## Why Now?
The most critical node in any AI workflow.

## Dependencies
- 01-graph-execution-model

## Implementation Tasks
- [ ] Create `LLMNode` class inheriting from `AgentNode`.
- [ ] Integrate LiteLLM for chat completions.
- [ ] Support prompt template rendering with Jinja2 or Python formatting (using input state variables).
- [ ] Support streaming output generators.

## Components
- LLM Node

## Files
- `agent/component/llm.py`

## Interfaces
- Outbound LLM APIs (OpenAI, Anthropic).

## Data Changes
N/A

## Data Flow
State Variables -> Render Prompt -> LLM API -> Node Output

## Testing
- Unit test LLM node execution with a simple prompt.

## Deliverable
Functioning LLM generation within the graph.

## Definition of Done
- Node correctly formats prompts and returns text completions.

## Next Subphase
03-retrieval-node