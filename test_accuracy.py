import logging
from rag.nlp.rerank import RerankEngine, RerankConfig
from sentence_transformers import CrossEncoder

logging.basicConfig(level=logging.INFO)

def run_benchmark():
    config = RerankConfig(
        provider="huggingface",
        model="cross-encoder/ms-marco-MiniLM-L-6-v2"
    )
    engine = RerankEngine(config)
    
    query = "How is update_progress protected from concurrent writes?"
    
    candidates = [
        "Workers update progress using RedisDistributedLock('update_progress').",
        "Workers update progress after parsing.",
        "Redis is used for distributed caching.",
        "Task execution uses background worker threads."
    ]
    
    print(f"Query: {query}")
    print("Candidates (Initial Retrieval Order):")
    for i, c in enumerate(candidates):
        print(f" {i+1}. {c}")
        
    scores = engine.rerank_scores(query, candidates)
    
    scored_candidates = list(zip(candidates, scores))
    scored_candidates.sort(key=lambda x: x[1], reverse=True)
    
    print("\nCandidates (Reranked Order):")
    for i, (c, s) in enumerate(scored_candidates):
        print(f" {i+1}. [Score: {s:.4f}] {c}")
        if i == 0 and "RedisDistributedLock" in c:
            print(" -> PASS: Reranker correctly placed the exact technical match at Rank 1.")
        elif i == 0:
            print(" -> FAIL: Reranker missed the exact match.")

if __name__ == "__main__":
    run_benchmark()
