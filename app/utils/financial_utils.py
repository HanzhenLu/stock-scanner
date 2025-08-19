import math
import pandas as pd
import datetime

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
            ma60 = close.ewm(span=60, adjust=False).mean().iloc[-1]
            
            technical_analysis['ma5'] = ma5
            technical_analysis['ma10'] = ma10
            technical_analysis['ma20'] = ma20
            technical_analysis['ma60'] = ma60
            
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
            technical_analysis['volume_status'] = {
                '当天交易量': recent_volume,
                f'近{volume_window}天平均交易量': avg_volume
            }
            
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
                technical_analysis['volume_status']['判断'] = '放量上涨' if price_change > 0 else '放量下跌'
            elif recent_volume < avg_volume * 0.5:
                technical_analysis['volume_status']['判断'] = '缩量调整'
            else:
                technical_analysis['volume_status']['判断'] = '温和放量'
            
        except Exception as e:
            technical_analysis['volume_status'] = '数据不足'
        
        return technical_analysis
        
    except Exception as e:
        logger.error(f"技术指标计算失败: {str(e)}")
        return _get_default_technical_analysis()