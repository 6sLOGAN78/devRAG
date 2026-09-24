from quart import Blueprint, jsonify, g
from .auth_decorator import require_auth

ml_bp = Blueprint('ml', __name__)

@ml_bp.route('/health', methods=['GET', 'OPTIONS'])
async def health():
    return jsonify({"status": "ok"})

@ml_bp.route('/protected_info', methods=['GET'])
@require_auth
async def protected_info():
    return jsonify({
        "user_id": g.user_id,
        "tenant_id": g.tenant_id
    })

from quart import request
from api.services.parsing_service import parsing_service

@ml_bp.route('/parse_document', methods=['POST'])
async def parse_document():
    data = await request.get_json()
    if not data or 'task_id' not in data or 'document_id' not in data:
        return jsonify({"error": "Missing task_id or document_id"}), 400
    
    # Execute synchronously since it's dispatched by the Go worker and we expect to return 200 upon acceptance.
    # Wait, the Go Syncer expects to return 200 immediately, and the task executes in background?
    # Or does it block? The Go syncer runs `s.httpClient.Do(req)` and waits for response.
    # If parsing takes 2 minutes, Go Syncer blocks that goroutine (which is fine, it uses semaphore for bounded concurrency).
    # BUT, the HTTP client timeout in Go syncer is `10 * time.Second`.
    # Therefore, we MUST execute the parsing asynchronously, and return 200 immediately (Task Accepted).

    import asyncio
    asyncio.create_task(run_parsing_background(data['task_id'], data['document_id']))
    
    return jsonify({"status": "accepted", "task_id": data['task_id']}), 200

async def run_parsing_background(task_id: str, document_id: str):
    import asyncio
    # Run CPU/IO bound parsing in a separate thread to avoid blocking Quart event loop
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, parsing_service.process_task, task_id, document_id)

from rag.nlp.retrieval import RetrievalService
from api.services.indexing_service import indexing_service

@ml_bp.route('/retrieval', methods=['POST'])
@require_auth
async def retrieval():
    data = await request.get_json()
    if not data or 'query' not in data or 'dataset_ids' not in data:
        return jsonify({"error": "Missing query or dataset_ids"}), 400
        
    query = data['query']
    dataset_ids = data['dataset_ids']
    top_k = data.get('top_k', 10)
    similarity_threshold = data.get('similarity_threshold', 0.2)
    methods = data.get('methods', ['dense', 'lexical'])
    
    tenant_id = g.tenant_id
    
    retrieval_service = RetrievalService(indexing_service.vector_store)
    
    import asyncio
    loop = asyncio.get_event_loop()
    try:
        results = await loop.run_in_executor(
            None, 
            lambda: retrieval_service.search(
                tenant_id=tenant_id,
                query=query,
                dataset_ids=dataset_ids,
                top_k=top_k,
                similarity_threshold=similarity_threshold,
                methods=methods
            )
        )
        
        # Convert RetrievedChunk objects to dicts
        chunks = []
        for r in results:
            chunks.append({
                "chunk_id": r.chunk_id,
                "document_id": r.document_id,
                "dataset_id": r.dataset_id,
                "content": r.content,
                "score": r.score,
                "dense_rank": r.dense_rank,
                "lexical_rank": r.lexical_rank,
                "dense_score": r.dense_score,
                "lexical_score": r.lexical_score,
                "rerank_rank": r.rerank_rank,
                "rerank_score": r.rerank_score,
                "retrieval_method": r.retrieval_method,
                "metadata": r.metadata
            })
            
        return jsonify({"data": chunks}), 200
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500
