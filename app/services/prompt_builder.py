from app.utils.format_utils import format_dict_data, format_list_data

MAX_LIST_ITEMS = 5

def _build_financial_section(financial_indicators: dict) -> str:
    if not financial_indicators:
        return ""
    
    lines = ["**核心财务指标：**"]
    for i, (key, value) in enumerate(financial_indicators.items(), 1):
        if isinstance(value, (int, float)) and value != -1:
            lines.append(f"{i}. {key}: {value}")
    return "\n".join(lines)

def _build_news_section(company_news: list, research_reports: list) -> str:
    news_text = [
        "**新闻数据详情：**",
        f"- 公司新闻：{len(company_news)}条",
        f"- 研究报告：{len(research_reports)}条",
        "",
        "**重要新闻标题：**"
    ]
    for i, news in enumerate(company_news, 1):
        news_text.append(f"{i}. {news['title']}")
    
    if research_reports:
        news_text.append("\n**研究报告标题：**")
        for i, report in enumerate(research_reports, 1):
            news_text.append(f"{i}. {report['institution']}: {report['rating']} - {report['title']}")
    
    return "\n".join(news_text)

def _get_analysis_instruction():
    return """**分析要求：**

请基于以上详细数据，从以下维度进行深度分析：

1. **财务健康度深度解读**：
- 基于财务指标，全面评估公司财务状况
- 识别财务优势和风险点
- 与行业平均水平对比分析
- 预测未来财务发展趋势

2. **技术面精准分析**：
- 结合多个技术指标，判断短中长期趋势
- 识别关键支撑位和阻力位
- 分析成交量与价格的配合关系
- 评估当前位置的风险收益比

3. **市场情绪深度挖掘**：
- 分析公司新闻、公告、研报的影响
- 评估市场对公司的整体预期
- 识别情绪拐点和催化剂
- 判断情绪对股价的推动或拖累作用

4. **基本面价值判断**：
- 评估公司内在价值和成长潜力
- 分析行业地位和竞争优势
- 评估业绩预告和分红政策
- 判断当前估值的合理性

5. **综合投资策略**：
- 给出明确的买卖建议和理由
- 设定目标价位和止损点
- 制定分批操作策略
- 评估投资时间周期

6. **风险机会识别**：
- 列出主要投资风险和应对措施
- 识别潜在催化剂和成长机会
- 分析宏观环境和政策影响
- 提供动态调整建议

请用专业、客观的语言进行分析，确保逻辑清晰、数据支撑充分、结论明确可执行。"""


def build_enhanced_ai_analysis_prompt(
    stock_code: str, stock_name: str, scores: dict,
    technical_analysis: dict, fundamental_data: dict,
    sentiment_analysis: dict, price_info: dict
) -> str:

    financial_text = _build_financial_section(fundamental_data.get('financial_indicators', {}))
    news_text = _build_news_section(
        sentiment_analysis.get('company_news', []),
        sentiment_analysis.get('research_reports', [])
    )
    
    prompt = f"""请作为一位资深的股票分析师，基于以下详细数据对股票进行深度分析：

**股票基本信息：**
- 股票代码：{stock_code}
- 股票名称：{stock_name}
- 当前价格：{price_info.get('current_price', '未知'):2.2}元
- 涨跌幅：{price_info.get('price_change', '未知'):2.2}%
- 成交量比率：{price_info.get('volume_ratio', '未知'):2.2}
- 波动率：{price_info.get('volatility', '未知'):2.2}%

**技术分析详情：**
- 均线趋势：{technical_analysis.get('ma_trend', '未知')} ExpMA5:{technical_analysis.get('ma5', '未知'):5.5} ExpMA10:{technical_analysis.get('ma10', '未知'):5.5} ExpMA20:{technical_analysis.get('ma20', '未知'):5.5}
- RSI指标：{technical_analysis.get('rsi', '未知'):5.5}
- MACD信号：{technical_analysis.get('macd_signal', '未知')} dif:{technical_analysis.get('dif', '未知'):5.5} dea:{technical_analysis.get('dea', '未知'):5.5}
- 布林带位置：{technical_analysis.get('bb_position', '未知'):5.5}
- 成交量状态：{technical_analysis.get('volume_status', '未知')}

{financial_text}

**估值指标：**
{format_dict_data(fundamental_data.get('valuation', {}))}

**业绩预告：**
共{len(fundamental_data.get('performance_forecast', []))}条业绩预告
{format_list_data(fundamental_data.get('performance_forecast', [])[:MAX_LIST_ITEMS])}

**分红配股：**
共{len(fundamental_data.get('dividend_info', []))}条分红配股信息
{format_list_data(fundamental_data.get('dividend_info', [])[:MAX_LIST_ITEMS])}

{news_text}

{_get_analysis_instruction()}"""

    return prompt
