import importlib

from app.container.analyzer import set_analyzer, get_analyzer
from app.services.analyzer import init_analyzer
from app import create_app

def main():
    """主函数"""
    print("🚀 启动Web版现代股票分析系统...")
    print("🌊 Server-Sent Events | 实时流式推送 | 完整LLM API支持")
    print("=" * 70)
    
    # 检查依赖
    missing_deps = []
    
    required_deps = [
        "akshare",
        "pandas",
        "flask",
        "flask_cors",
        "openai",
        "anthropic",
        "zhipuai"
    ]
    
    for dep in required_deps:
        try:
            importlib.import_module(dep)
        except ImportError:
            missing_deps.append(dep)
            print(f"{dep} not installed")
            
    if missing_deps:
        print(f"❌ 缺少必要依赖: {', '.join(missing_deps)}")
        print(f"请运行以下命令安装: pip install {' '.join(missing_deps)}")
        return
    
    print("=" * 70)
    
    # 初始化分析器
    set_analyzer(init_analyzer("config.json"))
    analyzer = get_analyzer()
    if not analyzer:
        print("❌ 分析器初始化失败，程序退出")
        return
    
    print("🔐 安全特性:")
    if analyzer:
        if analyzer.config.web_auth.enabled:
            if analyzer.config.web_auth.password:
                timeout_minutes = analyzer.config.web_auth.session_timeout // 60
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
        print(f"   - API地址: {analyzer.config.generation.api_base_url}")
        print(f"   - 使用模型: {analyzer.config.generation.server_name}:{analyzer.config.generation.model_name}")
    else:
        print("   - 分析器: 未初始化")
    
    print("📋 分析配置:")
    if analyzer:
        print(f"   - 技术分析周期: {analyzer.config.analysis_params.technical_period_days} 天")
        print(f"   - 财务指标数量: {analyzer.config.analysis_params.financial_indicators_count} 项")
        print(f"   - 新闻分析数量: {analyzer.config.analysis_params.max_news_count} 条")
        print(f"   - 分析权重: 技术{analyzer.config.analysis_weights.technical:.2f} | 基本面{analyzer.config.analysis_weights.fundamental:.2f} | 情绪{analyzer.config.analysis_weights.sentiment:.2f}")
    else:
        print("   - 配置: 使用默认值")
    
    print("🌐 Web服务器启动中...")
    print("📱 请在浏览器中访问: http://localhost:5000")
    
    print("🌊 SSE事件类型:")
    print("   - connected: 连接确认")
    print("   - log: 日志消息")
    print("   - progress: 进度更新")
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
        app = create_app()
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
    except Exception as e:
        print(f"❌ 服务器启动失败: {e}")

if __name__ == "__main__":
    main()