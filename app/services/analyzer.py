import pandas as pd
import akshare as ak
import math
from datetime import datetime, timedelta

from app.logger import logger
from app.utils.config import load_config
from financial_utils import calculate_core_financial_indicators

class WebStockAnalyzer:
    """Web版增强股票分析器（基于最新 stock_analyzer.py 修正，支持AI流式输出）"""
    
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
        
        # 检查API密钥状态
        available_apis = []

        logger.info(f"🤖 可用AI API: {', '.join(available_apis)}")
        primary = self.config.generation.model_preference
        logger.info(f"🎯 主要API: {primary}")
        
        # 显示自定义配置
        for server, url in self.config.generation.api_base_urls.items():
            if url.strip():
                available_apis.append(server)
                logger.info(f"🔗 {server} : {url}")
        
        if not available_apis:
            logger.warning("⚠️ 未配置任何AI")
        
        logger.info(f"📊 财务指标数量: {self.config.analysis_params.financial_indicators_count}")
        logger.info(f"📰 最大新闻数量: {self.config.analysis_params.max_news_count}")
        logger.info(f"📈 技术分析周期: {self.config.analysis_params.technical_period_days} 天")
        
        # 检查Web鉴权配置
        if self.config.web_auth.enabled:
            logger.info(f"🔐 Web鉴权: 已启用")
        else:
            logger.info(f"🔓 Web鉴权: 未启用")
        
        logger.info("=" * 40)

    def get_stock_data(self, stock_code):
        """获取股票价格数据（修正版本）"""
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

    def get_comprehensive_fundamental_data(self, stock_code):
        """获取25项综合财务指标数据"""
        if stock_code in self.fundamental_cache:
            cache_time, data = self.fundamental_cache[stock_code]
            if datetime.now() - cache_time < self.fundamental_cache_duration:
                logger.info(f"使用缓存的基本面数据: {stock_code}")
                return data
        
        try:
            fundamental_data = {}
            logger.info(f"开始获取 {stock_code} 的25项综合财务指标...")
            
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
            
            # 2. 详细财务指标 - 25项核心指标
            try:
                logger.info("正在获取25项详细财务指标...")
                financial_indicators = {}
                
                # 获取主要财务数据
                try:
                    # 利润表数据
                    income_statement = ak.stock_financial_abstract_ths(symbol=stock_code, indicator="按报告期")
                    if not income_statement.empty:
                        latest_income = income_statement.iloc[0].to_dict()
                        financial_indicators.update(latest_income)
                except Exception as e:
                    logger.warning(f"获取利润表数据失败: {e}")
                
                # 获取财务分析指标
                try:
                    balance_sheet = ak.stock_financial_analysis_indicator(symbol=stock_code)
                    if not balance_sheet.empty:
                        latest_balance = balance_sheet.iloc[-1].to_dict()
                        financial_indicators.update(latest_balance)
                except Exception as e:
                    logger.warning(f"获取财务分析指标失败: {e}")
                
                # 获取现金流量表
                try:
                    cash_flow = ak.stock_cash_flow_sheet_by_report_em(symbol=stock_code)
                    if not cash_flow.empty:
                        latest_cash = cash_flow.iloc[-1].to_dict()
                        financial_indicators.update(latest_cash)
                except Exception as e:
                    logger.warning(f"获取现金流量表失败: {e}")
                
                # 计算25项核心财务指标
                core_indicators = calculate_core_financial_indicators(financial_indicators)
                fundamental_data['financial_indicators'] = core_indicators
                
            except Exception as e:
                logger.warning(f"获取财务指标失败: {e}")
                fundamental_data['financial_indicators'] = {}
            
            # 3. 估值指标
            try:
                logger.info("正在获取估值指标...")
                valuation_data = ak.stock_a_indicator_lg(symbol=stock_code)
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
                    self.logger.info("✓ 估值指标获取成功")
                else:
                    fundamental_data['valuation'] = {}
            except Exception as e:
                self.logger.warning(f"获取估值指标失败: {e}")
                fundamental_data['valuation'] = {}
            
            # 4. 业绩预告和业绩快报
            try:
                self.logger.info("正在获取业绩预告...")
                performance_forecast = ak.stock_yjbb_em(symbol=stock_code)
                if not performance_forecast.empty:
                    fundamental_data['performance_forecast'] = performance_forecast.head(10).to_dict('records')
                    self.logger.info("✓ 业绩预告获取成功")
                else:
                    fundamental_data['performance_forecast'] = []
            except Exception as e:
                self.logger.warning(f"获取业绩预告失败: {e}")
                fundamental_data['performance_forecast'] = []
            
            # 5. 分红配股信息
            try:
                self.logger.info("正在获取分红配股信息...")
                dividend_info = ak.stock_fhpg_em(symbol=stock_code)
                if not dividend_info.empty:
                    fundamental_data['dividend_info'] = dividend_info.head(10).to_dict('records')
                    self.logger.info("✓ 分红配股信息获取成功")
                else:
                    fundamental_data['dividend_info'] = []
            except Exception as e:
                self.logger.warning(f"获取分红配股信息失败: {e}")
                fundamental_data['dividend_info'] = []
            
            # 6. 行业分析
            try:
                self.logger.info("正在获取行业分析数据...")
                industry_analysis = self._get_industry_analysis(stock_code)
                fundamental_data['industry_analysis'] = industry_analysis
                self.logger.info("✓ 行业分析数据获取成功")
            except Exception as e:
                self.logger.warning(f"获取行业分析失败: {e}")
                fundamental_data['industry_analysis'] = {}
            
            # 缓存数据
            self.fundamental_cache[stock_code] = (datetime.now(), fundamental_data)
            self.logger.info(f"✓ {stock_code} 综合基本面数据获取完成并已缓存")
            
            return fundamental_data
            
        except Exception as e:
            self.logger.error(f"获取综合基本面数据失败: {str(e)}")
            return {
                'basic_info': {},
                'financial_indicators': {},
                'valuation': {},
                'performance_forecast': [],
                'dividend_info': [],
                'industry_analysis': {}
            }

    def _get_industry_analysis(self, stock_code):
        """获取行业分析数据"""
        try:
            import akshare as ak
            
            industry_data = {}
            
            # 获取行业信息
            try:
                industry_info = ak.stock_board_industry_name_em()
                stock_industry = industry_info[industry_info.iloc[:, 0].astype(str).str.contains(stock_code, na=False)]
                if not stock_industry.empty:
                    industry_data['industry_info'] = stock_industry.iloc[0].to_dict()
                else:
                    industry_data['industry_info'] = {}
            except Exception as e:
                logger.warning(f"获取行业信息失败: {e}")
                industry_data['industry_info'] = {}
            
            return industry_data
            
        except Exception as e:
            logger.warning(f"行业分析失败: {e}")
            return {}

    def get_comprehensive_news_data(self, stock_code, days=15):
        """获取综合新闻数据（修正版本）"""
        cache_key = f"{stock_code}_{days}"
        if cache_key in self.news_cache:
            cache_time, data = self.news_cache[cache_key]
            if datetime.now() - cache_time < self.news_cache_duration:
                logger.info(f"使用缓存的新闻数据: {stock_code}")
                return data
        
        logger.info(f"开始获取 {stock_code} 的综合新闻数据（最近{days}天）...")
        
        try:
            import akshare as ak
            
            stock_name = self.get_stock_name(stock_code)
            all_news_data = {
                'company_news': [],
                'announcements': [],
                'research_reports': [],
                'industry_news': [],
                'market_sentiment': {},
                'news_summary': {}
            }
            
            # 1. 公司新闻
            try:
                self.logger.info("正在获取公司新闻...")
                company_news = ak.stock_news_em(symbol=stock_code)
                if not company_news.empty:
                    processed_news = []
                    for _, row in company_news.head(50).iterrows():  # 增加获取数量
                        news_item = {
                            'title': str(row.get(row.index[0], '')),
                            'content': str(row.get(row.index[1], '')) if len(row.index) > 1 else '',
                            'date': str(row.get(row.index[2], '')) if len(row.index) > 2 else datetime.now().strftime('%Y-%m-%d'),
                            'source': 'eastmoney',
                            'url': str(row.get(row.index[3], '')) if len(row.index) > 3 else '',
                            'relevance_score': 1.0
                        }
                        processed_news.append(news_item)
                    
                    all_news_data['company_news'] = processed_news
                    self.logger.info(f"✓ 获取公司新闻 {len(processed_news)} 条")
            except Exception as e:
                self.logger.warning(f"获取公司新闻失败: {e}")
            
            # 2. 公司公告
            try:
                self.logger.info("正在获取公司公告...")
                announcements = ak.stock_zh_a_alerts_cls(symbol=stock_code)
                if not announcements.empty:
                    processed_announcements = []
                    for _, row in announcements.head(30).iterrows():  # 增加获取数量
                        announcement = {
                            'title': str(row.get(row.index[0], '')),
                            'content': str(row.get(row.index[1], '')) if len(row.index) > 1 else '',
                            'date': str(row.get(row.index[2], '')) if len(row.index) > 2 else datetime.now().strftime('%Y-%m-%d'),
                            'type': str(row.get(row.index[3], '')) if len(row.index) > 3 else '公告',
                            'relevance_score': 1.0
                        }
                        processed_announcements.append(announcement)
                    
                    all_news_data['announcements'] = processed_announcements
                    self.logger.info(f"✓ 获取公司公告 {len(processed_announcements)} 条")
            except Exception as e:
                self.logger.warning(f"获取公司公告失败: {e}")
            
            # 3. 研究报告
            try:
                self.logger.info("正在获取研究报告...")
                research_reports = ak.stock_research_report_em(symbol=stock_code)
                if not research_reports.empty:
                    processed_reports = []
                    for _, row in research_reports.head(20).iterrows():  # 增加获取数量
                        report = {
                            'title': str(row.get(row.index[0], '')),
                            'institution': str(row.get(row.index[1], '')) if len(row.index) > 1 else '',
                            'rating': str(row.get(row.index[2], '')) if len(row.index) > 2 else '',
                            'target_price': str(row.get(row.index[3], '')) if len(row.index) > 3 else '',
                            'date': str(row.get(row.index[4], '')) if len(row.index) > 4 else datetime.now().strftime('%Y-%m-%d'),
                            'relevance_score': 0.9
                        }
                        processed_reports.append(report)
                    
                    all_news_data['research_reports'] = processed_reports
                    self.logger.info(f"✓ 获取研究报告 {len(processed_reports)} 条")
            except Exception as e:
                self.logger.warning(f"获取研究报告失败: {e}")
            
            # 4. 行业新闻
            try:
                self.logger.info("正在获取行业新闻...")
                industry_news = self._get_comprehensive_industry_news(stock_code, days)
                all_news_data['industry_news'] = industry_news
                self.logger.info(f"✓ 获取行业新闻 {len(industry_news)} 条")
            except Exception as e:
                self.logger.warning(f"获取行业新闻失败: {e}")
            
            # 5. 新闻摘要统计
            try:
                total_news = (len(all_news_data['company_news']) + 
                            len(all_news_data['announcements']) + 
                            len(all_news_data['research_reports']) + 
                            len(all_news_data['industry_news']))
                
                all_news_data['news_summary'] = {
                    'total_news_count': total_news,
                    'company_news_count': len(all_news_data['company_news']),
                    'announcements_count': len(all_news_data['announcements']),
                    'research_reports_count': len(all_news_data['research_reports']),
                    'industry_news_count': len(all_news_data['industry_news']),
                    'data_freshness': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                
            except Exception as e:
                self.logger.warning(f"生成新闻摘要失败: {e}")
            
            # 缓存数据
            self.news_cache[cache_key] = (datetime.now(), all_news_data)
            
            self.logger.info(f"✓ 综合新闻数据获取完成，总计 {all_news_data['news_summary'].get('total_news_count', 0)} 条")
            return all_news_data
            
        except Exception as e:
            self.logger.error(f"获取综合新闻数据失败: {str(e)}")
            return {
                'company_news': [],
                'announcements': [],
                'research_reports': [],
                'industry_news': [],
                'market_sentiment': {},
                'news_summary': {'total_news_count': 0}
            }

    def _get_comprehensive_industry_news(self, stock_code, days=30):
        """获取详细的行业新闻"""
        try:
            # 这里可以根据实际需要扩展行业新闻获取逻辑
            # 目前返回一个示例结构
            industry_news = []
            
            # 可以添加更多的行业新闻源
            # 比如获取同行业其他公司的新闻
            # 获取行业政策新闻等
            
            self.logger.info(f"行业新闻获取完成，共 {len(industry_news)} 条")
            return industry_news
            
        except Exception as e:
            self.logger.warning(f"获取行业新闻失败: {e}")
            return []

    def calculate_advanced_sentiment_analysis(self, comprehensive_news_data):
        """计算高级情绪分析（修正版本）"""
        self.logger.info("开始高级情绪分析...")
        
        try:
            # 准备所有新闻文本
            all_texts = []
            
            # 收集所有新闻文本
            for news in comprehensive_news_data.get('company_news', []):
                text = f"{news.get('title', '')} {news.get('content', '')}"
                all_texts.append({'text': text, 'type': 'company_news', 'weight': 1.0})
            
            for announcement in comprehensive_news_data.get('announcements', []):
                text = f"{announcement.get('title', '')} {announcement.get('content', '')}"
                all_texts.append({'text': text, 'type': 'announcement', 'weight': 1.2})  # 公告权重更高
            
            for report in comprehensive_news_data.get('research_reports', []):
                text = f"{report.get('title', '')} {report.get('rating', '')}"
                all_texts.append({'text': text, 'type': 'research_report', 'weight': 0.9})
            
            for news in comprehensive_news_data.get('industry_news', []):
                text = f"{news.get('title', '')} {news.get('content', '')}"
                all_texts.append({'text': text, 'type': 'industry_news', 'weight': 0.7})
            
            if not all_texts:
                return {
                    'overall_sentiment': 0.0,
                    'sentiment_by_type': {},
                    'sentiment_trend': '中性',
                    'confidence_score': 0.0,
                    'total_analyzed': 0
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
                        sentiment_score = 0.0
                    
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
            overall_sentiment = sum(overall_scores) / len(overall_scores) if overall_scores else 0.0
            
            # 计算各类型平均情绪
            avg_sentiment_by_type = {}
            for text_type, scores in sentiment_by_type.items():
                avg_sentiment_by_type[text_type] = sum(scores) / len(scores) if scores else 0.0
            
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
            
            self.logger.info(f"✓ 高级情绪分析完成: {sentiment_trend} (得分: {overall_sentiment:.3f})")
            return result
            
        except Exception as e:
            self.logger.error(f"高级情绪分析失败: {e}")
            return {
                'overall_sentiment': 0.0,
                'sentiment_by_type': {},
                'sentiment_trend': '分析失败',
                'confidence_score': 0.0,
                'total_analyzed': 0
            }

    def calculate_technical_indicators(self, price_data):
        """计算技术指标（修正版本）"""
        try:
            if price_data.empty:
                return self._get_default_technical_analysis()
            
            technical_analysis = {}
            
            # 安全的数值处理函数
            def safe_float(value, default=50.0):
                try:
                    if pd.isna(value):
                        return default
                    num_value = float(value)
                    if math.isnan(num_value) or math.isinf(num_value):
                        return default
                    return num_value
                except (ValueError, TypeError):
                    return default
            
            # 移动平均线
            try:
                price_data['ma5'] = price_data['close'].rolling(window=5, min_periods=1).mean()
                price_data['ma10'] = price_data['close'].rolling(window=10, min_periods=1).mean()
                price_data['ma20'] = price_data['close'].rolling(window=20, min_periods=1).mean()
                price_data['ma60'] = price_data['close'].rolling(window=60, min_periods=1).mean()
                
                latest_price = safe_float(price_data['close'].iloc[-1])
                ma5 = safe_float(price_data['ma5'].iloc[-1], latest_price)
                ma10 = safe_float(price_data['ma10'].iloc[-1], latest_price)
                ma20 = safe_float(price_data['ma20'].iloc[-1], latest_price)
                
                if latest_price > ma5 > ma10 > ma20:
                    technical_analysis['ma_trend'] = '多头排列'
                elif latest_price < ma5 < ma10 < ma20:
                    technical_analysis['ma_trend'] = '空头排列'
                else:
                    technical_analysis['ma_trend'] = '震荡整理'
                
            except Exception as e:
                technical_analysis['ma_trend'] = '计算失败'
            
            # RSI指标
            try:
                def calculate_rsi(prices, window=14):
                    delta = prices.diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=window, min_periods=1).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=window, min_periods=1).mean()
                    rs = gain / loss
                    rsi = 100 - (100 / (1 + rs))
                    return rsi
                
                rsi_series = calculate_rsi(price_data['close'])
                technical_analysis['rsi'] = safe_float(rsi_series.iloc[-1], 50.0)
                
            except Exception as e:
                technical_analysis['rsi'] = 50.0
            
            # MACD指标
            try:
                ema12 = price_data['close'].ewm(span=12, min_periods=1).mean()
                ema26 = price_data['close'].ewm(span=26, min_periods=1).mean()
                macd_line = ema12 - ema26
                signal_line = macd_line.ewm(span=9, min_periods=1).mean()
                histogram = macd_line - signal_line
                
                if len(histogram) >= 2:
                    current_hist = safe_float(histogram.iloc[-1])
                    prev_hist = safe_float(histogram.iloc[-2])
                    
                    if current_hist > prev_hist and current_hist > 0:
                        technical_analysis['macd_signal'] = '金叉向上'
                    elif current_hist < prev_hist and current_hist < 0:
                        technical_analysis['macd_signal'] = '死叉向下'
                    else:
                        technical_analysis['macd_signal'] = '横盘整理'
                else:
                    technical_analysis['macd_signal'] = '数据不足'
                
            except Exception as e:
                technical_analysis['macd_signal'] = '计算失败'
            
            # 布林带
            try:
                bb_window = min(20, len(price_data))
                bb_middle = price_data['close'].rolling(window=bb_window, min_periods=1).mean()
                bb_std = price_data['close'].rolling(window=bb_window, min_periods=1).std()
                bb_upper = bb_middle + 2 * bb_std
                bb_lower = bb_middle - 2 * bb_std
                
                latest_close = safe_float(price_data['close'].iloc[-1])
                bb_upper_val = safe_float(bb_upper.iloc[-1])
                bb_lower_val = safe_float(bb_lower.iloc[-1])
                
                if bb_upper_val != bb_lower_val and bb_upper_val > bb_lower_val:
                    bb_position = (latest_close - bb_lower_val) / (bb_upper_val - bb_lower_val)
                    technical_analysis['bb_position'] = safe_float(bb_position, 0.5)
                else:
                    technical_analysis['bb_position'] = 0.5
                
            except Exception as e:
                technical_analysis['bb_position'] = 0.5
            
            # 成交量分析
            try:
                volume_window = min(20, len(price_data))
                avg_volume = price_data['volume'].rolling(window=volume_window, min_periods=1).mean().iloc[-1]
                recent_volume = safe_float(price_data['volume'].iloc[-1])
                
                if 'change_pct' in price_data.columns:
                    price_change = safe_float(price_data['change_pct'].iloc[-1])
                elif len(price_data) >= 2:
                    current_price = safe_float(price_data['close'].iloc[-1])
                    prev_price = safe_float(price_data['close'].iloc[-2])
                    if prev_price > 0:
                        price_change = ((current_price - prev_price) / prev_price) * 100
                    else:
                        price_change = 0
                else:
                    price_change = 0
                
                avg_volume = safe_float(avg_volume, recent_volume)
                if recent_volume > avg_volume * 1.5:
                    technical_analysis['volume_status'] = '放量上涨' if price_change > 0 else '放量下跌'
                elif recent_volume < avg_volume * 0.5:
                    technical_analysis['volume_status'] = '缩量调整'
                else:
                    technical_analysis['volume_status'] = '温和放量'
                
            except Exception as e:
                technical_analysis['volume_status'] = '数据不足'
            
            return technical_analysis
            
        except Exception as e:
            self.logger.error(f"技术指标计算失败: {str(e)}")
            return self._get_default_technical_analysis()

    def _get_default_technical_analysis(self):
        """获取默认技术分析结果"""
        return {
            'ma_trend': '数据不足',
            'rsi': 50.0,
            'macd_signal': '数据不足',
            'bb_position': 0.5,
            'volume_status': '数据不足'
        }

    def calculate_technical_score(self, technical_analysis):
        """计算技术分析得分"""
        try:
            score = 50
            
            ma_trend = technical_analysis.get('ma_trend', '数据不足')
            if ma_trend == '多头排列':
                score += 20
            elif ma_trend == '空头排列':
                score -= 20
            
            rsi = technical_analysis.get('rsi', 50)
            if 30 <= rsi <= 70:
                score += 10
            elif rsi < 30:
                score += 5
            elif rsi > 70:
                score -= 5
            
            macd_signal = technical_analysis.get('macd_signal', '横盘整理')
            if macd_signal == '金叉向上':
                score += 15
            elif macd_signal == '死叉向下':
                score -= 15
            
            bb_position = technical_analysis.get('bb_position', 0.5)
            if 0.2 <= bb_position <= 0.8:
                score += 5
            elif bb_position < 0.2:
                score += 10
            elif bb_position > 0.8:
                score -= 5
            
            volume_status = technical_analysis.get('volume_status', '数据不足')
            if '放量上涨' in volume_status:
                score += 10
            elif '放量下跌' in volume_status:
                score -= 10
            
            score = max(0, min(100, score))
            return score
            
        except Exception as e:
            self.logger.error(f"技术分析评分失败: {str(e)}")
            return 50

    def calculate_fundamental_score(self, fundamental_data):
        """计算基本面得分"""
        try:
            score = 50
            
            # 财务指标评分
            financial_indicators = fundamental_data.get('financial_indicators', {})
            if len(financial_indicators) >= 15:  # 有足够的财务指标
                score += 20
                
                # 盈利能力评分
                roe = financial_indicators.get('净资产收益率', 0)
                if roe > 15:
                    score += 10
                elif roe > 10:
                    score += 5
                elif roe < 5:
                    score -= 5
                
                # 偿债能力评分
                debt_ratio = financial_indicators.get('资产负债率', 50)
                if debt_ratio < 30:
                    score += 5
                elif debt_ratio > 70:
                    score -= 10
                
                # 成长性评分
                revenue_growth = financial_indicators.get('营收同比增长率', 0)
                if revenue_growth > 20:
                    score += 10
                elif revenue_growth > 10:
                    score += 5
                elif revenue_growth < -10:
                    score -= 10
            
            # 估值评分
            valuation = fundamental_data.get('valuation', {})
            if valuation:
                score += 10
            
            # 业绩预告评分
            performance_forecast = fundamental_data.get('performance_forecast', [])
            if performance_forecast:
                score += 10
            
            score = max(0, min(100, score))
            return score
            
        except Exception as e:
            self.logger.error(f"基本面评分失败: {str(e)}")
            return 50

    def calculate_sentiment_score(self, sentiment_analysis):
        """计算情绪分析得分"""
        try:
            overall_sentiment = sentiment_analysis.get('overall_sentiment', 0.0)
            confidence_score = sentiment_analysis.get('confidence_score', 0.0)
            total_analyzed = sentiment_analysis.get('total_analyzed', 0)
            
            # 基础得分：将情绪得分从[-1,1]映射到[0,100]
            base_score = (overall_sentiment + 1) * 50
            
            # 置信度调整
            confidence_adjustment = confidence_score * 10
            
            # 新闻数量调整
            news_adjustment = min(total_analyzed / 100, 1.0) * 10
            
            final_score = base_score + confidence_adjustment + news_adjustment
            final_score = max(0, min(100, final_score))
            
            return final_score
            
        except Exception as e:
            self.logger.error(f"情绪得分计算失败: {e}")
            return 50

    def calculate_comprehensive_score(self, scores):
        """计算综合得分"""
        try:
            technical_score = scores.get('technical', 50)
            fundamental_score = scores.get('fundamental', 50)
            sentiment_score = scores.get('sentiment', 50)
            
            comprehensive_score = (
                technical_score * self.analysis_weights['technical'] +
                fundamental_score * self.analysis_weights['fundamental'] +
                sentiment_score * self.analysis_weights['sentiment']
            )
            
            comprehensive_score = max(0, min(100, comprehensive_score))
            return comprehensive_score
            
        except Exception as e:
            self.logger.error(f"计算综合得分失败: {e}")
            return 50

    def get_stock_name(self, stock_code):
        """获取股票名称"""
        try:
            import akshare as ak
            
            try:
                stock_info = ak.stock_individual_info_em(symbol=stock_code)
                if not stock_info.empty:
                    info_dict = dict(zip(stock_info['item'], stock_info['value']))
                    stock_name = info_dict.get('股票简称', stock_code)
                    if stock_name and stock_name != stock_code:
                        return stock_name
            except Exception as e:
                self.logger.warning(f"获取股票名称失败: {e}")
            
            return stock_code
            
        except Exception as e:
            self.logger.warning(f"获取股票名称时出错: {e}")
            return stock_code

    def get_price_info(self, price_data):
        """从价格数据中提取关键信息 - 修复版本"""
        try:
            if price_data.empty or 'close' not in price_data.columns:
                self.logger.warning("价格数据为空或缺少收盘价列")
                return {
                    'current_price': 0.0,
                    'price_change': 0.0,
                    'volume_ratio': 1.0,
                    'volatility': 0.0
                }
            
            # 获取最新数据
            latest = price_data.iloc[-1]
            
            # 确保使用收盘价作为当前价格
            current_price = float(latest['close'])
            self.logger.info(f"✓ 当前价格(收盘价): {current_price}")
            
            # 如果收盘价异常，尝试使用其他价格
            if pd.isna(current_price) or current_price <= 0:
                if 'open' in price_data.columns and not pd.isna(latest['open']) and latest['open'] > 0:
                    current_price = float(latest['open'])
                    self.logger.warning(f"⚠️ 收盘价异常，使用开盘价: {current_price}")
                elif 'high' in price_data.columns and not pd.isna(latest['high']) and latest['high'] > 0:
                    current_price = float(latest['high'])
                    self.logger.warning(f"⚠️ 收盘价异常，使用最高价: {current_price}")
                else:
                    self.logger.error(f"❌ 所有价格数据都异常")
                    return {
                        'current_price': 0.0,
                        'price_change': 0.0,
                        'volume_ratio': 1.0,
                        'volatility': 0.0
                    }
            
            # 安全的数值处理函数
            def safe_float(value, default=0.0):
                try:
                    if pd.isna(value):
                        return default
                    num_value = float(value)
                    if math.isnan(num_value) or math.isinf(num_value):
                        return default
                    return num_value
                except (ValueError, TypeError):
                    return default
            
            # 计算价格变化
            price_change = 0.0
            try:
                if 'change_pct' in price_data.columns and not pd.isna(latest['change_pct']):
                    price_change = safe_float(latest['change_pct'])
                    self.logger.info(f"✓ 使用现成的涨跌幅: {price_change}%")
                elif len(price_data) > 1:
                    prev = price_data.iloc[-2]
                    prev_price = safe_float(prev['close'])
                    if prev_price > 0:
                        price_change = safe_float(((current_price - prev_price) / prev_price * 100))
                        self.logger.info(f"✓ 计算涨跌幅: {price_change}%")
            except Exception as e:
                self.logger.warning(f"计算价格变化失败: {e}")
                price_change = 0.0
            
            # 计算成交量比率
            volume_ratio = 1.0
            try:
                if 'volume' in price_data.columns:
                    volume_data = price_data['volume'].dropna()
                    if len(volume_data) >= 5:
                        recent_volume = volume_data.tail(5).mean()
                        avg_volume = volume_data.mean()
                        if avg_volume > 0:
                            volume_ratio = safe_float(recent_volume / avg_volume, 1.0)
            except Exception as e:
                self.logger.warning(f"计算成交量比率失败: {e}")
                volume_ratio = 1.0
            
            # 计算波动率
            volatility = 0.0
            try:
                close_prices = price_data['close'].dropna()
                if len(close_prices) >= 20:
                    returns = close_prices.pct_change().dropna()
                    if len(returns) >= 20:
                        volatility = safe_float(returns.tail(20).std() * 100)
            except Exception as e:
                self.logger.warning(f"计算波动率失败: {e}")
                volatility = 0.0
            
            result = {
                'current_price': safe_float(current_price),
                'price_change': safe_float(price_change),
                'volume_ratio': safe_float(volume_ratio, 1.0),
                'volatility': safe_float(volatility)
            }
            
            self.logger.info(f"✓ 价格信息提取完成: {result}")
            return result
            
        except Exception as e:
            self.logger.error(f"获取价格信息失败: {e}")
            return {
                'current_price': 0.0,
                'price_change': 0.0,
                'volume_ratio': 1.0,
                'volatility': 0.0
            }

    def generate_recommendation(self, scores):
        """根据得分生成投资建议"""
        try:
            comprehensive_score = scores.get('comprehensive', 50)
            technical_score = scores.get('technical', 50)
            fundamental_score = scores.get('fundamental', 50)
            sentiment_score = scores.get('sentiment', 50)
            
            if comprehensive_score >= 80:
                if technical_score >= 75 and fundamental_score >= 75:
                    return "强烈推荐买入"
                else:
                    return "推荐买入"
            elif comprehensive_score >= 65:
                if sentiment_score >= 60:
                    return "建议买入"
                else:
                    return "谨慎买入"
            elif comprehensive_score >= 45:
                return "持有观望"
            elif comprehensive_score >= 30:
                return "建议减仓"
            else:
                return "建议卖出"
                
        except Exception as e:
            self.logger.warning(f"生成投资建议失败: {e}")
            return "数据不足，建议谨慎"

    def _build_enhanced_ai_analysis_prompt(self, stock_code, stock_name, scores, technical_analysis, 
                                        fundamental_data, sentiment_analysis, price_info):
        """构建增强版AI分析提示词，包含所有详细数据"""
        
        # 提取25项财务指标
        financial_indicators = fundamental_data.get('financial_indicators', {})
        financial_text = ""
        if financial_indicators:
            financial_text = "**25项核心财务指标：**\n"
            for i, (key, value) in enumerate(financial_indicators.items(), 1):
                if isinstance(value, (int, float)) and value != 0:
                    financial_text += f"{i}. {key}: {value}\n"
        
        # 提取新闻详细信息
        news_summary = sentiment_analysis.get('news_summary', {})
        company_news = sentiment_analysis.get('company_news', [])
        announcements = sentiment_analysis.get('announcements', [])
        research_reports = sentiment_analysis.get('research_reports', [])
        
        news_text = f"""
**新闻数据详情：**
- 公司新闻：{len(company_news)}条
- 公司公告：{len(announcements)}条  
- 研究报告：{len(research_reports)}条
- 总新闻数：{news_summary.get('total_news_count', 0)}条

**重要新闻标题（前10条）：**
"""
        
        for i, news in enumerate(company_news[:5], 1):
            news_text += f"{i}. {news.get('title', '未知标题')}\n"
        
        for i, announcement in enumerate(announcements[:5], 1):
            news_text += f"{i+5}. [公告] {announcement.get('title', '未知标题')}\n"
        
        # 提取研究报告信息
        research_text = ""
        if research_reports:
            research_text = "\n**研究报告摘要：**\n"
            for i, report in enumerate(research_reports[:5], 1):
                research_text += f"{i}. {report.get('institution', '未知机构')}: {report.get('rating', '未知评级')} - {report.get('title', '未知标题')}\n"
        
        # 构建完整的提示词
        prompt = f"""请作为一位资深的股票分析师，基于以下详细数据对股票进行深度分析：

**股票基本信息：**
- 股票代码：{stock_code}
- 股票名称：{stock_name}
- 当前价格：{price_info.get('current_price', 0):.2f}元
- 涨跌幅：{price_info.get('price_change', 0):.2f}%
- 成交量比率：{price_info.get('volume_ratio', 1):.2f}
- 波动率：{price_info.get('volatility', 0):.2f}%

**技术分析详情：**
- 均线趋势：{technical_analysis.get('ma_trend', '未知')}
- RSI指标：{technical_analysis.get('rsi', 50):.1f}
- MACD信号：{technical_analysis.get('macd_signal', '未知')}
- 布林带位置：{technical_analysis.get('bb_position', 0.5):.2f}
- 成交量状态：{technical_analysis.get('volume_status', '未知')}

{financial_text}

**估值指标：**
{self._format_dict_data(fundamental_data.get('valuation', {}))}

**业绩预告：**
共{len(fundamental_data.get('performance_forecast', []))}条业绩预告
{self._format_list_data(fundamental_data.get('performance_forecast', [])[:3])}

**分红配股：**
共{len(fundamental_data.get('dividend_info', []))}条分红配股信息
{self._format_list_data(fundamental_data.get('dividend_info', [])[:3])}

{news_text}

{research_text}

**市场情绪分析：**
- 整体情绪得分：{sentiment_analysis.get('overall_sentiment', 0):.3f}
- 情绪趋势：{sentiment_analysis.get('sentiment_trend', '中性')}
- 置信度：{sentiment_analysis.get('confidence_score', 0):.2f}
- 各类新闻情绪：{sentiment_analysis.get('sentiment_by_type', {})}

**综合评分：**
- 技术面得分：{scores.get('technical', 50):.1f}/100
- 基本面得分：{scores.get('fundamental', 50):.1f}/100
- 情绪面得分：{scores.get('sentiment', 50):.1f}/100
- 综合得分：{scores.get('comprehensive', 50):.1f}/100

**分析要求：**

请基于以上详细数据，从以下维度进行深度分析：

1. **财务健康度深度解读**：
   - 基于25项财务指标，全面评估公司财务状况
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

        return prompt

    def _format_dict_data(self, data_dict, max_items=5):
        """格式化字典数据"""
        if not data_dict:
            return "无数据"
        
        formatted = ""
        for i, (key, value) in enumerate(data_dict.items()):
            if i >= max_items:
                break
            formatted += f"- {key}: {value}\n"
        
        return formatted if formatted else "无有效数据"

    def _format_list_data(self, data_list, max_items=3):
        """格式化列表数据"""
        if not data_list:
            return "无数据"
        
        formatted = ""
        for i, item in enumerate(data_list):
            if i >= max_items:
                break
            if isinstance(item, dict):
                # 取字典的前几个键值对
                item_str = ", ".join([f"{k}: {v}" for k, v in list(item.items())[:3]])
                formatted += f"- {item_str}\n"
            else:
                formatted += f"- {item}\n"
        
        return formatted if formatted else "无有效数据"

    def generate_ai_analysis(self, analysis_data, enable_streaming=False, stream_callback=None):
        """生成AI增强分析 - 支持流式输出"""
        try:
            self.logger.info("🤖 开始AI深度分析...")
            
            stock_code = analysis_data.get('stock_code', '')
            stock_name = analysis_data.get('stock_name', stock_code)
            scores = analysis_data.get('scores', {})
            technical_analysis = analysis_data.get('technical_analysis', {})
            fundamental_data = analysis_data.get('fundamental_data', {})
            sentiment_analysis = analysis_data.get('sentiment_analysis', {})
            price_info = analysis_data.get('price_info', {})
            
            # 构建增强版AI分析提示词
            prompt = self._build_enhanced_ai_analysis_prompt(
                stock_code, stock_name, scores, technical_analysis, 
                fundamental_data, sentiment_analysis, price_info
            )
            
            # 调用AI API（支持流式）
            ai_response = self._call_ai_api(prompt, enable_streaming, stream_callback)
            
            if ai_response:
                self.logger.info("✅ AI深度分析完成")
                return ai_response
            else:
                self.logger.warning("⚠️ AI API不可用，使用高级分析模式")
                return self._advanced_rule_based_analysis(analysis_data)
                
        except Exception as e:
            self.logger.error(f"AI分析失败: {e}")
            return self._advanced_rule_based_analysis(analysis_data)

    def _call_ai_api(self, prompt, enable_streaming=False, stream_callback=None):
        """调用AI API - 支持流式输出"""
        try:
            model_preference = self.config.get('ai', {}).get('model_preference', 'openai')
            
            if model_preference == 'openai' and self.api_keys.get('openai'):
                result = self._call_openai_api(prompt, enable_streaming, stream_callback)
                if result:
                    return result
            
            elif model_preference == 'anthropic' and self.api_keys.get('anthropic'):
                result = self._call_claude_api(prompt, enable_streaming, stream_callback)
                if result:
                    return result
                    
            elif model_preference == 'zhipu' and self.api_keys.get('zhipu'):
                result = self._call_zhipu_api(prompt, enable_streaming, stream_callback)
                if result:
                    return result
            
            # 尝试其他可用的服务
            if self.api_keys.get('openai') and model_preference != 'openai':
                self.logger.info("尝试备用OpenAI API...")
                result = self._call_openai_api(prompt, enable_streaming, stream_callback)
                if result:
                    return result
                    
            if self.api_keys.get('anthropic') and model_preference != 'anthropic':
                self.logger.info("尝试备用Claude API...")
                result = self._call_claude_api(prompt, enable_streaming, stream_callback)
                if result:
                    return result
                    
            if self.api_keys.get('zhipu') and model_preference != 'zhipu':
                self.logger.info("尝试备用智谱AI API...")
                result = self._call_zhipu_api(prompt, enable_streaming, stream_callback)
                if result:
                    return result
            
            return None
                
        except Exception as e:
            self.logger.error(f"AI API调用失败: {e}")
            return None

    def _call_openai_api(self, prompt, enable_streaming=False, stream_callback=None):
        """调用OpenAI API - 支持流式输出"""
        try:
            import openai
            
            api_key = self.api_keys.get('openai')
            if not api_key:
                return None
            
            # 设置API密钥
            openai.api_key = api_key
            
            # 处理API base URL
            api_base = self.config.get('ai', {}).get('api_base_urls', {}).get('openai')
            if api_base:
                openai.api_base = api_base
                self.logger.info(f"使用自定义API Base: {api_base}")
            
            model = self.config.get('ai', {}).get('models', {}).get('openai', 'gpt-4o-mini')
            max_tokens = self.config.get('ai', {}).get('max_tokens', 6000)
            temperature = self.config.get('ai', {}).get('temperature', 0.7)
            
            self.logger.info(f"正在调用OpenAI {model} 进行深度分析...")
            
            messages = [
                {"role": "system", "content": "你是一位资深的股票分析师，具有丰富的市场经验和深厚的金融知识。请提供专业、客观、有深度的股票分析。"},
                {"role": "user", "content": prompt}
            ]
            
            # 检测OpenAI库版本并使用相应的API
            try:
                # 尝试新版本API (openai >= 1.0)
                if hasattr(openai, 'OpenAI'):
                    client = openai.OpenAI(api_key=api_key)
                    if api_base:
                        client.base_url = api_base
                    
                    if enable_streaming and stream_callback:
                        # 流式调用
                        response = client.chat.completions.create(
                            model=model,
                            messages=messages,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            stream=True
                        )
                        
                        full_response = ""
                        for chunk in response:
                            if chunk.choices[0].delta.content:
                                content = chunk.choices[0].delta.content
                                full_response += content
                                # 发送流式内容
                                if stream_callback:
                                    stream_callback(content)
                        
                        return full_response
                    else:
                        # 非流式调用
                        response = client.chat.completions.create(
                            model=model,
                            messages=messages,
                            max_tokens=max_tokens,
                            temperature=temperature
                        )
                        return response.choices[0].message.content
                
                # 使用旧版本API (openai < 1.0)
                else:
                    if enable_streaming and stream_callback:
                        # 流式调用
                        response = openai.ChatCompletion.create(
                            model=model,
                            messages=messages,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            stream=True
                        )
                        
                        full_response = ""
                        for chunk in response:
                            if chunk.choices[0].delta.get('content'):
                                content = chunk.choices[0].delta.content
                                full_response += content
                                # 发送流式内容
                                if stream_callback:
                                    stream_callback(content)
                        
                        return full_response
                    else:
                        # 非流式调用
                        response = openai.ChatCompletion.create(
                            model=model,
                            messages=messages,
                            max_tokens=max_tokens,
                            temperature=temperature
                        )
                        return response.choices[0].message.content
                    
            except Exception as api_error:
                self.logger.error(f"OpenAI API调用错误: {api_error}")
                return None
                
        except ImportError:
            self.logger.error("OpenAI库未安装")
            return None
        except Exception as e:
            self.logger.error(f"OpenAI API调用失败: {e}")
            return None

    def _call_claude_api(self, prompt, enable_streaming=False, stream_callback=None):
        """调用Claude API - 支持流式输出"""
        try:
            import anthropic
            
            api_key = self.api_keys.get('anthropic')
            if not api_key:
                return None
            
            client = anthropic.Anthropic(api_key=api_key)
            
            model = self.config.get('ai', {}).get('models', {}).get('anthropic', 'claude-3-haiku-20240307')
            max_tokens = self.config.get('ai', {}).get('max_tokens', 6000)
            
            self.logger.info(f"正在调用Claude {model} 进行深度分析...")
            
            if enable_streaming and stream_callback:
                # 流式调用
                with client.messages.stream(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                ) as stream:
                    full_response = ""
                    for text in stream.text_stream:
                        full_response += text
                        # 发送流式内容
                        if stream_callback:
                            stream_callback(text)
                
                return full_response
            else:
                # 非流式调用
                response = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                
                return response.content[0].text
            
        except Exception as e:
            self.logger.error(f"Claude API调用失败: {e}")
            return None

    def _call_zhipu_api(self, prompt, enable_streaming=False, stream_callback=None):
        """调用智谱AI API - 支持流式输出"""
        try:
            api_key = self.api_keys.get('zhipu')
            if not api_key:
                return None
            
            model = self.config.get('ai', {}).get('models', {}).get('zhipu', 'chatglm_turbo')
            max_tokens = self.config.get('ai', {}).get('max_tokens', 6000)
            temperature = self.config.get('ai', {}).get('temperature', 0.7)
            
            self.logger.info(f"正在调用智谱AI {model} 进行深度分析...")
            
            try:
                # 尝试新版本zhipuai库
                import zhipuai
                zhipuai.api_key = api_key
                
                # 尝试新的调用方式
                if hasattr(zhipuai, 'ZhipuAI'):
                    client = zhipuai.ZhipuAI(api_key=api_key)
                    
                    if enable_streaming and stream_callback:
                        # 流式调用
                        response = client.chat.completions.create(
                            model=model,
                            messages=[
                                {"role": "user", "content": prompt}
                            ],
                            temperature=temperature,
                            max_tokens=max_tokens,
                            stream=True
                        )
                        
                        full_response = ""
                        for chunk in response:
                            if chunk.choices[0].delta.content:
                                content = chunk.choices[0].delta.content
                                full_response += content
                                # 发送流式内容
                                if stream_callback:
                                    stream_callback(content)
                        
                        return full_response
                    else:
                        # 非流式调用
                        response = client.chat.completions.create(
                            model=model,
                            messages=[
                                {"role": "user", "content": prompt}
                            ],
                            temperature=temperature,
                            max_tokens=max_tokens
                        )
                        return response.choices[0].message.content
                
                # 使用旧版本调用方式
                else:
                    # 注意：旧版本可能不支持流式
                    response = zhipuai.model_api.invoke(
                        model=model,
                        prompt=[
                            {"role": "user", "content": prompt}
                        ],
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    
                    # 处理不同的响应格式
                    if isinstance(response, dict):
                        if 'data' in response and 'choices' in response['data']:
                            return response['data']['choices'][0]['content']
                        elif 'choices' in response:
                            return response['choices'][0]['content']
                        elif 'data' in response:
                            return response['data']
                    
                    return str(response)
                    
            except ImportError:
                self.logger.error("智谱AI库未安装")
                return None
            except Exception as api_error:
                self.logger.error(f"智谱AI API调用错误: {api_error}")
                return None
            
        except Exception as e:
            self.logger.error(f"智谱AI API调用失败: {e}")
            return None

    def _advanced_rule_based_analysis(self, analysis_data):
        """高级规则分析（AI备用方案）"""
        try:
            self.logger.info("🧠 使用高级规则引擎进行分析...")
            
            stock_code = analysis_data.get('stock_code', '')
            stock_name = analysis_data.get('stock_name', stock_code)
            scores = analysis_data.get('scores', {})
            technical_analysis = analysis_data.get('technical_analysis', {})
            fundamental_data = analysis_data.get('fundamental_data', {})
            sentiment_analysis = analysis_data.get('sentiment_analysis', {})
            price_info = analysis_data.get('price_info', {})
            
            analysis_sections = []
            
            # 1. 综合评估
            comprehensive_score = scores.get('comprehensive', 50)
            analysis_sections.append(f"""## 📊 综合评估

