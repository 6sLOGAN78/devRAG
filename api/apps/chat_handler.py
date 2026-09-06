import json
import uuid
import datetime
import asyncio
import logging
from quart import Blueprint, request, jsonify, g, make_response
from api.apps.auth_decorator import require_auth
from api.db.db_models import ChatSession, ChatMessage, AgentCanvas
from agent.graph import AgentGraph
from agent.runner import GraphRunner

logger = logging.getLogger(__name__)

chat_bp = Blueprint('chat', __name__)

def extract_citations(state) -> list:
    """Extracts citations/chunks from any Retrieval node in the execution state."""
    citations = []
    if hasattr(state, '_outputs'):
        for node_id, output in state._outputs.items():
            if isinstance(output, dict) and "chunks" in output:
                citations.extend(output["chunks"])
    return citations

@chat_bp.route('/completions', methods=['POST'])
@require_auth
async def chat_completions():
    body = await request.get_json()
    session_id = body.get('session_id')
    message = body.get('message')

    if not session_id or not message:
        return jsonify({"error": "Missing session_id or message"}), 400

    # Validate session and ownership
    try:
        session = ChatSession.get(
            (ChatSession.id == session_id) & 
            (ChatSession.user_id == g.user_id) & 
            (ChatSession.tenant_id == g.tenant_id)
        )
    except ChatSession.DoesNotExist:
        return jsonify({"error": "Session not found or unauthorized"}), 404

    # Validate agent canvas
    try:
        canvas = AgentCanvas.get(
            (AgentCanvas.id == session.agent_id) &
            (AgentCanvas.tenant_id == g.tenant_id)
        )
    except AgentCanvas.DoesNotExist:
        return jsonify({"error": "Agent canvas not found or unauthorized"}), 404

    # Load graph definition
    try:
        graph_def = json.loads(canvas.graph_definition)
        agent_graph = AgentGraph(graph_def)
    except Exception as e:
        return jsonify({"error": f"Invalid graph definition: {str(e)}"}), 400

    # Persist user message immediately before execution
    user_msg_id = str(uuid.uuid4())
    ChatMessage.create(
        id=user_msg_id,
        session_id=session.id,
        tenant_id=g.tenant_id,
        role="user",
        content=message
    )

    # We need to fetch chat history to pass to the graph, if needed by the nodes
    history = []
    messages = list(ChatMessage.select().where(
        (ChatMessage.session_id == session.id) & 
        (ChatMessage.tenant_id == g.tenant_id)
    ).order_by(ChatMessage.created_at.asc()))
    
    for msg in messages:
        history.append({"role": msg.role, "content": msg.content})

    queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def stream_callback(token: str):
        # Push token to the queue safely from a synchronous worker thread
        asyncio.run_coroutine_threadsafe(queue.put({"type": "token", "content": token}), loop)

    initial_inputs = {
        "query": message,
        "session_id": session.id,
        "history": history,
        "__stream_callback__": stream_callback
    }

    tenant_id = g.tenant_id
    async def run_graph():
        runner = GraphRunner(tenant_id=tenant_id)
        try:
            result = await asyncio.to_thread(runner.run, agent_graph, initial_inputs)
            await queue.put({"type": "done", "result": result})
        except Exception as e:
            await queue.put({"type": "error", "error": str(e)})

    # Start graph execution task in background
    execution_task = asyncio.create_task(run_graph())

    async def event_generator():
        accumulated_text = ""
        try:
            while True:
                item = await queue.get()
                
                if item["type"] == "token":
                    token = item["content"]
                    accumulated_text += token
                    # Format as SSE
                    data_json = json.dumps({"text": token})
                    yield f"data: {data_json}\n\n"
                    
                elif item["type"] == "done":
                    result = item["result"]
                    if result.status == "success":
                        # Attempt to extract citations if available
                        citations = extract_citations(result.state)
                        citations_str = json.dumps(citations) if citations else None
                        
                        yield "data: [DONE]\n\n"
                        
                        # Persist finalized assistant message
                        ChatMessage.create(
                            id=str(uuid.uuid4()),
                            session_id=session.id,
                            tenant_id=g.tenant_id,
                            role="assistant",
                            content=accumulated_text,
                            citations=citations_str
                        )
                    else:
                        error_json = json.dumps({"error": "Graph execution failed", "details": str(result.error)})
                        yield f"data: {error_json}\n\n"
                    break
                    
                elif item["type"] == "error":
                    error_json = json.dumps({"error": "Graph runner error", "details": item["error"]})
                    yield f"data: {error_json}\n\n"
                    break
                    
        except asyncio.CancelledError:
            logger.warning(f"Client disconnected during SSE for session {session.id}. Cancelling execution.")
            execution_task.cancel()
            raise

    response = await make_response(
        event_generator(),
        {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )
    response.timeout = None
    return response
