"""
Flask Web服务器 - SSE流式输出版
支持Server-Sent Events实时推送分析进度和结果
"""

from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for, Response
from flask_cors import CORS
import logging
import json
import threading
from datetime import datetime
import os
import sys
import math
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
import secrets
from queue import Queue, Empty

# 导入我们的分析器
try:
    from app.services.analyzer import WebStockAnalyzer
except ImportError:
    print("❌ 无法导入 web_stock_analyzer.py")
    print("请确保 web_stock_analyzer.py 文件存在于同一目录下")
    sys.exit(1)

# 创建Flask应用
app = Flask(__name__)
CORS(app)  # 允许跨域请求

# 高并发优化配置
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False
app.config['JSON_SORT_KEYS'] = False

# 生成随机的SECRET_KEY
app.secret_key = secrets.token_hex(32)

# 全局变量
analyzer = None
analysis_tasks = {}  # 存储分析任务状态
task_results = {}   # 存储任务结果
task_lock = threading.Lock()
sse_clients = {}    # 存储SSE客户端连接
sse_lock = threading.Lock()

# 线程池用于并发处理
executor = ThreadPoolExecutor(max_workers=4)

# 配置日志 - 只输出到命令行
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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

# 全局SSE管理器
sse_manager = SSEManager()

def clean_data_for_json(obj):
    """清理数据中的NaN、Infinity、日期等无效值，使其能够正确序列化为JSON"""
    import pandas as pd
    from datetime import datetime, date, time
    
    if isinstance(obj, dict):
        return {key: clean_data_for_json(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [clean_data_for_json(item) for item in obj]
    elif isinstance(obj, tuple):
        return [clean_data_for_json(item) for item in obj]
    elif isinstance(obj, (int, float)):
        if math.isnan(obj):
            return None
        elif math.isinf(obj):
            return None
        else:
            return obj
    elif isinstance(obj, np.ndarray):
        return clean_data_for_json(obj.tolist())
    elif isinstance(obj, (np.integer, np.floating)):
        if np.isnan(obj):
            return None
        elif np.isinf(obj):
            return None
        else:
            return obj.item()
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat() if hasattr(obj, 'isoformat') else str(obj)
    elif isinstance(obj, time):
        return obj.isoformat()
    elif isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    elif isinstance(obj, pd.NaT.__class__):
        return None
    elif pd.isna(obj):
        return None
    elif hasattr(obj, 'to_dict'):  # DataFrame或Series
        try:
            return clean_data_for_json(obj.to_dict())
        except:
            return str(obj)
    elif hasattr(obj, 'item'):  # numpy标量
        try:
            return clean_data_for_json(obj.item())
        except:
            return str(obj)
    elif obj is None:
        return None
    elif isinstance(obj, (str, bool)):
        return obj
    else:
        # 对于其他不可序列化的对象，转换为字符串
        try:
            # 尝试直接序列化测试
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)

def check_auth_config():
    """检查鉴权配置"""
    if not analyzer:
        return False, {}
    
    web_auth_config = analyzer.config.get('web_auth', {})
    return web_auth_config.get('enabled', False), web_auth_config

def require_auth(f):
    """鉴权装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_enabled, auth_config = check_auth_config()
        
        if not auth_enabled:
            return f(*args, **kwargs)
        
        # 检查session中是否已认证
        if session.get('authenticated'):
            # 检查session是否过期
            login_time = session.get('login_time')
            if login_time:
                session_timeout = auth_config.get('session_timeout', 3600)
                if (datetime.now() - datetime.fromisoformat(login_time)).total_seconds() < session_timeout:
                    return f(*args, **kwargs)
                else:
                    session.pop('authenticated', None)
                    session.pop('login_time', None)
        
        return redirect(url_for('login'))
    
    return decorated_function

def init_analyzer():
    """初始化分析器"""
    global analyzer
    try:
        logger.info("正在初始化WebStockAnalyzer...")
        analyzer = WebStockAnalyzer()
        logger.info("✅ WebStockAnalyzer初始化成功")
        return True
    except Exception as e:
        logger.error(f"❌ 分析器初始化失败: {e}")
        return False

@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面"""
    auth_enabled, auth_config = check_auth_config()
    current_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(current_dir, '..', 'templates', 'login.html')
    with open(template_path, 'r') as f:
        html_content = f.read()
    
    if not auth_enabled:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        config_password = auth_config.get('password', '')
        
        if not config_password:
            return render_template_string(html_content, 
                error="系统未设置访问密码，请联系管理员配置", 
                session_timeout=auth_config.get('session_timeout', 3600) // 60
            )
        
        if password == config_password:
            session['authenticated'] = True
            session['login_time'] = datetime.now().isoformat()
            logger.info("用户登录成功")
            return redirect(url_for('index'))
        else:
            logger.warning("用户登录失败：密码错误")
            return render_template_string(html_content, 
                error="密码错误，请重试", 
                session_timeout=auth_config.get('session_timeout', 3600) // 60
            )
    
    return render_template_string(html_content, 
        session_timeout=auth_config.get('session_timeout', 3600) // 60
    )

@app.route('/logout')
def logout():
    """退出登录"""
    session.pop('authenticated', None)
    session.pop('login_time', None)
    logger.info("用户退出登录")
    return redirect(url_for('login'))

@app.route('/')
@require_auth
def index():
    """主页"""
    auth_enabled, _ = check_auth_config()
    current_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(current_dir, '..', 'templates', 'main.html')
    with open(template_path, 'r') as f:
        html_content = f.read()
    return render_template_string(html_content, auth_enabled=auth_enabled)

@app.route('/api/sse')
@require_auth
def sse_stream():
    """SSE流接口"""
    client_id = request.args.get('client_id')
    if not client_id:
        return "Missing client_id", 400
    
    def event_stream():
        # 创建客户端队列
        client_queue = Queue()
        sse_manager.add_client(client_id, client_queue)
        
        try:
            # 发送连接确认
            yield f"data: {json.dumps({'event': 'connected', 'data': {'client_id': client_id}})}\n\n"
            
            while True:
                try:
                    # 获取消息（带超时，防止长时间阻塞）
                    message = client_queue.get(timeout=30)
                    
                    # 确保消息可以JSON序列化
                    try:
                        json_data = json.dumps(message, ensure_ascii=False)
                        yield f"data: {json_data}\n\n"
                    except (TypeError, ValueError) as e:
                        logger.error(f"SSE消息序列化失败: {e}, 消息类型: {type(message)}")
                        # 发送错误消息
                        error_message = {
                            'event': 'error',
                            'data': {'error': f'消息序列化失败: {str(e)}'},
                            'timestamp': datetime.now().isoformat()
                        }
                        yield f"data: {json.dumps(error_message)}\n\n"
                        
                except Empty:
                    # 发送心跳
                    yield f"data: {json.dumps({'event': 'heartbeat', 'data': {'timestamp': datetime.now().isoformat()}})}\n\n"
                except GeneratorExit:
                    break
                except Exception as e:
                    logger.error(f"SSE流处理错误: {e}")
                    try:
                        error_message = {
                            'event': 'error',
                            'data': {'error': f'流处理错误: {str(e)}'},
                            'timestamp': datetime.now().isoformat()
                        }
                        yield f"data: {json.dumps(error_message)}\n\n"
                    except:
                        pass
                    break
                    
        except Exception as e:
            logger.error(f"SSE流错误: {e}")
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

class StreamingAnalyzer:
    """流式分析器"""
    
    def __init__(self, client_id):
        self.client_id = client_id
    
    def send_log(self, message, log_type='info'):
        """发送日志消息"""
        sse_manager.send_to_client(self.client_id, 'log', {
            'message': message,
            'type': log_type
        })
    
    def send_progress(self, element_id, percent, message=None, current_stock=None):
        """发送进度更新"""
        sse_manager.send_to_client(self.client_id, 'progress', {
            'element_id': element_id,
            'percent': percent,
            'message': message,
            'current_stock': current_stock
        })
    
    def send_scores(self, scores, animate=True):
        """发送评分更新"""
        sse_manager.send_to_client(self.client_id, 'scores_update', {
            'scores': scores,
            'animate': animate
        })
    
    def send_data_quality(self, data_quality):
        """发送数据质量指标"""
        sse_manager.send_to_client(self.client_id, 'data_quality_update', data_quality)
    
    def send_partial_result(self, data):
        """发送部分结果"""
        cleaned_data = clean_data_for_json(data)
        sse_manager.send_to_client(self.client_id, 'partial_result', cleaned_data)
    
    def send_final_result(self, result):
        """发送最终结果"""
        cleaned_result = clean_data_for_json(result)
        sse_manager.send_to_client(self.client_id, 'final_result', cleaned_result)
    
    def send_batch_result(self, results):
        """发送批量结果"""
        cleaned_results = clean_data_for_json(results)
        sse_manager.send_to_client(self.client_id, 'batch_result', cleaned_results)
    
    def send_completion(self, message=None):
        """发送完成信号"""
        sse_manager.send_to_client(self.client_id, 'analysis_complete', {
            'message': message or '分析完成'
        })
    
    def send_error(self, error_message):
        """发送错误信息"""
        sse_manager.send_to_client(self.client_id, 'analysis_error', {
            'error': error_message
        })
    
    def send_ai_stream(self, content):
        """发送AI流式内容"""
        sse_manager.send_to_client(self.client_id, 'ai_stream', {
            'content': content
        })

def analyze_stock_streaming(stock_code, enable_streaming, client_id):
    """流式股票分析"""
    streamer = StreamingAnalyzer(client_id)
    
    try:
        streamer.send_log(f"🚀 开始流式分析股票: {stock_code}", 'header')
        streamer.send_progress('singleProgress', 5, "正在获取股票基本信息...")
        
        # 获取股票名称
        stock_name = analyzer.get_stock_name(stock_code)
        streamer.send_log(f"✓ 股票名称: {stock_name}", 'success')
        
        # 发送基本信息
        streamer.send_partial_result({
            'type': 'basic_info',
            'stock_code': stock_code,
            'stock_name': stock_name,
            'current_price': 0,
            'price_change': 0
        })
        
        # 1. 获取价格数据和技术分析
        streamer.send_progress('singleProgress', 15, "正在获取价格数据...")
        streamer.send_log("正在获取历史价格数据...", 'info')
        
        price_data = analyzer.get_stock_data(stock_code)
        if price_data.empty:
            raise ValueError(f"无法获取股票 {stock_code} 的价格数据")
        
        price_info = analyzer.get_price_info(price_data)
        streamer.send_log(f"✓ 当前价格: {price_info['current_price']:.2f}元", 'success')
        
        # 更新基本信息
        streamer.send_partial_result({
            'type': 'basic_info',
            'stock_code': stock_code,
            'stock_name': stock_name,
            'current_price': price_info['current_price'],
            'price_change': price_info['price_change']
        })
        
        streamer.send_progress('singleProgress', 25, "正在计算技术指标...")
        technical_analysis = analyzer.calculate_technical_indicators(price_data)
        technical_score = analyzer.calculate_technical_score(technical_analysis)
        streamer.send_log(f"✓ 技术分析完成，得分: {technical_score:.1f}", 'success')
        
        # 发送技术面得分
        streamer.send_scores({
            'technical': technical_score,
            'fundamental': 50,
            'sentiment': 50,
            'comprehensive': 50
        })
        
        # 2. 获取基本面数据
        streamer.send_progress('singleProgress', 45, "正在分析财务指标...")
        streamer.send_log("正在获取25项财务指标...", 'info')
        
        fundamental_data = analyzer.get_comprehensive_fundamental_data(stock_code)
        fundamental_score = analyzer.calculate_fundamental_score(fundamental_data)
        streamer.send_log(f"✓ 基本面分析完成，得分: {fundamental_score:.1f}", 'success')
        
        # 发送基本面得分
        streamer.send_scores({
            'technical': technical_score,
            'fundamental': fundamental_score,
            'sentiment': 50,
            'comprehensive': (technical_score + fundamental_score) / 2
        })
        
        # 3. 获取新闻和情绪分析
        streamer.send_progress('singleProgress', 65, "正在分析市场情绪...")
        streamer.send_log("正在获取新闻数据和分析市场情绪...", 'info')
        
        comprehensive_news_data = analyzer.get_comprehensive_news_data(stock_code, days=30)
        sentiment_analysis = analyzer.calculate_advanced_sentiment_analysis(comprehensive_news_data)
        sentiment_score = analyzer.calculate_sentiment_score(sentiment_analysis)
        streamer.send_log(f"✓ 情绪分析完成，得分: {sentiment_score:.1f}", 'success')
        
        # 合并新闻数据到情绪分析结果中
        sentiment_analysis.update(comprehensive_news_data)
        
        # 4. 计算综合得分
        scores = {
            'technical': technical_score,
            'fundamental': fundamental_score,
            'sentiment': sentiment_score,
            'comprehensive': analyzer.calculate_comprehensive_score({
                'technical': technical_score,
                'fundamental': fundamental_score,
                'sentiment': sentiment_score
            })
        }
        
        # 发送最终得分
        streamer.send_scores(scores, animate=True)
        
        # 发送数据质量指标
        data_quality = {
            'financial_indicators_count': len(fundamental_data.get('financial_indicators', {})),
            'total_news_count': sentiment_analysis.get('total_analyzed', 0),
            'analysis_completeness': '完整' if len(fundamental_data.get('financial_indicators', {})) >= 15 else '部分'
        }
        streamer.send_data_quality(data_quality)
        
        # 5. 生成投资建议
        streamer.send_progress('singleProgress', 80, "正在生成投资建议...")
        recommendation = analyzer.generate_recommendation(scores)
        streamer.send_log(f"✓ 投资建议: {recommendation}", 'success')
        
        # 6. AI增强分析（流式）
        streamer.send_progress('singleProgress', 90, "正在进行AI深度分析...")
        streamer.send_log("🤖 正在调用AI进行深度分析...", 'info')
        
        # 设置AI流式内容处理
        ai_content_buffer = ""
        
        def ai_stream_callback(content):
            """AI流式内容回调"""
            nonlocal ai_content_buffer
            ai_content_buffer += content
            # 实时发送AI流式内容
            streamer.send_ai_stream(content)
        
        # 执行AI分析，支持流式输出
        ai_analysis = analyzer.generate_ai_analysis({
            'stock_code': stock_code,
            'stock_name': stock_name,
            'price_info': price_info,
            'technical_analysis': technical_analysis,
            'fundamental_data': fundamental_data,
            'sentiment_analysis': sentiment_analysis,
            'scores': scores
        }, enable_streaming, ai_stream_callback)
        
        # 如果AI分析返回了完整内容，使用返回的内容，否则使用缓冲的内容
        if not ai_analysis and ai_content_buffer:
            ai_analysis = ai_content_buffer
        
        streamer.send_log("✅ AI深度分析完成", 'success')
        
        # 7. 生成最终报告
        streamer.send_progress('singleProgress', 100, "分析完成")
        
        report = {
            'stock_code': stock_code,
            'stock_name': stock_name,
            'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'price_info': price_info,
            'technical_analysis': technical_analysis,
            'fundamental_data': fundamental_data,
            'comprehensive_news_data': comprehensive_news_data,
            'sentiment_analysis': sentiment_analysis,
            'scores': scores,
            'analysis_weights': analyzer.analysis_weights,
            'recommendation': recommendation,
            'ai_analysis': ai_analysis,
            'data_quality': data_quality
        }
        
        # 发送最终结果
        streamer.send_final_result(report)
        streamer.send_completion(f"✅ {stock_code} 流式分析完成，综合得分: {scores['comprehensive']:.1f}")
        
        return report
        
    except Exception as e:
        error_msg = f"流式分析失败: {str(e)}"
        streamer.send_error(error_msg)
        streamer.send_log(f"❌ {error_msg}", 'error')
        raise

def analyze_batch_streaming(stock_codes, client_id):
    """流式批量股票分析"""
    streamer = StreamingAnalyzer(client_id)
    
    try:
        total_stocks = len(stock_codes)
        streamer.send_log(f"📊 开始流式批量分析 {total_stocks} 只股票", 'header')
        
        results = []
        failed_stocks = []
        
        for i, stock_code in enumerate(stock_codes):
            try:
                progress = int((i / total_stocks) * 100)
                streamer.send_progress('batchProgress', progress, 
                    f"正在分析第 {i+1}/{total_stocks} 只股票", stock_code)
                
                streamer.send_log(f"🔍 开始分析 {stock_code} ({i+1}/{total_stocks})", 'info')
                
                # 分析单只股票（简化版，不发送中间进度）
                report = analyzer.analyze_stock(stock_code, False)
                results.append(report)
                
                streamer.send_log(f"✓ {stock_code} 分析完成 (得分: {report['scores']['comprehensive']:.1f})", 'success')
                
            except Exception as e:
                failed_stocks.append(stock_code)
                streamer.send_log(f"❌ {stock_code} 分析失败: {e}", 'error')
        
        # 计算平均得分并发送
        if results:
            avg_scores = {
                'comprehensive': sum(r['scores']['comprehensive'] for r in results) / len(results),
                'technical': sum(r['scores']['technical'] for r in results) / len(results),
                'fundamental': sum(r['scores']['fundamental'] for r in results) / len(results),
                'sentiment': sum(r['scores']['sentiment'] for r in results) / len(results)
            }
            streamer.send_scores(avg_scores, animate=True)
            
            # 发送数据质量指标
            avg_financial = sum(r['data_quality']['financial_indicators_count'] for r in results) / len(results)
            avg_news = sum(r['sentiment_analysis']['total_analyzed'] for r in results) / len(results)
            
            streamer.send_data_quality({
                'financial_indicators_count': round(avg_financial),
                'total_news_count': round(avg_news),
                'analysis_completeness': '批量'
            })
        
        streamer.send_progress('batchProgress', 100, f"批量分析完成")
        
        # 发送批量结果
        streamer.send_batch_result(results)
        
        success_count = len(results)
        message = f"🎉 批量分析完成！成功分析 {success_count}/{total_stocks} 只股票"
        if failed_stocks:
            message += f"，失败: {', '.join(failed_stocks)}"
        
        streamer.send_completion(message)
        
        return results
        
    except Exception as e:
        error_msg = f"批量流式分析失败: {str(e)}"
        streamer.send_error(error_msg)
        streamer.send_log(f"❌ {error_msg}", 'error')
        raise

@app.route('/api/analyze_stream', methods=['POST'])
@require_auth
def analyze_stock_stream():
    """单只股票流式分析接口"""
    try:
        if not analyzer:
            return jsonify({
                'success': False,
                'error': '分析器未初始化'
            }), 500
        
        data = request.json
        stock_code = data.get('stock_code', '').strip()
        enable_streaming = data.get('enable_streaming', False)
        client_id = data.get('client_id')
        
        if not stock_code:
            return jsonify({
                'success': False,
                'error': '股票代码不能为空'
            }), 400
        
        if not client_id:
            return jsonify({
                'success': False,
                'error': '缺少客户端ID'
            }), 400
        
        # 检查是否有相同的分析正在进行
        with task_lock:
            if stock_code in analysis_tasks:
                return jsonify({
                    'success': False,
                    'error': f'股票 {stock_code} 正在分析中，请稍候'
                }), 429
            
            analysis_tasks[stock_code] = {
                'start_time': datetime.now(),
                'status': 'analyzing',
                'client_id': client_id
            }
        
        logger.info(f"开始流式分析股票: {stock_code}, 客户端: {client_id}")
        
        # 异步执行分析
        def run_analysis():
            try:
                global currentAnalysis
                report = analyze_stock_streaming(stock_code, enable_streaming, client_id)
                currentAnalysis = report
                logger.info(f"股票流式分析完成: {stock_code}")
            except Exception as e:
                logger.error(f"股票流式分析失败: {stock_code}, 错误: {e}")
            finally:
                with task_lock:
                    analysis_tasks.pop(stock_code, None)
        
        # 在线程池中执行
        executor.submit(run_analysis)
        
        return jsonify({
            'success': True,
            'message': f'股票 {stock_code} 流式分析已启动',
            'client_id': client_id
        })
        
    except Exception as e:
        logger.error(f"启动股票流式分析失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/batch_analyze_stream', methods=['POST'])
@require_auth
def batch_analyze_stream():
    """批量股票流式分析接口"""
    try:
        if not analyzer:
            return jsonify({
                'success': False,
                'error': '分析器未初始化'
            }), 500
        
        data = request.json
        stock_codes = data.get('stock_codes', [])
        client_id = data.get('client_id')
        
        if not stock_codes:
            return jsonify({
                'success': False,
                'error': '股票代码列表不能为空'
            }), 400
        
        if not client_id:
            return jsonify({
                'success': False,
                'error': '缺少客户端ID'
            }), 400
        
        # 限制批量分析数量
        if len(stock_codes) > 10:
            return jsonify({
                'success': False,
                'error': '批量分析最多支持10只股票'
            }), 400
        
        logger.info(f"开始流式批量分析 {len(stock_codes)} 只股票, 客户端: {client_id}")
        
        # 异步执行批量分析
        def run_batch_analysis():
            try:
                global currentAnalysis
                results = analyze_batch_streaming(stock_codes, client_id)
                currentAnalysis = results
                logger.info(f"批量流式分析完成，成功分析 {len(results)}/{len(stock_codes)} 只股票")
            except Exception as e:
                logger.error(f"批量流式分析失败: {e}")
        
        # 在线程池中执行
        executor.submit(run_batch_analysis)
        
        return jsonify({
            'success': True,
            'message': f'批量分析已启动，共 {len(stock_codes)} 只股票',
            'client_id': client_id
        })
        
    except Exception as e:
        logger.error(f"启动批量流式分析失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/status', methods=['GET'])
def status():
    """系统状态检查"""
    try:
        auth_enabled, auth_config = check_auth_config()
        return jsonify({
            'success': True,
            'status': 'ready',
            'message': 'Web股票分析系统运行正常 (SSE流式版)',
            'analyzer_available': analyzer is not None,
            'auth_enabled': auth_enabled,
            'sse_support': True,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/analyze', methods=['POST'])
@require_auth
def analyze_stock():
    """单只股票分析 - 兼容接口（非流式）"""
    try:
        if not analyzer:
            return jsonify({
                'success': False,
                'error': '分析器未初始化'
            }), 500
        
        data = request.json
        stock_code = data.get('stock_code', '').strip()
        enable_streaming = data.get('enable_streaming', False)
        
        if not stock_code:
            return jsonify({
                'success': False,
                'error': '股票代码不能为空'
            }), 400
        
        # 检查是否有相同的分析正在进行
        with task_lock:
            if stock_code in analysis_tasks:
                return jsonify({
                    'success': False,
                    'error': f'股票 {stock_code} 正在分析中，请稍候'
                }), 429
            
            analysis_tasks[stock_code] = {
                'start_time': datetime.now(),
                'status': 'analyzing'
            }
        
        logger.info(f"开始分析股票: {stock_code}")
        
        try:
            # 执行分析
            report = analyzer.analyze_stock(stock_code, enable_streaming)
            
            # 清理数据中的NaN值
            cleaned_report = clean_data_for_json(report)
            
            logger.info(f"股票分析完成: {stock_code}")
            
            return jsonify({
                'success': True,
                'data': cleaned_report,
                'message': f'股票 {stock_code} 分析完成'
            })
            
        finally:
            with task_lock:
                analysis_tasks.pop(stock_code, None)
        
    except Exception as e:
        with task_lock:
            analysis_tasks.pop(stock_code, None)
        
        logger.error(f"股票分析失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/batch_analyze', methods=['POST'])
@require_auth
def batch_analyze():
    """批量股票分析 - 兼容接口（非流式）"""
    try:
        if not analyzer:
            return jsonify({
                'success': False,
                'error': '分析器未初始化'
            }), 500
        
        data = request.json
        stock_codes = data.get('stock_codes', [])
        
        if not stock_codes:
            return jsonify({
                'success': False,
                'error': '股票代码列表不能为空'
            }), 400
        
        if len(stock_codes) > 10:
            return jsonify({
                'success': False,
                'error': '批量分析最多支持10只股票'
            }), 400
        
        logger.info(f"开始批量分析 {len(stock_codes)} 只股票")
        
        results = []
        failed_stocks = []
        
        # 使用线程池并发处理
        futures = {}
        for stock_code in stock_codes:
            future = executor.submit(analyzer.analyze_stock, stock_code, False)
            futures[future] = stock_code
        
        # 收集结果
        for future in futures:
            stock_code = futures[future]
            try:
                report = future.result(timeout=60)
                results.append(report)
                logger.info(f"✓ {stock_code} 分析完成")
            except Exception as e:
                failed_stocks.append(stock_code)
                logger.error(f"❌ {stock_code} 分析失败: {e}")
        
        # 清理数据中的NaN值
        cleaned_results = clean_data_for_json(results)
        
        success_count = len(results)
        total_count = len(stock_codes)
        
        logger.info(f"批量分析完成，成功分析 {success_count}/{total_count} 只股票")
        
        response_data = {
            'success': True,
            'data': cleaned_results,
            'message': f'批量分析完成，成功分析 {success_count}/{total_count} 只股票'
        }
        
        if failed_stocks:
            response_data['failed_stocks'] = failed_stocks
            response_data['message'] += f'，失败股票: {", ".join(failed_stocks)}'
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"批量分析失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/task_status/<stock_code>', methods=['GET'])
@require_auth
def get_task_status(stock_code):
    """获取分析任务状态"""
    try:
        with task_lock:
            task_info = analysis_tasks.get(stock_code)
            
        if not task_info:
            return jsonify({
                'success': True,
                'status': 'not_found',
                'message': f'未找到股票 {stock_code} 的分析任务'
            })
        
        # 计算分析时长
        elapsed_time = (datetime.now() - task_info['start_time']).total_seconds()
        
        return jsonify({
            'success': True,
            'status': task_info['status'],
            'elapsed_time': elapsed_time,
            'client_id': task_info.get('client_id'),
            'message': f'股票 {stock_code} 正在分析中'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/system_info', methods=['GET'])
def get_system_info():
    """获取系统信息"""
    try:
        with task_lock:
            active_tasks = len(analysis_tasks)
        
        with sse_lock:
            sse_clients_count = len(sse_manager.clients)
        
        # 检测配置的API
        configured_apis = []
        api_versions = {}
        
        if analyzer:
            for api_name, api_key in analyzer.api_keys.items():
                if api_name != 'notes' and api_key and api_key.strip():
                    configured_apis.append(api_name)
                    
                    # 检测API版本/状态
                    if api_name == 'openai':
                        try:
                            import openai
                            if hasattr(openai, 'OpenAI'):
                                api_versions[api_name] = "新版本"
                            else:
                                api_versions[api_name] = "旧版本"
                        except ImportError:
                            api_versions[api_name] = "未安装"
                    elif api_name == 'anthropic':
                        try:
                            import anthropic
                            api_versions[api_name] = "已安装"
                        except ImportError:
                            api_versions[api_name] = "未安装"
                    elif api_name == 'zhipu':
                        try:
                            import zhipuai
                            api_versions[api_name] = "已安装"
                        except ImportError:
                            api_versions[api_name] = "未安装"
        
        # 检测鉴权状态
        auth_enabled, auth_config = check_auth_config()
        
        return jsonify({
            'success': True,
            'data': {
                'analyzer_available': analyzer is not None,
                'active_tasks': active_tasks,
                'max_workers': executor._max_workers,
                'sse_clients': sse_clients_count,
                'sse_support': True,
                'configured_apis': configured_apis,
                'api_versions': api_versions,
                'api_configured': len(configured_apis) > 0,
                'primary_api': analyzer.config.get('ai', {}).get('model_preference', 'openai') if analyzer else None,
                'auth_enabled': auth_enabled,
                'auth_configured': auth_config.get('password', '') != '',
                'version': 'Enhanced v3.0-Web-SSE',
                'timestamp': datetime.now().isoformat()
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': '接口不存在'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'error': '服务器内部错误'
    }), 500

def main():
    """主函数"""
    print("🚀 启动Web版现代股票分析系统（SSE流式版）...")
    print("🌊 Server-Sent Events | 实时流式推送 | 完整LLM API支持")
    print("=" * 70)
    
    # 检查依赖
    missing_deps = []
    
    try:
        import akshare
        print("   ✅ akshare: 已安装")
    except ImportError:
        missing_deps.append("akshare")
        print("   ❌ akshare: 未安装")
    
    try:
        import pandas
        print("   ✅ pandas: 已安装")
    except ImportError:
        missing_deps.append("pandas")
        print("   ❌ pandas: 未安装")
    
    try:
        import flask
        print("   ✅ flask: 已安装")
    except ImportError:
        missing_deps.append("flask")
        print("   ❌ flask: 未安装")
    
    try:
        import flask_cors
        print("   ✅ flask-cors: 已安装")
    except ImportError:
        missing_deps.append("flask-cors")
        print("   ❌ flask-cors: 未安装")
    
    # 检查AI依赖
    ai_deps = []
    try:
        import openai
        if hasattr(openai, 'OpenAI'):
            ai_deps.append("OpenAI (新版)")
        else:
            ai_deps.append("OpenAI (旧版)")
    except ImportError:
        pass
    
    try:
        import anthropic
        ai_deps.append("Claude")
    except ImportError:
        pass
    
    try:
        import zhipuai
        ai_deps.append("智谱AI")
    except ImportError:
        pass
    
    if ai_deps:
        print(f"   🤖 AI支持: {', '.join(ai_deps)}")
    else:
        print("   ⚠️  AI依赖: 未安装 (pip install openai anthropic zhipuai)")
    
    # 检查配置文件
    if os.path.exists('config.json'):
        print("   ✅ config.json: 已存在")
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
                api_keys = config.get('api_keys', {})
                configured_apis = [name for name, key in api_keys.items() 
                                 if name != 'notes' and key and key.strip()]
                if configured_apis:
                    print(f"   🔑 已配置API: {', '.join(configured_apis)}")
                else:
                    print("   ⚠️  API密钥: 未配置")
                
                # 检查Web鉴权配置
                web_auth = config.get('web_auth', {})
                if web_auth.get('enabled', False):
                    if web_auth.get('password'):
                        print(f"   🔐 Web鉴权: 已启用 (会话超时: {web_auth.get('session_timeout', 3600)}秒)")
                    else:
                        print("   ⚠️  Web鉴权: 已启用但未设置密码")
                else:
                    print("   🔓 Web鉴权: 未启用")
                    
        except Exception as e:
            print(f"   ❌ config.json: 格式错误 - {e}")
    else:
        print("   ⚠️  config.json: 不存在，将使用默认配置")
    
    if missing_deps:
        print(f"❌ 缺少必要依赖: {', '.join(missing_deps)}")
        print(f"请运行以下命令安装: pip install {' '.join(missing_deps)}")
        return
    
    print("=" * 70)
    
    # 初始化分析器
    if not init_analyzer():
        print("❌ 分析器初始化失败，程序退出")
        return
    
    print("✅ 系统初始化完成！")
    print("🌊 SSE流式特性:")
    print("   - Server-Sent Events: 支持")
    print("   - 实时进度推送: 启用")
    print("   - 动态结果更新: 启用")
    print("   - 客户端连接管理: 自动化")
    print("   - 断线重连: 自动")
    print("   - 心跳检测: 启用")
    
    print("🔥 高并发特性:")
    print(f"   - 线程池: {executor._max_workers} 个工作线程")
    print("   - 异步分析: 支持")
    print("   - 任务队列: 支持")
    print("   - 重复请求防护: 启用")
    print("   - 批量并发优化: 启用")
    print("   - SSE连接池: 支持")
    
    print("🔐 安全特性:")
    if analyzer:
        web_auth = analyzer.config.get('web_auth', {})
        if web_auth.get('enabled', False):
            if web_auth.get('password'):
                timeout_minutes = web_auth.get('session_timeout', 3600) // 60
                print(f"   - 密码鉴权: 已启用")
                print(f"   - 会话超时: {timeout_minutes} 分钟")
                print(f"   - 安全状态: 保护模式")
            else:
                print("   - 密码鉴权: 已启用但未设置密码")
                print("   - 安全状态: 配置不完整")
        else:
            print("   - 密码鉴权: 未启用")
            print("   - 安全状态: 开放模式")
    else:
        print("   - 鉴权配置: 无法检测")
    
    print("🤖 AI分析特性:")
    if analyzer:
        api_keys = analyzer.api_keys
        configured_apis = [name for name, key in api_keys.items() 
                          if name != 'notes' and key and key.strip()]
        if configured_apis:
            print(f"   - 已配置API: {', '.join(configured_apis)}")
            primary_api = analyzer.config.get('ai', {}).get('model_preference', 'openai')
            print(f"   - 主要API: {primary_api}")
            
            api_base = analyzer.config.get('ai', {}).get('api_base_urls', {}).get('openai')
            if api_base and api_base != 'https://api.openai.com/v1':
                print(f"   - 自定义API地址: {api_base}")
            
            model = analyzer.config.get('ai', {}).get('models', {}).get(primary_api, 'default')
            print(f"   - 使用模型: {model}")
            
            print("   - LLM深度分析: 完整支持")
            print("   - 流式AI推理: 支持")
        else:
            print("   - API配置: 未配置")
            print("   - 分析模式: 高级规则分析")
    else:
        print("   - 分析器: 未初始化")
    
    print("   - 多模型支持: OpenAI/Claude/智谱AI")
    print("   - 智能切换: 启用")
    print("   - 版本兼容: 新旧版本自动适配")
    print("   - 规则分析备用: 启用")
    
    print("📋 分析配置:")
    if analyzer:
        params = analyzer.analysis_params
        weights = analyzer.analysis_weights
        print(f"   - 技术分析周期: {params.get('technical_period_days', 180)} 天")
        print(f"   - 财务指标数量: {params.get('financial_indicators_count', 25)} 项")
        print(f"   - 新闻分析数量: {params.get('max_news_count', 100)} 条")
        print(f"   - 分析权重: 技术{weights['technical']:.1f} | 基本面{weights['fundamental']:.1f} | 情绪{weights['sentiment']:.1f}")
    else:
        print("   - 配置: 使用默认值")
    
    print("📋 性能优化:")
    print("   - 日志文件: 已禁用")
    print("   - JSON压缩: 启用")
    print("   - 缓存优化: 启用")
    print("   - NaN值清理: 启用")
    print("   - SSE消息队列: 启用")
    
    print("🌐 Web服务器启动中...")
    print("📱 请在浏览器中访问: http://localhost:5000")
    
    if analyzer and analyzer.config.get('web_auth', {}).get('enabled', False):
        print("🔐 首次访问需要密码验证")
    
    print("🔧 API接口文档:")
    print("   - GET  /api/status - 系统状态")
    print("   - GET  /api/sse?client_id=xxx - SSE流式接口")
    print("   - POST /api/analyze_stream - 单只股票流式分析")
    print("   - POST /api/batch_analyze_stream - 批量股票流式分析")
    print("   - POST /api/analyze - 单只股票分析 (兼容)")
    print("   - POST /api/batch_analyze - 批量股票分析 (兼容)")
    print("   - GET  /api/task_status/<code> - 任务状态")
    print("   - GET  /api/system_info - 系统信息")
    print("   - GET  /login - 登录页面 (如启用鉴权)")
    print("   - GET  /logout - 退出登录")
    print("🌊 SSE事件类型:")
    print("   - connected: 连接确认")
    print("   - log: 日志消息")
    print("   - progress: 进度更新")
    print("   - scores_update: 评分更新")
    print("   - data_quality_update: 数据质量更新")
    print("   - partial_result: 部分结果")
    print("   - final_result: 最终结果")
    print("   - batch_result: 批量结果")
    print("   - analysis_complete: 分析完成")
    print("   - analysis_error: 分析错误")
    print("   - heartbeat: 心跳")
    print("=" * 70)
    
    # 启动Flask服务器
    try:
        app.run(
            host='0.0.0.0',
            port=5000,
            debug=False,
            threaded=True,
            use_reloader=False,
            processes=1
        )
    except KeyboardInterrupt:
        print("\n👋 系统已关闭")
        executor.shutdown(wait=True)
    except Exception as e:
        print(f"❌ 服务器启动失败: {e}")
        executor.shutdown(wait=True)

if __name__ == '__main__':
    main()