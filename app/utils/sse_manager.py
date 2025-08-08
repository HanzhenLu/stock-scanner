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