基于技术面、基本面和市场情绪的综合分析，{stock_name}({stock_code})的综合得分为{comprehensive_score:.1f}分。

- 技术面得分：{scores.get('technical', 50):.1f}/100
- 基本面得分：{scores.get('fundamental', 50):.1f}/100  
- 情绪面得分：{scores.get('sentiment', 50):.1f}/100""")
            
            # 2. 财务分析
            financial_indicators = fundamental_data.get('financial_indicators', {})
            if financial_indicators:
                key_metrics = []
                for key, value in list(financial_indicators.items())[:10]:
                    if isinstance(value, (int, float)) and value != 0:
                        key_metrics.append(f"- {key}: {value}")
                
                financial_text = f"""## 💰 财务健康度分析

获取到{len(financial_indicators)}项财务指标，主要指标如下：

{chr(10).join(key_metrics[:8])}

财务健康度评估：{'优秀' if scores.get('fundamental', 50) >= 70 else '良好' if scores.get('fundamental', 50) >= 50 else '需关注'}"""
                analysis_sections.append(financial_text)
            
            # 3. 技术面分析
            tech_analysis = f"""## 📈 技术面分析

当前技术指标显示：
- 均线趋势：{technical_analysis.get('ma_trend', '未知')}
- RSI指标：{technical_analysis.get('rsi', 50):.1f}
- MACD信号：{technical_analysis.get('macd_signal', '未知')}
- 成交量状态：{technical_analysis.get('volume_status', '未知')}

