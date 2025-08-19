from flask import Blueprint, Response, request
from datetime import datetime
from queue import Empty, Queue
import json
from app.utils.decorators import require_auth
from app.logger import logger
from app.container import sse_manager

sse_bp = Blueprint('sse', __name__)

@sse_bp.route('/stream')
@require_auth
def sse_stream():
    client_id = request.args.get('client_id')
    if not client_id:
        return "Missing client_id", 400

    def event_stream():
        client_queue = Queue()
        sse_manager.add_client(client_id, client_queue)

        try:
            yield f"data: {json.dumps({'event': 'connected', 'data': {'client_id': client_id}})}\n\n"
            while True:
                try:
                    message = client_queue.get(timeout=30)
                    try:
                        json_data = json.dumps(message, ensure_ascii=False)
                        yield f"data: {json_data}\n\n"
                    except (TypeError, ValueError) as e:
                        logger.error(f"SSE消息序列化失败: {e}")
                        yield f"data: {json.dumps({'event': 'error', 'data': {'error': str(e)}})}\n\n"
                except Empty:
                    yield f"data: {json.dumps({'event': 'heartbeat', 'data': {'timestamp': datetime.now().isoformat()}})}\n\n"
                except GeneratorExit:
                    break
                except Exception as e:
                    logger.error(f"SSE流处理错误: {e}")
                    yield f"data: {json.dumps({'event': 'error', 'data': {'error': str(e)}})}\n\n"
                    break
        finally:
            sse_manager.remove_client(client_id)

    return Response(
        event_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*',
        }
    )
