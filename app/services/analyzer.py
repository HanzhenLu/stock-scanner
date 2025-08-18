import pandas as pd
import akshare as ak
import math
import time
from datetime import datetime, timedelta

from app.logger import logger
from app.utils.config import load_config
from app.utils.financial_utils import (get_price_info, calculate_technical_indicators, calculate_technical_score)
from app.services.ai_client import generate_ai_analysis

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
                if industry_name not in industry_pe_info["行业名称"].to_list():
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

    def calculate_fundamental_score(self, fundamental_data:dict) -> float:
        """计算基本面得分"""
        try:
            score = 50
            
            # 财务指标评分
            financial_indicators = fundamental_data.get('financial_indicators', {})
            if len(financial_indicators) >= 15:  # 有足够的财务指标
                score += 20
                
                # 盈利能力评分
                roe = financial_indicators.get('净资产收益率', 0)
                if isinstance(roe, str) and roe.endswith("%"):
                    roe = float(roe[:-1])
                if roe > 15:
                    score += 10
                elif roe > 10:
                    score += 5
                elif roe < 5:
                    score -= 5
                
                # 偿债能力评分
                debt_ratio = financial_indicators.get('资产负债率', 100)
                if isinstance(debt_ratio, str) and debt_ratio.endswith("%"):
                    debt_ratio = float(debt_ratio[:-1])
                if debt_ratio < 30:
                    score += 5
                elif debt_ratio > 70:
                    score -= 10
                
                # 成长性评分
                revenue_growth = financial_indicators.get('营收同比增长率', 0)
                if isinstance(revenue_growth, str) and revenue_growth.endswith("%"):
                    revenue_growth = float(revenue_growth[:-1])
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
            logger.error(f"基本面评分失败: {str(e)}")
            return -1

    def calculate_sentiment_score(self, sentiment_analysis:dict) -> float:
        """计算情绪分析得分"""
        try:
            overall_sentiment = sentiment_analysis['overall_sentiment']
            confidence_score = sentiment_analysis['confidence_score']
            total_analyzed = sentiment_analysis['total_analyzed']
            
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
            logger.error(f"情绪得分计算失败: {e}")
            return -1

    def calculate_comprehensive_score(self, scores:dict) -> float:
        """计算综合得分"""
        try:
            technical_score = scores.get('technical', 50)
            fundamental_score = scores.get('fundamental', 50)
            sentiment_score = scores.get('sentiment', 50)
            
            comprehensive_score = (
                technical_score * self.config.analysis_weights.technical +
                fundamental_score * self.config.analysis_weights.fundamental +
                sentiment_score * self.config.analysis_weights.sentiment
            )
            
            comprehensive_score = max(0, min(100, comprehensive_score))
            return comprehensive_score
            
        except Exception as e:
            logger.error(f"计算综合得分失败: {e}")
            return -1

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

    def generate_recommendation(self, scores:dict) -> str:
        """根据得分生成投资建议"""
        try:
            comprehensive_score = scores.get('comprehensive', 0)
            technical_score = scores.get('technical', 0)
            fundamental_score = scores.get('fundamental', 0)
            sentiment_score = scores.get('sentiment', 0)
            
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
            logger.warning(f"生成投资建议失败: {e}")
            return "数据不足，建议谨慎"

    def set_streaming_config(self, enabled:bool=True, show_thinking:bool=True):
        """设置流式推理配置"""
        self.config.streaming.enabled = enabled
        self.config.streaming.show_thinking = show_thinking

    def analyze_stock(self, stock_code, enable_streaming=None, stream_callback=None):
        """分析股票的主方法（修正版，支持AI流式输出）"""
        if enable_streaming is None:
            enable_streaming = self.config.streaming.enabled
        
        try:
            logger.info(f"开始增强版股票分析: {stock_code}")
            
            # 获取股票名称
            stock_name = self.get_stock_name(stock_code)
            
            # 1. 获取价格数据和技术分析
            logger.info("正在进行技术分析...")
            price_data = self.get_stock_data(stock_code)
            if price_data.empty:
                raise ValueError(f"无法获取股票 {stock_code} 的价格数据")
            
            price_info = get_price_info(price_data)
            technical_analysis = calculate_technical_indicators(price_data)
            technical_score = calculate_technical_score(technical_analysis)
            
            # 2. 获取财务指标和综合基本面分析
            logger.info("正在进行财务指标分析...")
            fundamental_data = self.get_comprehensive_fundamental_data(stock_code)
            fundamental_score = self.calculate_fundamental_score(fundamental_data)
            
            # 3. 获取综合新闻数据和高级情绪分析
            logger.info("正在进行综合新闻和情绪分析...")
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
            ai_analysis = generate_ai_analysis({
                'stock_code': stock_code,
                'stock_name': stock_name,
                'price_info': price_info,
                'technical_analysis': technical_analysis,
                'fundamental_data': fundamental_data,
                'sentiment_analysis': sentiment_analysis,
                'scores': scores
            }, analyzer.config.generation, enable_streaming, stream_callback)
            
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
                'analysis_weights': self.config.analysis_weights.model_dump(),
                'recommendation': recommendation,
                'ai_analysis': ai_analysis,
                'data_quality': {
                    'financial_indicators_count': len(fundamental_data.get('financial_indicators', {})),
                    'total_news_count': sentiment_analysis.get('total_analyzed', 0),
                    'analysis_completeness': '完整' if len(fundamental_data.get('financial_indicators', {})) >= 15 else '部分'
                }
            }
            
            logger.info(f"✓ 增强版股票分析完成: {stock_code}")
            logger.info(f"  - 财务指标: {len(fundamental_data.get('financial_indicators', {}))} 项")
            logger.info(f"  - 新闻数据: {sentiment_analysis.get('total_analyzed', 0)} 条")
            logger.info(f"  - 综合得分: {scores['comprehensive']:.1f}")
            
            return report
            
        except Exception as e:
            logger.error(f"增强版股票分析失败 {stock_code}: {str(e)}")
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