import math
import pandas as pd

from app.logger import logger

# 安全的数值处理函数
def safe_float(value:float, default:float=-1) -> float:
    try:
        if pd.isna(value):
            return default
        num_value = float(value)
        if math.isnan(num_value) or math.isinf(num_value):
            return default
        return num_value
    except (ValueError, TypeError):
        return default

# 从原始数据中安全获取数值
def safe_get(raw_dict:dict, key, default:float=-1) -> float:
    value = raw_dict.get(key, default)
    try:
        return safe_float(value, default)
    except (ValueError, TypeError):
        return default

def calculate_core_financial_indicators(raw_data:dict) -> dict:
    """计算25项核心财务指标（修正版本）"""
    try:
        indicators = {}
        
        # 1-5: 盈利能力指标
        indicators['净利润率'] = safe_get(raw_data, '净利润率')
        indicators['净资产收益率'] = safe_get(raw_data, '净资产收益率')
        indicators['总资产收益率'] = safe_get(raw_data, '总资产收益率')
        indicators['毛利率'] = safe_get(raw_data, '毛利率')
        indicators['营业利润率'] = safe_get(raw_data, '营业利润率')
        
        # 6-10: 偿债能力指标
        indicators['流动比率'] = safe_get(raw_data, '流动比率')
        indicators['速动比率'] = safe_get(raw_data, '速动比率')
        indicators['资产负债率'] = safe_get(raw_data, '资产负债率')
        indicators['产权比率'] = safe_get(raw_data, '产权比率')
        indicators['利息保障倍数'] = safe_get(raw_data, '利息保障倍数')
        
        # 11-15: 营运能力指标
        indicators['总资产周转率'] = safe_get(raw_data, '总资产周转率')
        indicators['存货周转率'] = safe_get(raw_data, '存货周转率')
        indicators['应收账款周转率'] = safe_get(raw_data, '应收账款周转率')
        indicators['流动资产周转率'] = safe_get(raw_data, '流动资产周转率')
        indicators['固定资产周转率'] = safe_get(raw_data, '固定资产周转率')
        
        # 16-20: 发展能力指标
        indicators['营收同比增长率'] = safe_get(raw_data, '营收同比增长率')
        indicators['净利润同比增长率'] = safe_get(raw_data, '净利润同比增长率')
        indicators['总资产增长率'] = safe_get(raw_data, '总资产增长率')
        indicators['净资产增长率'] = safe_get(raw_data, '净资产增长率')
        indicators['经营现金流增长率'] = safe_get(raw_data, '经营现金流增长率')
        
        # 21-25: 市场表现指标
        indicators['市盈率'] = safe_get(raw_data, '市盈率')
        indicators['市净率'] = safe_get(raw_data, '市净率')
        indicators['市销率'] = safe_get(raw_data, '市销率')
        indicators['PEG比率'] = safe_get(raw_data, 'PEG比率')
        indicators['股息收益率'] = safe_get(raw_data, '股息收益率')
        
        # 计算一些衍生指标
        try:
            # 如果有基础数据，计算一些关键比率
            revenue = safe_get(raw_data, '营业收入')
            net_income = safe_get(raw_data, '净利润')
            total_assets = safe_get(raw_data, '总资产')
            shareholders_equity = safe_get(raw_data, '股东权益')
            
            if revenue > 0 and net_income > 0 and indicators['净利润率'] == 0:
                indicators['净利润率'] = (net_income / revenue) * 100
            
            if total_assets > 0 and net_income > 0 and indicators['总资产收益率'] == 0:
                indicators['总资产收益率'] = (net_income / total_assets) * 100
            
            if shareholders_equity > 0 and net_income > 0 and indicators['净资产收益率'] == 0:
                indicators['净资产收益率'] = (net_income / shareholders_equity) * 100
                    
        except Exception as e:
            logger.warning(f"计算衍生指标失败: {e}")
        
        # 过滤掉无效的指标
        valid_indicators = {k: v for k, v in indicators.items() if v not in [0, None, 'nan']}
        
        logger.info(f"✓ 成功计算 {len(valid_indicators)} 项有效财务指标")
        return valid_indicators
        
    except Exception as e:
        logger.error(f"计算核心财务指标失败: {e}")
        return {}
    
def rolling_mean_tail(series:pd.DataFrame, window:int, default:float) -> float:
    if len(series) < window:
        return safe_float(series.mean(), default)
    else:
        return safe_float(series.iloc[-window:].mean(), default)
    
