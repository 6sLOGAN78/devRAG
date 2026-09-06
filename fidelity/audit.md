You are auditing an existing implementation called DevRAG against the actual RAGFlow source code.

REFERENCE RAGFLOW REPOSITORY:

/home/logan78/Desktop/ragflow

TARGET DEVRAG REPOSITORY:

/home/logan78/Desktop/devRAG

REVERSE-ENGINEERING DOCUMENTATION:

/home/logan78/Desktop/devRAG/ragflow-docs

IMPORTANT:

RAGFlow is the reference system.

DevRAG is the existing implementation that must eventually be fixed.

Do NOT modify the RAGFlow repository.

Do NOT modify DevRAG during this initial audit.

Your job in this iteration is ONLY to understand and compare the systems.

---

## 1. Inspect RAGFlow

Recursively inspect the actual RAGFlow repository.

Understand its:

* architecture
* services
* APIs
* database
* Redis
* object storage
* document ingestion
* parsing
* chunking
* embeddings
* vector storage
* retrieval
* reranking
* LLM integration
* agents
* workflows
* GraphRAG
* chat
* streaming
* citations
* frontend
* authentication
* authorization
* concurrency
* workers
* deployment
* testing

Do not assume that a component exists merely because a folder has a similar name.

Inspect actual source code and actual call relationships.

---

## 2. Inspect reverse-engineering documentation

Inspect:

/home/logan78/Desktop/devRAG/ragflow-docs

Use this material to understand the architecture that was previously reverse-engineered.

Classify important claims as:

OBSERVED
INFERRED
VERIFIED
UNKNOWN
CONTRADICTED

If the documentation conflicts with actual RAGFlow source code, prefer verified RAGFlow source behavior.

Do not invent behavior.

---

## 3. Inspect DevRAG

Recursively inspect:

/home/logan78/Desktop/devRAG

Inspect:

* .agents
* source
* tests
* configuration
* migrations
* Docker
* deployment
* frontend
* backend
* Python
* Go
* Redis
* storage
* vector database
* embeddings
* retrieval
* reranking
* agents
* graph execution
* LLM
* chat
* SSE
* citations

Determine what is actually implemented.

Do not trust previous implementation plans or completion claims without verifying the source.

---

## 4. Compare RAGFlow → DevRAG

For every important subsystem determine:

Reference behavior: <what RAGFlow actually does>

DevRAG behavior: <what DevRAG actually does>

Difference: <exact difference>

Impact: <why it matters>

Evidence:
<actual files/functions>

Classification:

MATCH
FUNCTIONALLY EQUIVALENT
PARTIAL
DIFFERENT
INCORRECT
MISSING
STUB
DEAD
UNKNOWN

---

## 5. Prioritize the core product path

Pay particular attention to:

Document upload
→ parsing
→ chunking
→ embedding
→ vector indexing
→ retrieval
→ reranking
→ agent graph
→ LLM
→ streaming
→ citations

Determine where DevRAG differs from RAGFlow.

---

## 6. Identify actual bugs

Find:

* broken integrations
* incorrect assumptions
* missing calls
* incorrect state transitions
* incorrect database behavior
* incorrect Redis behavior
* incorrect vector indexing
* retrieval differences
* graph execution bugs
* streaming bugs
* citation bugs
* authentication bugs
* authorization bugs
* concurrency problems
* dead code
* mocks accidentally used in production
* TODOs on production paths

---

## 7. Create the audit

Create:

fidelity/audit.md

The audit must contain:

1. RAGFlow architecture summary
2. DevRAG architecture summary
3. Architecture differences
4. Component comparison
5. Data-flow comparison
6. API comparison
7. Database comparison
8. Ingestion comparison
9. Retrieval comparison
10. Agent comparison
11. LLM comparison
12. Chat comparison
13. Citation comparison
14. Frontend comparison
15. Security comparison
16. Concurrency comparison
17. Testing comparison
18. Deployment comparison
19. Bugs
20. Missing functionality
21. Architectural deviations
22. Top-priority fixes

Create:

fidelity/gaps.md

with a prioritized list:

CRITICAL
HIGH
MEDIUM
LOW

For each gap include:

* ID
* problem
* RAGFlow behavior
* DevRAG behavior
* evidence
* impact
* likely root cause
* dependencies
* recommended fix

Create:

fidelity/progress.md

and record that the initial forensic audit has been completed.

---

## 8. NO CODE MODIFICATION

This iteration must NOT modify application source code.

Only create/update the fidelity audit documentation.

The purpose of this iteration is to establish an evidence-backed understanding of what must be fixed before autonomous implementation begins.

---

## 9. Final requirement

Do not merely say:

"DevRAG is similar to RAGFlow."

Produce concrete mappings between actual RAGFlow source and actual DevRAG source.

The output must make it possible for another engineer to begin fixing DevRAG without repeating the entire investigation.
