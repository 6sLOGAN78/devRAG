# Phase 07: Agentic Workflow Engine (Backend)

## Phase Objective
Build the Python backend graph execution engine capable of running directed acyclic graphs (DAGs) representing multi-step agent workflows.

## Why This Phase Comes Here
RAG is no longer just prompt chaining. We need a graph engine to connect Retrieval, LLM, and Logic nodes together.

## Dependencies
Depends on:
- Phase 06 (Retrieval Engine)

Required by:
- Phase 08 (Frontend Canvas), Phase 09 (Chat API)

## Phase Architecture
A custom node-based execution runtime in Python (`agent/component`). Each node defines an `execute()` method. The engine traverses the graph statefully.

## Subphase Order
01-graph-execution-model -> 02-llm-node -> 03-retrieval-node -> 04-logic-nodes

## Phase Deliverable
A headless Python graph engine that can execute complex RAG JSON definitions.

## Phase Definition of Done
- Given a JSON DAG definition, the engine executes nodes in correct topological order.
- State/Memory is passed between nodes.

## What NOT To Build Yet
The visual UI editor (Phase 08).

## Next Phase
Phase 08: Agent Canvas UI
