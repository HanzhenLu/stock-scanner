from datetime import datetime

from app.container import sse_manager
from app.container.analyzer import get_analyzer
from app.utils.sse_manager import StreamingSender
from app.services.ai_client import generate_ai_analysis
from app.utils.financial_utils import calculate_technical_score, calculate_technical_indicators, get_price_info, get_K_graph_table

def analyze_stock_streaming(stock_code, enable_streaming, client_id, position_percent:float=0, avg_price:float=-1):
    """流式股票分析"""
    streamer = StreamingSender(client_id, sse_manager)
    analyzer = get_analyzer()
    
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
        
        price_info = get_price_info(price_data)
        streamer.send_log(f"✓ 当前价格: {price_info['current_price']:5f}元", 'success')
        
        # 更新基本信息
        streamer.send_partial_result({
            'type': 'basic_info',
            'stock_code': stock_code,
            'stock_name': stock_name,
            'current_price': price_info['current_price'],
            'price_change': price_info['price_change']
        })
        
        streamer.send_progress('singleProgress', 25, "正在计算技术指标...")
        technical_analysis = calculate_technical_indicators(price_data)
        technical_score = calculate_technical_score(technical_analysis)
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
        
        # 执行AI分析，支持流式输出
        ai_analysis = generate_ai_analysis({
            'stock_code': stock_code,
            'stock_name': stock_name,
            'price_info': price_info,
            'technical_analysis': technical_analysis,
            'fundamental_data': fundamental_data,
            'sentiment_analysis': sentiment_analysis,
            'scores': scores,
            "k_graph_table": get_K_graph_table(price_data),
            "avg_price": avg_price,
            "position_percent": position_percent
        }, analyzer.config.generation, enable_streaming, streamer)
        
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
            'analysis_weights': analyzer.config.analysis_weights,
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
    streamer = StreamingSender(client_id, sse_manager)
    analyzer = get_analyzer()
    
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