def get_price_info(price_data:pd.DataFrame) -> dict:
    """从价格数据中提取关键信息 - 修复版本"""
    try:
        if price_data.empty or 'close' not in price_data.columns:
            logger.warning("价格数据为空或缺少收盘价列")
            return {
                'current_price': -1,
                'price_change': -1,
                'volume_ratio': -1,
                'volatility': -1
            }
        
        # 获取最新数据
        latest = price_data.iloc[-1]
        
        # 确保使用收盘价作为当前价格
        current_price = float(latest['close'])
        logger.info(f"✓ 当前价格(收盘价): {current_price}")
        
        # 如果收盘价异常，尝试使用其他价格
        if pd.isna(current_price) or current_price <= 0:
            if 'open' in price_data.columns and not pd.isna(latest['open']) and latest['open'] > 0:
                current_price = float(latest['open'])
                logger.warning(f"⚠️ 收盘价异常，使用开盘价: {current_price}")
            elif 'high' in price_data.columns and not pd.isna(latest['high']) and latest['high'] > 0:
                current_price = float(latest['high'])
                logger.warning(f"⚠️ 收盘价异常，使用最高价: {current_price}")
            else:
                logger.error(f"❌ 所有价格数据都异常")
                return {
                    'current_price': -1,
                    'price_change': -1,
                    'volume_ratio': -1,
                    'volatility': -1
                }
        
        # 计算价格变化
        try:
            if 'change_pct' in price_data.columns and not pd.isna(latest['change_pct']):
                price_change = safe_float(latest['change_pct'])
                logger.info(f"✓ 使用现成的涨跌幅: {price_change}%")
            elif len(price_data) > 1:
                prev = price_data.iloc[-2]
                prev_price = safe_float(prev['close'])
                if prev_price > 0:
                    price_change = safe_float(((current_price - prev_price) / prev_price * 100))
                    logger.info(f"✓ 计算涨跌幅: {price_change}%")
        except Exception as e:
            logger.warning(f"计算价格变化失败: {e}")
            price_change = -1
        
        # 计算成交量比率
        try:
            if 'volume' in price_data.columns:
                volume_data = price_data['volume'].dropna()
                if len(volume_data) >= 20:
                    recent_volume = volume_data.tail(5).mean()
                    avg_volume = volume_data.tail(20).mean()
                    volume_ratio = safe_float(recent_volume / avg_volume, -1)
        except Exception as e:
            logger.warning(f"计算成交量比率失败: {e}")
            volume_ratio = -1
        
        # 计算波动率
        try:
            close_prices = price_data['close'].dropna()
            if len(close_prices) >= 20:
                returns = close_prices.pct_change().dropna()
                volatility = safe_float(returns.tail(20).std() * 100)
        except Exception as e:
            logger.warning(f"计算波动率失败: {e}")
            volatility = -1
        
        result = {
            'current_price': safe_float(current_price, -1),
            'price_change': safe_float(price_change, -1),
            'volume_ratio': safe_float(volume_ratio, -1),
            'volatility': safe_float(volatility, -1)
        }
        
        logger.info(f"✓ 价格信息提取完成: {result}")
        return result
        
    except Exception as e:
        logger.error(f"获取价格信息失败: {e}")
        return {
            'current_price': -1,
            'price_change': -1,
            'volume_ratio': -1,
            'volatility': -1
        }
        
def get_K_graph_table(price_data:pd.DataFrame) -> pd.DataFrame:
    columns_to_keep = ['open', 'close', 'high', 'low']
    missing_cols = [col for col in columns_to_keep if col not in price_data.columns]
    if missing_cols:
        logger.debug(f"输入的DataFrame缺少以下列: {missing_cols}")
        return None
    recent_data = price_data[columns_to_keep].tail(30)
    result = recent_data.fillna("-1")
    
    return result

def _get_default_technical_analysis() -> dict:
    """获取默认技术分析结果"""
    return {
        'ma_trend': '数据不足',
        'rsi': '数据不足',
        'macd_signal': '数据不足',
        'bb_position': '数据不足',
        'volume_status': '数据不足'
    }
    
