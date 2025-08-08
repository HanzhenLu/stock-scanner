from app.services.streaming_analyzer import analyze_stock_streaming, analyze_batch_streaming
from app.utils.decorators import require_auth
from app.logger import logger
from app.container.analyzer import get_analyzer
from app.container import analysis_manager, executor

from flask import Blueprint, request, jsonify

analyzer_bp = Blueprint('analyze', __name__)

@analyzer_bp.route('/streaming', methods=['POST'])
@require_auth
def analyze_stock_stream():
    """单只股票流式分析接口"""

    analyzer = get_analyzer()
    
    try:
        if not analyzer:
            return jsonify({'success': False, 'error': '分析器未初始化'}), 500

        data = request.json
        stock_code = data.get('stock_code', '').strip()
        enable_streaming = data.get('enable_streaming', False)
        client_id = data.get('client_id')

        if not stock_code:
            return jsonify({'success': False, 'error': '股票代码不能为空'}), 400

        if not client_id:
            return jsonify({'success': False, 'error': '缺少客户端ID'}), 400

        # TODO 这里虽然显示了请稍后，但是分析完成后可能不会推送给对应的用户
        if not analysis_manager.add_task(stock_code, client_id):
            return jsonify({
                'success': False,
                'error': f'股票 {stock_code} 正在分析中，请稍候'
            }), 429

        logger.info(f"开始流式分析股票: {stock_code}, 客户端: {client_id}")

        def run_analysis():
            try:
                analyze_stock_streaming(stock_code, enable_streaming, client_id)
                logger.info(f"股票流式分析完成: {stock_code}")
            except Exception as e:
                logger.error(f"股票流式分析失败: {stock_code}, 错误: {e}")
            finally:
                analysis_manager.remove_task(stock_code)

        executor.submit(run_analysis)

        return jsonify({
            'success': True,
            'message': f'股票 {stock_code} 流式分析已启动',
            'client_id': client_id
        })

    except Exception as e:
        logger.error(f"启动股票流式分析失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@analyzer_bp.route('/batch_streaming', methods=['POST'])
@require_auth
def batch_analyze_stream():
    """批量股票流式分析接口"""
    analyzer = get_analyzer()
    
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