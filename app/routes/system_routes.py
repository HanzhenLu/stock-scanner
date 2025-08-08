from flask import Blueprint, jsonify
from datetime import datetime

from app.container.analyzer import get_analyzer
from app.container import sse_manager, analysis_manager, executor

status_bp = Blueprint('status', __name__)

@status_bp.route('/', methods=['GET'])
def status():
    """系统状态检查"""
    try:
        analyzer = get_analyzer()
        auth_enabled = analyzer.config.web_auth.enabled
        
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

@status_bp.route('/system_info', methods=['GET'])
def get_system_info():
    """获取系统信息"""
    try:
        active_tasks = len(analysis_manager)
        sse_clients_count = len(sse_manager)
        analyzer = get_analyzer()
        
        # 检测鉴权状态
        auth_enabled = analyzer.config.web_auth.enabled 
        auth_config = analyzer.config.web_auth
        
        return jsonify({
            'success': True,
            'data': {
                'analyzer_available': analyzer is not None,
                'active_tasks': active_tasks,
                'max_workers': executor._max_workers,
                'sse_clients': sse_clients_count,
                'sse_support': True,
                'primary_api': f"{analyzer.config.generation.server_name} : {analyzer.config.generation.model_name}",
                'auth_enabled': auth_enabled,
                'auth_configured': auth_config.password != '',
                'version': 'Enhanced v3.0-Web-SSE',
                'timestamp': datetime.now().isoformat()
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500