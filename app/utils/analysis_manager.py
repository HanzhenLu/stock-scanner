import threading
from datetime import datetime

class AnalysisManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.tasks = {}

    def add_task(self, stock_code:str, client_id:str) -> bool:
        with self.lock:
            if stock_code in self.tasks:
                return False  # 已存在
            self.tasks[stock_code] = {
                'start_time': datetime.now(),
                'status': 'analyzing',
                'client_id': client_id
            }
            return True

    def remove_task(self, stock_code):
        with self.lock:
            self.tasks.pop(stock_code, None)

    def is_task_running(self, stock_code):
        with self.lock:
            return stock_code in self.tasks
        
    def __len__(self):
        with self.lock:
            return len(self.tasks.keys())