技术面评估：{'强势' if scores.get('technical', 50) >= 70 else '中性' if scores.get('technical', 50) >= 50 else '偏弱'}"""
            analysis_sections.append(tech_analysis)
            
            # 4. 市场情绪
            sentiment_desc = f"""## 📰 市场情绪分析

基于{sentiment_analysis.get('total_analyzed', 0)}条新闻的分析：
- 整体情绪：{sentiment_analysis.get('sentiment_trend', '中性')}
- 情绪得分：{sentiment_analysis.get('overall_sentiment', 0):.3f}
- 置信度：{sentiment_analysis.get('confidence_score', 0):.2%}

新闻分布：
- 公司新闻：{len(sentiment_analysis.get('company_news', []))}条
- 公司公告：{len(sentiment_analysis.get('announcements', []))}条  
- 研究报告：{len(sentiment_analysis.get('research_reports', []))}条"""
            analysis_sections.append(sentiment_desc)
            
            # 5. 投资建议
            recommendation = self.generate_recommendation(scores)
            strategy = f"""## 🎯 投资策略建议

**投资建议：{recommendation}**

根据综合分析，建议如下：

{'**积极配置**：各项指标表现优异，可适当加大仓位。' if comprehensive_score >= 80 else 
 '**谨慎买入**：整体表现良好，但需要关注风险点。' if comprehensive_score >= 60 else
 '**观望为主**：当前风险收益比一般，建议等待更好时机。' if comprehensive_score >= 40 else
 '**规避风险**：多项指标显示风险较大，建议减仓或观望。'}

