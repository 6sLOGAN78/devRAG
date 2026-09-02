## Objective
Implement the Retrieval node, wrapping the Hybrid Search engine built in Phase 06.

## Why Now?
Allows the graph to fetch context before calling the LLM node.

## Dependencies
- 02-llm-node
- Phase 06 (Retrieval)

## Implementation Tasks
- [ ] Create `RetrievalNode` class.
- [ ] Accept `query` from state, and configuration (Dataset IDs, Top-K, similarity thresholds).
- [ ] Call `HybridRetrievalService.search()`.
- [ ] Format output as a context string for downstream LLM nodes.

## Components
- Retrieval Node

## Files
- `agent/component/retrieval.py`

## Interfaces
N/A

## Data Changes
N/A

## Data Flow
Query State -> Retrieval Service -> Vector DB -> Chunks -> Formatted Context String

## Testing
- Integration test: Execute a graph with RetrievalNode -> LLMNode.

## Deliverable
The "RAG" part of the workflow.

## Definition of Done
- Node successfully queries the vector db and outputs context strings.

## Next Subphase
04-logic-nodes