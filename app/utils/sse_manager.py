import threading
from datetime import datetime

from app.logger import logger
from app.utils.format_utils import clean_data_for_json

class SSEManager:
    """SSE连接管理器"""
    
    def __init__(self):
        self.clients = {}
        self.lock = threading.Lock()
    
    def add_client(self, client_id, queue):
        """添加SSE客户端"""
        with self.lock:
            self.clients[client_id] = queue
            logger.info(f"SSE客户端连接: {client_id}")
    
    def remove_client(self, client_id):
        """移除SSE客户端"""
        with self.lock:
            if client_id in self.clients:
                del self.clients[client_id]
                logger.info(f"SSE客户端断开: {client_id}")
    
    def send_to_client(self, client_id, event_type, data):
        """向特定客户端发送消息"""
        with self.lock:
            if client_id in self.clients:
                try:
                    # 清理数据确保JSON可序列化
                    cleaned_data = clean_data_for_json(data)
                    message = {
                        'event': event_type,
                        'data': cleaned_data,
                        'timestamp': datetime.now().isoformat()
                    }
                    self.clients[client_id].put(message, block=False)
                    return True
                except Exception as e:
                    logger.error(f"SSE消息发送失败: {e}")
                    return False
            return False
    
    def broadcast(self, event_type, data):
        """广播消息给所有客户端"""
        with self.lock:
            # 清理数据确保JSON可序列化
            cleaned_data = clean_data_for_json(data)
            message = {
                'event': event_type,
                'data': cleaned_data,
                'timestamp': datetime.now().isoformat()
            }
            
            dead_clients = []
            for client_id, queue in self.clients.items():
                try:
                    queue.put(message, block=False)
                except Exception as e:
                    logger.error(f"SSE广播失败给客户端 {client_id}: {e}")
                    dead_clients.append(client_id)
            
            # 清理死连接
            for client_id in dead_clients:
                del self.clients[client_id]
                
    def __len__(self):
        with self.lock:
            return len(self.clients)
        
class StreamingSender:
    """流式分析器"""
    
    def __init__(self, client_id, sse_manager:SSEManager):
        self.client_id = client_id
        self.sse_manager = sse_manager
    
    def send_log(self, message, log_type='info'):
        """发送日志消息"""
        self.sse_manager.send_to_client(self.client_id, 'log', {
            'message': message,
            'type': log_type
        })
    
    def send_progress(self, element_id, percent, message=None, current_stock=None):
        """发送进度更新"""
        self.sse_manager.send_to_client(self.client_id, 'progress', {
            'element_id': element_id,
            'percent': percent,
            'message': message,
            'current_stock': current_stock
        })
    
    def send_scores(self, scores, animate=True):
        """发送评分更新"""
        self.sse_manager.send_to_client(self.client_id, 'scores_update', {
            'scores': scores,
            'animate': animate
        })
    
    def send_data_quality(self, data_quality):
        """发送数据质量指标"""
        self.sse_manager.send_to_client(self.client_id, 'data_quality_update', data_quality)
    
    def send_partial_result(self, data):
        """发送部分结果"""
        cleaned_data = clean_data_for_json(data)
        self.sse_manager.send_to_client(self.client_id, 'partial_result', cleaned_data)
    
    def send_final_result(self, result):
        """发送最终结果"""
        cleaned_result = clean_data_for_json(result)
        self.sse_manager.send_to_client(self.client_id, 'final_result', cleaned_result)
    
    def send_batch_result(self, results):
        """发送批量结果"""
        cleaned_results = clean_data_for_json(results)
        self.sse_manager.send_to_client(self.client_id, 'batch_result', cleaned_results)
    
    def send_completion(self, message=None):
        """发送完成信号"""
        self.sse_manager.send_to_client(self.client_id, 'analysis_complete', {
            'message': message or '分析完成'
        })
    
    def send_error(self, error_message):
        """发送错误信息"""
        self.sse_manager.send_to_client(self.client_id, 'analysis_error', {
            'error': error_message
        })
    
    def send_ai_stream(self, content):
        """发送AI流式内容"""
        self.sse_manager.send_to_client(self.client_id, 'ai_stream', {
            'content': content
        })
        
    def send_prompt(self, prompt:str):
        self.sse_manager.send_to_client(self.client_id, 'ai_prompt', {
            'content': prompt
        })