import pandas as pd
import akshare as ak
import math
import time
from datetime import datetime, timedelta

from app.logger import logger
from app.utils.config import load_config
from app.utils.financial_utils import (get_price_info, calculate_technical_indicators, get_K_graph_table)
from app.utils.sse_manager import StreamingSender
from app.container import sse_manager
from app.services.ai_client import generate_ai_analysis, news_summarize, k_graph_analysis, value_analyze
from app.services.prompt_builder import build_value_prompt

class WebStockAnalyzer:
    """Web版增强股票分析器"""
    
    def __init__(self, config_file='config.json'):
        """初始化分析器"""
        self.config_file = config_file
        
        # 加载配置文件
        self.config = load_config(self.config_file)
        
        # 缓存配置
        self.price_cache_duration = timedelta(hours=self.config.cache.price_hours)
        self.fundamental_cache_duration = timedelta(hours=self.config.cache.fundamental_hours)
        self.news_cache_duration = timedelta(hours=self.config.cache.news_hours)
        
        self.price_cache = {}
        self.fundamental_cache = {}
        self.news_cache = {}
        
        # 权重配置， 重新归一化
        weights_sum = self.config.analysis_weights.technical + self.config.analysis_weights.fundamental + self.config.analysis_weights.sentiment
        if weights_sum != 1:
            logger.info("重新归一化")
            self.config.analysis_weights.technical /= weights_sum
            self.config.analysis_weights.fundamental /= weights_sum
            self.config.analysis_weights.sentiment /= weights_sum
        
        logger.info("Web版股票分析器初始化完成")
        self._log_config_status()

    def _log_config_status(self):
        """记录配置状态"""
        logger.info("=== Web版系统配置状态===")
        
        # 检查AI状态
        logger.info(f"🤖 使用AI: {self.config.generation.server_name}:{self.config.generation.model_name}")
        logger.info(f"🎯 使用url: {self.config.generation.api_base_url}")
        
        if not self.config.generation.api_key:
            logger.warning("⚠️ 未提供api keys")
        
        logger.info(f"📊 财务指标数量: {self.config.analysis_params.financial_indicators_count}")
        logger.info(f"📰 最大新闻数量: {self.config.analysis_params.max_news_count}")
        logger.info(f"📈 技术分析周期: {self.config.analysis_params.technical_period_days} 天")
        
        # 检查Web鉴权配置
        if self.config.web_auth.enabled:
            logger.info(f"🔐 Web鉴权: 已启用")
        else:
            logger.info(f"🔓 Web鉴权: 未启用")
        
        logger.info("=" * 40)

    def get_stock_data(self, stock_code:str):
        """获取股票价格数据"""
        if stock_code in self.price_cache:
            cache_time, data = self.price_cache[stock_code]
            if datetime.now() - cache_time < self.price_cache_duration:
                logger.info(f"使用缓存的价格数据: {stock_code}")
                return data
        
        try:
            end_date = datetime.now().strftime('%Y%m%d')
            # 使用用户配置的技术分析周期
            days = self.config.analysis_params.technical_period_days
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
            
            logger.info(f"正在获取 {stock_code} 的历史数据 (过去{days}天)...")
            
            stock_data = ak.stock_zh_a_hist(
                symbol=stock_code,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"
            )
            
            if stock_data.empty:
                raise ValueError(f"无法获取股票 {stock_code} 的数据")
            
            actual_columns = len(stock_data.columns)
            logger.info(f"获取到 {actual_columns} 列数据，列名: {list(stock_data.columns)}")
            
            # 根据实际返回的列数进行映射
            if actual_columns == 13:  # 包含code列的完整格式
                standard_columns = ['date', 'code', 'open', 'close', 'high', 'low', 'volume', 'turnover', 'amplitude', 'change_pct', 'change_amount', 'turnover_rate', 'extra']
            elif actual_columns == 12:  # 包含code列
                standard_columns = ['date', 'code', 'open', 'close', 'high', 'low', 'volume', 'turnover', 'amplitude', 'change_pct', 'change_amount', 'turnover_rate']
            elif actual_columns == 11:  # 不包含code列的标准格式
                standard_columns = ['date', 'open', 'close', 'high', 'low', 'volume', 'turnover', 'amplitude', 'change_pct', 'change_amount', 'turnover_rate']
            elif actual_columns == 10:  # 简化格式
                standard_columns = ['date', 'open', 'close', 'high', 'low', 'volume', 'turnover', 'amplitude', 'change_pct', 'change_amount']
            else:
                raise ValueError(f"股票 {stock_code} 获取数据格式错误 列数仅有 {actual_columns}")
            
            # 创建列名映射
            column_mapping = dict(zip(stock_data.columns, standard_columns))
            stock_data = stock_data.rename(columns=column_mapping)
            
            logger.info(f"列名映射完成: {column_mapping}")
            
            # 处理日期列
            try:
                stock_data['date'] = pd.to_datetime(stock_data['date'])
                stock_data = stock_data.set_index('date')
            except Exception as e:
                logger.warning(f"日期处理失败: {e}")
            
            # 确保数值列为数值类型
            numeric_columns = ['open', 'close', 'high', 'low', 'volume']
            for col in numeric_columns:
                if col in stock_data.columns:
                    try:
                        stock_data[col] = pd.to_numeric(stock_data[col], errors='coerce')
                    except:
                        pass
            
            # 验证数据质量
            if 'close' in stock_data.columns:
                latest_close = stock_data['close'].iloc[-1]
                latest_open = stock_data['open'].iloc[-1] if 'open' in stock_data.columns else 0
                logger.info(f"✓ 数据验证 - 最新收盘价: {latest_close}, 最新开盘价: {latest_open}")
                
                # 检查收盘价是否合理
                if pd.isna(latest_close) or latest_close <= 0:
                    logger.error(f"❌ 收盘价数据异常: {latest_close}")
                    raise ValueError(f"股票 {stock_code} 的收盘价数据异常")
            
            # 缓存数据
            self.price_cache[stock_code] = (datetime.now(), stock_data)
            
            logger.info(f"✓ 成功获取 {stock_code} 的价格数据，共 {len(stock_data)} 条记录")
            logger.info(f"✓ 数据列: {list(stock_data.columns)}")
            
            return stock_data
            
        except Exception as e:
            logger.error(f"获取股票数据失败: {str(e)}")
            return pd.DataFrame()

    def get_comprehensive_fundamental_data(self, stock_code:str) -> dict:
        """获取项综合财务指标数据"""
        if stock_code in self.fundamental_cache:
            cache_time, data = self.fundamental_cache[stock_code]
            if datetime.now() - cache_time < self.fundamental_cache_duration:
                logger.info(f"使用缓存的基本面数据: {stock_code}")
                return data
        
        current_time = datetime.today()
        
        try:
            fundamental_data = {}
            logger.info(f"开始获取 {stock_code} 的综合财务指标...")
            
            # 1. 基本信息
            try:
                logger.info("正在获取股票基本信息...")
                stock_info = ak.stock_individual_info_em(symbol=stock_code)
                info_dict = dict(zip(stock_info['item'], stock_info['value']))
                fundamental_data['basic_info'] = info_dict
                logger.info("✓ 股票基本信息获取成功")
            except Exception as e:
                logger.warning(f"获取基本信息失败: {e}")
                fundamental_data['basic_info'] = {}
            
            # 2. 详细财务指标 - 核心指标
            try:
                logger.info("正在获取详细财务指标...")
                
                # 获取财务分析指标
                financial_analysis_indicator = ak.stock_financial_analysis_indicator(symbol=stock_code, start_year=f"{current_time.year}")
                if not financial_analysis_indicator.empty:
                    latest_financial_analysis_indicator = financial_analysis_indicator.iloc[-1].to_dict()
                
                def safe_isnan(x):
                    try:
                        return math.isnan(x)
                    except:
                        return False
                
                fundamental_data['financial_indicators'] = {
                    k: v for k, v in latest_financial_analysis_indicator.items()
                    if v not in [0, None, 'nan', -1] and not safe_isnan(v)
                }
                logger.info(f"获取到{len(fundamental_data['financial_indicators'].keys())}条财务分析指标")
                
            except Exception as e:
                logger.warning(f"获取财务指标失败: {e}")
                fundamental_data['financial_indicators'] = {}
            
            # 3. 估值指标
            try:
                logger.info("正在获取估值指标...")
                valuation_data = ak.stock_value_em(symbol=stock_code)
                if not valuation_data.empty:
                    latest_valuation = valuation_data.iloc[-1].to_dict()
                    # 清理估值数据中的NaN值
                    cleaned_valuation = {}
                    for key, value in latest_valuation.items():
                        if pd.isna(value) or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
                            cleaned_valuation[key] = None
                        else:
                            cleaned_valuation[key] = value
                    fundamental_data['valuation'] = cleaned_valuation
                    logger.info("✓ 估值指标获取成功")
                else:
                    fundamental_data['valuation'] = {}
            except Exception as e:
                logger.warning(f"获取估值指标失败: {e}")
                fundamental_data['valuation'] = {}
            
            # 4. 业绩预告和业绩快报
            try:
                logger.info("正在获取业绩报表...")
                if current_time.month <= 3:
                    query_time = [f"{current_time.year-1}1231", f"{current_time.year-1}0930", f"{current_time.year-1}0630", f"{current_time.year-1}0331"]
                elif current_time.month <= 6:
                    query_time = [f"{current_time.year}0331", f"{current_time.year-1}1231", f"{current_time.year-1}0930", f"{current_time.year-1}0630"]
                elif current_time.month <= 9:
                    query_time = [f"{current_time.year}0630", f"{current_time.year}0331", f"{current_time.year-1}1231", f"{current_time.year-1}0930"]
                else:
                    query_time = [f"{current_time.year}0930", f"{current_time.year}0630", f"{current_time.year}0331", f"{current_time.year-1}1231"]
                for t in query_time:
                    time.sleep(1)
                    performance_forecast = ak.stock_yjbb_em(t)
                    if stock_code in performance_forecast["股票代码"].values:
                        break
                if stock_code in performance_forecast["股票代码"].values:
                    fundamental_data['performance_repo'] = performance_forecast[performance_forecast["股票代码"] == stock_code].iloc[0].to_dict()
                    logger.info("✓ 业绩报表获取成功")
                else:
                    logger.info("未能查找到业绩报表")
                    fundamental_data['performance_repo'] = "未能找到业绩报表"
            except Exception as e:
                logger.warning(f"获取业绩报表失败: {e}")
                fundamental_data['performance_repo'] = "未能找到业绩报表"
            
            # 5. 分红配股信息
            try:
                logger.info("正在获取分红配股信息...")
                dividend_info = ak.stock_fhps_detail_em(stock_code)
                if not dividend_info.empty:
                    dividend_info_list = []
                    for i in range(min(5, len(dividend_info))):
                        dividend_info_list.append(dividend_info.iloc[-(i+1)].to_dict())
                    fundamental_data['dividend_info'] = dividend_info_list
                    logger.info("✓ 分红配股信息获取成功")
                else:
                    fundamental_data['dividend_info'] = []
            except Exception as e:
                logger.warning(f"获取分红配股信息失败: {e}")
                fundamental_data['dividend_info'] = []
            
            # 6. 行业分析
            try:
                logger.info("正在获取行业分析数据...")
                industry_analysis = self.get_industry_analysis(fundamental_data['basic_info']["行业"])
                fundamental_data['industry_analysis'] = industry_analysis
                logger.info("✓ 行业分析数据获取成功")
            except Exception as e:
                logger.warning(f"获取行业分析失败: {e}")
                fundamental_data['industry_analysis'] = {}
            
            # 缓存数据
            self.fundamental_cache[stock_code] = (datetime.now(), fundamental_data)
            logger.info(f"✓ {stock_code} 综合基本面数据获取完成并已缓存")
            
            return fundamental_data
            
        except Exception as e:
            logger.error(f"获取综合基本面数据失败: {str(e)}")
            return {
                'basic_info': {},
                'financial_indicators': {},
                'valuation': {},
                'performance_forecast': [],
                'dividend_info': [],
                'industry_analysis': {}
            }

    def get_industry_analysis(self, industry_name:str) -> dict:
        """获取行业分析数据"""
        try:
            industry_data = {}
            current_time = datetime.today()

            # 获取行业信息
            try:
                industry_info = ak.stock_board_industry_name_em()
                stock_industry_info = industry_info[industry_info["板块名称"] == industry_name].iloc[0].to_dict()
                industry_data['industry_info'] = stock_industry_info
            except Exception as e:
                logger.warning(f"获取行业信息失败: {e}")
                industry_data['industry_info'] = {}
            
            try:
                # 最近 30 天的交易日数据
                start_date = (current_time - timedelta(days=30)).strftime('%Y%m%d')
                stock_data = ak.stock_zh_a_hist(
                    symbol="000001",
                    period="daily",
                    start_date=start_date,
                    end_date=current_time.strftime("%Y%m%d"),
                    adjust="qfq"
                )
                # 最近两个交易日，按日期升序排列
                date_df = stock_data[['日期']].sort_values('日期').reset_index(drop=True)
                last_trading_day = date_df.iloc[-1]['日期']
                previous_trading_day = date_df.iloc[-2]['日期']

                # 决定用于获取 PE 的日期
                if last_trading_day.strftime('%Y-%m-%d') == current_time.strftime('%Y-%m-%d') and current_time.hour < 17:
                    # 今天交易日但未收盘 → 用上一个交易日
                    pe_date = previous_trading_day.strftime('%Y%m%d')
                else:
                    # 今天非交易日，或已收盘 → 用最近一个交易日
                    pe_date = last_trading_day.strftime('%Y%m%d')

                # 获取行业市盈率
                industry_pe_info = ak.stock_industry_pe_ratio_cninfo("国证行业分类", pe_date)
                if industry_name not in industry_pe_info["行业名称"].to_list():
                    industry_pe_info = ak.stock_industry_pe_ratio_cninfo("证监会行业分类", pe_date)
                if industry_name in industry_pe_info["行业名称"].to_list():
                    stock_industry_pe_info = industry_pe_info[industry_pe_info["行业名称"] == industry_name].iloc[0].to_dict()
                    industry_data['industry_pe_info'] = stock_industry_pe_info
                else:
                    stock_board_industry_cons_em_df = ak.stock_board_industry_cons_em(symbol=industry_name)
                    industry_data['industry_pe_info'] = {
                        "平均换手率": round(float(stock_board_industry_cons_em_df["换手率"].mean()), 2),
                        "平均市盈率-动态": round(float(stock_board_industry_cons_em_df["市盈率-动态"].mean()), 2),
                        "平均市净率": round(float(stock_board_industry_cons_em_df["市净率"].mean()), 2)
                    }

            except Exception as e:
                logger.warning(f"获取行业市盈率失败: {e}")
                industry_data['industry_pe_info'] = {}

            
            return industry_data
            
        except Exception as e:
            logger.warning(f"行业分析失败: {e}")
            return {}

    def get_comprehensive_news_data(self, stock_code:str, days:int=15) -> dict:
        """获取综合新闻数据（修正版本）"""
        cache_key = f"{stock_code}_{days}"
        if cache_key in self.news_cache:
            cache_time, data = self.news_cache[cache_key]
            if datetime.now() - cache_time < self.news_cache_duration:
                logger.info(f"使用缓存的新闻数据: {stock_code}")
                return data
        
        logger.info(f"开始获取 {stock_code} 的综合新闻数据（最近{days}天）...")
        
        try:
            all_news_data = {
                'company_news': [],
                'research_reports': [],
                'market_sentiment': {},
                'news_summary': {}
            }
            
            # 1. 公司新闻
            try:
                logger.info("正在获取公司新闻...")
                company_news = ak.stock_news_em(symbol=stock_code)
                if not company_news.empty:
                    processed_news = []
                    for _, row in company_news.head(50).iterrows():  # 增加获取数量
                        news_item = {
                            'title': row.iloc[1],
                            'content': row.iloc[2],
                            'date': row.iloc[3],
                            'source': row.iloc[4],
                            'url': row.iloc[5],
                            'relevance_score': 1.0
                        }
                        processed_news.append(news_item)
                    
                    all_news_data['company_news'] = processed_news
                    logger.info(f"✓ 获取公司新闻 {len(processed_news)} 条")
            except Exception as e:
                logger.warning(f"获取公司新闻失败: {e}")
            
            # 3. 研究报告
            try:
                logger.info("正在获取研究报告...")
                research_reports = ak.stock_research_report_em(symbol=stock_code)
                if not research_reports.empty:
                    processed_reports = []
                    for _, row in research_reports.head(20).iterrows():  # 增加获取数量
                        report = {
                            'title': row.iloc[3],
                            'institution': row.iloc[5],
                            'rating': row.iloc[4],
                            'target_price': row.iloc[7],
                            'date': row.iloc[14],
                            'relevance_score': 0.9
                        }
                        processed_reports.append(report)
                    
                    all_news_data['research_reports'] = processed_reports
                    logger.info(f"✓ 获取研究报告 {len(processed_reports)} 条")
            except Exception as e:
                logger.warning(f"获取研究报告失败: {e}")
            
            # 5. 新闻摘要统计
            try:
                total_news = (len(all_news_data['company_news']) + 
                            len(all_news_data['research_reports']))
                
                all_news_data['news_summary'] = {
                    'total_news_count': total_news,
                    'company_news_count': len(all_news_data['company_news']),
                    'research_reports_count': len(all_news_data['research_reports']),
                    'data_freshness': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                
            except Exception as e:
                logger.warning(f"生成新闻摘要失败: {e}")
            
            # 缓存数据
            self.news_cache[cache_key] = (datetime.now(), all_news_data)
            
            logger.info(f"✓ 综合新闻数据获取完成，总计 {all_news_data['news_summary'].get('total_news_count', 0)} 条")
            return all_news_data
            
        except Exception as e:
            logger.error(f"获取综合新闻数据失败: {str(e)}")
            return {
                'company_news': [],
                'research_reports': [],
                'market_sentiment': {},
                'news_summary': {'total_news_count': 0}
            }

    def calculate_advanced_sentiment_analysis(self, comprehensive_news_data:dict) -> dict:
        """计算高级情绪分析（修正版本）"""
        logger.info("开始高级情绪分析...")
        
        try:
            # 准备所有新闻文本
            all_texts = []
            
            # 收集所有新闻文本
            for news in comprehensive_news_data.get('company_news', []):
                text = f"{news.get('title', '')} {news.get('content', '')}"
                all_texts.append({'text': text, 'type': 'company_news', 'weight': 1.0})
            
            for report in comprehensive_news_data.get('research_reports', []):
                text = f"{report.get('title', '')} {report.get('rating', '')}"
                all_texts.append({'text': text, 'type': 'research_report', 'weight': 0.9})
            
            if not all_texts:
                return {
                    'overall_sentiment': -1,
                    'sentiment_by_type': {},
                    'sentiment_trend': '分析失败',
                    'confidence_score': -1,
                    'total_analyzed': -1
                }
            
            # 扩展的情绪词典
            positive_words = {
                '上涨', '涨停', '利好', '突破', '增长', '盈利', '收益', '回升', '强势', '看好',
                '买入', '推荐', '优秀', '领先', '创新', '发展', '机会', '潜力', '稳定', '改善',
                '提升', '超预期', '积极', '乐观', '向好', '受益', '龙头', '热点', '爆发', '翻倍',
                '业绩', '增收', '扩张', '合作', '签约', '中标', '获得', '成功', '完成', '达成'
            }
            
            negative_words = {
                '下跌', '跌停', '利空', '破位', '下滑', '亏损', '风险', '回调', '弱势', '看空',
                '卖出', '减持', '较差', '落后', '滞后', '困难', '危机', '担忧', '悲观', '恶化',
                '下降', '低于预期', '消极', '压力', '套牢', '被套', '暴跌', '崩盘', '踩雷', '退市',
                '违规', '处罚', '调查', '停牌', '亏损', '债务', '违约', '诉讼', '纠纷', '问题'
            }
            
            # 分析每类新闻的情绪
            sentiment_by_type = {}
            overall_scores = []
            
            for text_data in all_texts:
                try:
                    text = text_data['text']
                    text_type = text_data['type']
                    weight = text_data['weight']
                    
                    if not text.strip():
                        continue
                    
                    positive_count = sum(1 for word in positive_words if word in text)
                    negative_count = sum(1 for word in negative_words if word in text)
                    
                    # 计算情绪得分
                    total_sentiment_words = positive_count + negative_count
                    if total_sentiment_words > 0:
                        sentiment_score = (positive_count - negative_count) / total_sentiment_words
                    else:
                        sentiment_score = -1
                    
                    # 应用权重
                    weighted_score = sentiment_score * weight
                    overall_scores.append(weighted_score)
                    
                    # 按类型统计
                    if text_type not in sentiment_by_type:
                        sentiment_by_type[text_type] = []
                    sentiment_by_type[text_type].append(weighted_score)
                    
                except Exception as e:
                    continue
            
            # 计算总体情绪
            overall_sentiment = sum(overall_scores) / len(overall_scores) if overall_scores else -1
            
            # 计算各类型平均情绪
            avg_sentiment_by_type = {}
            for text_type, scores in sentiment_by_type.items():
                avg_sentiment_by_type[text_type] = sum(scores) / len(scores) if scores else -1
            
            # 判断情绪趋势
            if overall_sentiment > 0.3:
                sentiment_trend = '非常积极'
            elif overall_sentiment > 0.1:
                sentiment_trend = '偏向积极'
            elif overall_sentiment > -0.1:
                sentiment_trend = '相对中性'
            elif overall_sentiment > -0.3:
                sentiment_trend = '偏向消极'
            else:
                sentiment_trend = '非常消极'
            
            # 计算置信度
            confidence_score = min(len(all_texts) / 50, 1.0)  # 基于新闻数量的置信度
            
            result = {
                'overall_sentiment': overall_sentiment,
                'sentiment_by_type': avg_sentiment_by_type,
                'sentiment_trend': sentiment_trend,
                'confidence_score': confidence_score,
                'total_analyzed': len(all_texts),
                'type_distribution': {k: len(v) for k, v in sentiment_by_type.items()},
                'positive_ratio': len([s for s in overall_scores if s > 0]) / len(overall_scores) if overall_scores else 0,
                'negative_ratio': len([s for s in overall_scores if s < 0]) / len(overall_scores) if overall_scores else 0
            }
            
            logger.info(f"✓ 高级情绪分析完成: {sentiment_trend} (得分: {overall_sentiment:.3f})")
            return result
            
        except Exception as e:
            logger.error(f"高级情绪分析失败: {e}")
            return {
                'overall_sentiment': '分析失败',
                'sentiment_by_type': '分析失败',
                'sentiment_trend': '分析失败',
                'confidence_score': '分析失败',
                'total_analyzed': '分析失败'
            }

    def get_stock_name(self, stock_code:str) -> str:
        """获取股票名称"""
        try:
            stock_info = ak.stock_individual_info_em(symbol=stock_code)
            if not stock_info.empty:
                info_dict = dict(zip(stock_info['item'], stock_info['value']))
                stock_name = info_dict.get('股票简称', stock_code)
                if stock_name and stock_name != stock_code:
                    return stock_name
        except Exception as e:
            logger.warning(f"获取股票名称失败: {e}")
        
        return stock_code

    def set_streaming_config(self, enabled:bool=True, show_thinking:bool=True):
        """设置流式推理配置"""
        self.config.streaming.enabled = enabled
        self.config.streaming.show_thinking = show_thinking

    def analyze_stock(self, stock_code:str, position_percent:float=0, avg_price:float=-1, enable_streaming:bool=False, streamer:StreamingSender=None):
        """分析股票的主方法（修正版，支持AI流式输出）"""
        try:
            logger.info(f"开始增强版股票分析: {stock_code}")
            if streamer:
                streamer.send_progress('singleProgress', 5, "正在获取股票基本信息...")
            
            # 获取股票名称
            stock_name = self.get_stock_name(stock_code)
            
            # 获取价格数据和技术分析
            logger.info("正在进行技术分析...")
            price_data = self.get_stock_data(stock_code)
            if price_data.empty:
                raise ValueError(f"无法获取股票 {stock_code} 的价格数据")
            
            price_info = get_price_info(price_data)
            technical_analysis = calculate_technical_indicators(price_data)
            if streamer:
                streamer.send_partial_result({
                    'type': 'basic_info',
                    'stock_code': stock_code,
                    'stock_name': stock_name,
                    'current_price': price_info['current_price'],
                    'price_change': price_info['price_change']
                })
            
            # 获取财务指标和综合基本面分析
            logger.info("正在进行财务指标分析...")
            fundamental_data = self.get_comprehensive_fundamental_data(stock_code)
            
            # 获取综合新闻数据和高级情绪分析
            logger.info("正在进行综合新闻和情绪分析...")
            comprehensive_news_data = self.get_comprehensive_news_data(stock_code, days=30)
            sentiment_analysis = self.calculate_advanced_sentiment_analysis(comprehensive_news_data)
            
            # 合并新闻数据到情绪分析结果中，方便AI分析使用
            sentiment_analysis.update(comprehensive_news_data)
            
            data_quality = {
                'financial_indicators_count': len(fundamental_data.get('financial_indicators', {})),
                'total_news_count': sentiment_analysis.get('total_analyzed', 0),
                'analysis_completeness': '完整' if len(fundamental_data.get('financial_indicators', {})) >= 15 else '部分'
            }
            if streamer:
                streamer.send_data_quality(data_quality)
            
            # AI分析
            no_thinking_config = analyzer.config.generation.model_copy()
            no_thinking_config.extra_parm = {"chat_template_kwargs": {"enable_thinking": False}}
            if streamer:
                streamer.send_progress('singleProgress', 20, "正在分析K线图...")
            _, K_graph_conclusion = k_graph_analysis(stock_name, get_K_graph_table(price_data), no_thinking_config)
            if streamer:
                streamer.send_progress('singleProgress', 40, "正在分析相关新闻...")
            _, news_summary = news_summarize(stock_name, sentiment_analysis, no_thinking_config)
            if streamer:
                streamer.send_progress('singleProgress', 60, "正在分析公司价值...")
            value_prompt, value_analysis = value_analyze(stock_code, stock_name, fundamental_data, price_info, no_thinking_config, streamer)
            
            prompt, ai_analysis = generate_ai_analysis({
                'stock_code': stock_code,
                'stock_name': stock_name,
                'price_info': price_info,
                'technical_analysis': technical_analysis,
                'fundamental_data': fundamental_data,
                "position_percent": position_percent,
                "avg_price": avg_price,
                "news_summary": news_summary,
                "K_graph_conclusion": K_graph_conclusion,
                "value_analysis": value_analysis
            }, analyzer.config.generation, enable_streaming, streamer)
            
            # 生成最终报告
            report = {
                'stock_code': stock_code,
                'stock_name': stock_name,
                'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'price_info': price_info,
                'technical_analysis': technical_analysis,
                'fundamental_data': fundamental_data,
                'comprehensive_news_data': comprehensive_news_data,
                'sentiment_analysis': sentiment_analysis,
                'analysis_weights': self.config.analysis_weights.model_dump(),
                'ai_analysis': ai_analysis,
                'data_quality': data_quality,
                "value_prompt": value_prompt,
                "prompt": prompt
            }
            if streamer:
                streamer.send_progress('singleProgress', 100, "分析完成")
                streamer.send_final_result(report)
                streamer.send_completion(f"✅ {stock_code} 流式分析完成")

            logger.info(f"✓ 增强版股票分析完成: {stock_code}")
            
            return report
            
        except Exception as e:
            logger.error(f"增强版股票分析失败 {stock_code}: {str(e)}")
            raise

    def analyze_stock_with_streaming(self, stock_code:str, position_percent:float=0, avg_price:float=-1, streamer:StreamingSender=None):
        return self.analyze_stock(stock_code, position_percent, avg_price, True, streamer)
    
    def analyze_batch_streaming(self, stock_codes:list[str], client_id:str):
        streamer = StreamingSender(client_id, sse_manager)
        try:
            total_stocks = len(stock_codes)
            streamer.send_log(f"📊 开始流式批量分析 {total_stocks} 只股票", 'header')
            failed_stocks = []
            for i, stock_code in enumerate(stock_codes):
                try:
                    progress = int((i / total_stocks) * 100)
                    streamer.send_progress('batchProgress', progress, 
                        f"正在分析第 {i+1}/{total_stocks} 只股票", stock_code)
                    
                    report = self.analyze_stock(stock_code)
                    streamer.send_batch_result(i, report)
                    streamer.send_log(f"{stock_code} 分析完成", 'success')
        
                except Exception as e:
                    failed_stocks.append(stock_code)
                    streamer.send_log(f"{stock_code} 分析失败: {e}", 'error')       
        
            streamer.send_progress('batchProgress', 100, f"批量分析完成")
            message = f"🎉 批量分析完成！成功分析 {total_stocks - len(failed_stocks)}/{total_stocks} 只股票"
            if failed_stocks:
                message += f"，失败: {', '.join(failed_stocks)}"
            streamer.send_completion(message)
            return
        except Exception as e:
            error_msg = f"批量流式分析失败: {str(e)}"
            streamer.send_error(error_msg)
            streamer.send_log(f"{error_msg}", 'error')
            streamer.send_completion()
            raise
        
                
    
def init_analyzer(config_path:str) -> WebStockAnalyzer:
    """初始化分析器"""
    global analyzer
    try:
        logger.info("正在初始化WebStockAnalyzer...")
        analyzer = WebStockAnalyzer(config_path)
        logger.info("✅ WebStockAnalyzer初始化成功")
        return analyzer
    except Exception as e:
        logger.error(f"❌ 分析器初始化失败: {e}")
        return None