操作建议：
- 买入时机：技术面突破关键位置时
- 止损位置：跌破重要技术支撑
- 持有周期：中长期为主"""
            analysis_sections.append(strategy)
            
            return "\n\n".join(analysis_sections)
            
        except Exception as e:
            self.logger.error(f"高级规则分析失败: {e}")
            return "分析系统暂时不可用，请稍后重试。"

    def set_streaming_config(self, enabled=True, show_thinking=True):
        """设置流式推理配置"""
        self.streaming_config.update({
            'enabled': enabled,
            'show_thinking': show_thinking
        })

    def analyze_stock(self, stock_code, enable_streaming=None, stream_callback=None):
        """分析股票的主方法（修正版，支持AI流式输出）"""
        if enable_streaming is None:
            enable_streaming = self.streaming_config.get('enabled', False)
        
        try:
            self.logger.info(f"开始增强版股票分析: {stock_code}")
            
            # 获取股票名称
            stock_name = self.get_stock_name(stock_code)
            
            # 1. 获取价格数据和技术分析
            self.logger.info("正在进行技术分析...")
            price_data = self.get_stock_data(stock_code)
            if price_data.empty:
                raise ValueError(f"无法获取股票 {stock_code} 的价格数据")
            
            price_info = self.get_price_info(price_data)
            technical_analysis = self.calculate_technical_indicators(price_data)
            technical_score = self.calculate_technical_score(technical_analysis)
            
            # 2. 获取25项财务指标和综合基本面分析
            self.logger.info("正在进行25项财务指标分析...")
            fundamental_data = self.get_comprehensive_fundamental_data(stock_code)
            fundamental_score = self.calculate_fundamental_score(fundamental_data)
            
            # 3. 获取综合新闻数据和高级情绪分析
            self.logger.info("正在进行综合新闻和情绪分析...")
            comprehensive_news_data = self.get_comprehensive_news_data(stock_code, days=30)
            sentiment_analysis = self.calculate_advanced_sentiment_analysis(comprehensive_news_data)
            sentiment_score = self.calculate_sentiment_score(sentiment_analysis)
            
            # 合并新闻数据到情绪分析结果中，方便AI分析使用
            sentiment_analysis.update(comprehensive_news_data)
            
            # 4. 计算综合得分
            scores = {
                'technical': technical_score,
                'fundamental': fundamental_score,
                'sentiment': sentiment_score,
                'comprehensive': self.calculate_comprehensive_score({
                    'technical': technical_score,
                    'fundamental': fundamental_score,
                    'sentiment': sentiment_score
                })
            }
            
            # 5. 生成投资建议
            recommendation = self.generate_recommendation(scores)
            
            # 6. AI增强分析（包含所有详细数据，支持流式输出）
            ai_analysis = self.generate_ai_analysis({
                'stock_code': stock_code,
                'stock_name': stock_name,
                'price_info': price_info,
                'technical_analysis': technical_analysis,
                'fundamental_data': fundamental_data,
                'sentiment_analysis': sentiment_analysis,
                'scores': scores
            }, enable_streaming, stream_callback)
            
            # 7. 生成最终报告
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
                'analysis_weights': self.analysis_weights,
                'recommendation': recommendation,
                'ai_analysis': ai_analysis,
                'data_quality': {
                    'financial_indicators_count': len(fundamental_data.get('financial_indicators', {})),
                    'total_news_count': sentiment_analysis.get('total_analyzed', 0),
                    'analysis_completeness': '完整' if len(fundamental_data.get('financial_indicators', {})) >= 15 else '部分'
                }
            }
            
            self.logger.info(f"✓ 增强版股票分析完成: {stock_code}")
            self.logger.info(f"  - 财务指标: {len(fundamental_data.get('financial_indicators', {}))} 项")
            self.logger.info(f"  - 新闻数据: {sentiment_analysis.get('total_analyzed', 0)} 条")
            self.logger.info(f"  - 综合得分: {scores['comprehensive']:.1f}")
            
            return report
            
        except Exception as e:
            self.logger.error(f"增强版股票分析失败 {stock_code}: {str(e)}")
            raise

    def analyze_stock_with_streaming(self, stock_code, streamer):
        """带流式回调的股票分析方法"""
        def stream_callback(content):
            """AI流式内容回调"""
            if streamer:
                streamer.send_ai_stream(content)
        
        return self.analyze_stock(stock_code, enable_streaming=True, stream_callback=stream_callback)

    # 兼容旧版本的方法名
    def get_fundamental_data(self, stock_code):
        """兼容方法：获取基本面数据"""
        return self.get_comprehensive_fundamental_data(stock_code)
    
    def get_news_data(self, stock_code, days=30):
        """兼容方法：获取新闻数据"""
        return self.get_comprehensive_news_data(stock_code, days)
    
    def calculate_news_sentiment(self, news_data):
        """兼容方法：计算新闻情绪"""
        return self.calculate_advanced_sentiment_analysis(news_data)
    
    def get_sentiment_analysis(self, stock_code):
        """兼容方法：获取情绪分析"""
        news_data = self.get_comprehensive_news_data(stock_code)
        return self.calculate_advanced_sentiment_analysis(news_data)