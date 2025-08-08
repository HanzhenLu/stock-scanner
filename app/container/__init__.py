from app.utils.sse_manager import SSEManager
from app.utils.analysis_manager import AnalysisManager
from concurrent.futures import ThreadPoolExecutor

sse_manager = SSEManager()
analysis_manager = AnalysisManager()
executor = ThreadPoolExecutor(max_workers=4)