def calculate_technical_indicators(price_data:pd.DataFrame) -> dict:
    """计算技术指标（修正版本）"""
    try:
        if price_data.empty:
            return _get_default_technical_analysis()
        
        technical_analysis = {}
        
        # 移动平均线
        try:
            latest_price = safe_float(price_data['close'].iloc[-1])
            close = price_data['close']
            ma5 = close.ewm(span=5, adjust=False).mean().iloc[-1]
            ma10 = close.ewm(span=10, adjust=False).mean().iloc[-1]
            ma20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
            
            technical_analysis['ma5'] = ma5
            technical_analysis['ma10'] = ma10
            technical_analysis['ma20'] = ma20
            
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
            window = 14
            close = price_data['close']

            # 检查数据是否足够
            if len(close) < window + 1:
                technical_analysis['rsi'] = "数据不足"
            else:
                delta = close.diff()
                gain = delta.clip(lower=0)
                loss = -delta.clip(upper=0)

                # 用 EWM 实现 Wilder 平滑
                avg_gain = gain.ewm(alpha=1/window, min_periods=window, adjust=False).mean()
                avg_loss = loss.ewm(alpha=1/window, min_periods=window, adjust=False).mean()

                rs = avg_gain / avg_loss.replace(0, pd.NA)  # 防止除零
                rsi_last = 100 - (100 / (1 + rs.iloc[-1]))
                technical_analysis['rsi'] = safe_float(rsi_last, -1)
                if technical_analysis["rsi"] == -1:
                    technical_analysis["rsi"] = "计算失败"
            
        except Exception as e:
            technical_analysis['rsi'] = "计算失败"
        
        try:
            close = price_data['close']
            if len(close) < 35:
                technical_analysis['macd_signal'] = '数据不足'
            else:
                close_recent = close

                # EMA 计算：用于最后两个点
                ema12 = close_recent.ewm(span=12, adjust=False).mean()
                ema26 = close_recent.ewm(span=26, adjust=False).mean()
                dif = ema12 - ema26  # 快线（DIF）
                dea = dif.ewm(span=9, adjust=False).mean()  # 慢线（DEA）

                # 取最后两个点做交叉判断
                dif_now, dif_prev = dif.iloc[-1], dif.iloc[-2]
                dea_now, dea_prev = dea.iloc[-1], dea.iloc[-2]

                if dif_prev < dea_prev and dif_now > dea_now:
                    # DIF 上穿 DEA => 金叉
                    technical_analysis['macd_signal'] = '零上金叉' if dif_now > 0 else '零下金叉'
                elif dif_prev > dea_prev and dif_now < dea_now:
                    # DIF 下穿 DEA => 死叉
                    technical_analysis['macd_signal'] = '零上死叉' if dif_now > 0 else '零下死叉'
                elif dif_now > dea_now:
                    technical_analysis['macd_signal'] = '多头趋势'
                else:
                    technical_analysis['macd_signal'] = '空头趋势'
            
                technical_analysis['dif'] = dif_now
                technical_analysis['dea'] = dea_now

        except Exception as e:
            technical_analysis['macd_signal'] = '计算失败'
        
        try:
            close = price_data['close']
            window = 20
            if len(close) < 2:
                technical_analysis['bb_position'] = "数据不足"
            else:
                # 只取最后 window 个数据计算
                close_recent = close.iloc[-window:]
                bb_middle = close_recent.mean()
                bb_std = close_recent.std()

                bb_upper = bb_middle + 2 * bb_std
                bb_lower = bb_middle - 2 * bb_std
                latest_close = safe_float(close.iloc[-1])

                # 避免除以 0
                band_range = bb_upper - bb_lower
                if band_range > 0:
                    bb_position = (latest_close - bb_lower) / band_range
                    # 保证在 0~1 区间
                    bb_position = max(0.0, min(1.0, bb_position))
                else:
                    bb_position = 0.5

                technical_analysis['bb_position'] = safe_float(bb_position)

        except Exception:
            technical_analysis['bb_position'] = '计算失败'
        
        # 成交量分析
        try:
            volume_window = min(20, len(price_data))
            recent_data = price_data.iloc[-volume_window:]
            recent_volume = safe_float(price_data['volume'].iloc[-1])
            avg_volume = safe_float(recent_data['volume'].mean(), recent_volume)
            
            if 'change_pct' in price_data.columns:
                price_change = safe_float(price_data['change_pct'].iloc[-1])
            elif len(price_data) >= 2:
                current_price = safe_float(price_data['close'].iloc[-1])
                prev_price = safe_float(price_data['close'].iloc[-2])
                price_change = ((current_price - prev_price) / prev_price) * 100 if prev_price > 0 else 0
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
        logger.error(f"技术指标计算失败: {str(e)}")
        return _get_default_technical_analysis()
    
def calculate_technical_score(technical_analysis:dict) -> float:
    """计算技术分析得分"""
    try:
        score = 50
        
        ma_trend = technical_analysis.get('ma_trend', '数据不足')
        if ma_trend == '多头排列':
            score += 20
        elif ma_trend == '空头排列':
            score -= 20
        
        rsi = technical_analysis.get('rsi', 50)
        if isinstance(rsi, str):
            score -= 5
        elif 30 <= rsi <= 70:
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
        
        bb_position = technical_analysis.get('bb_position', 1.0)
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
        logger.error(f"技术分析评分失败: {str(e)}")
        return -1