import math

from app.logger import logger

def calculate_core_financial_indicators(raw_data):
    """计算25项核心财务指标（修正版本）"""
    try:
        indicators = {}
        
        # 从原始数据中安全获取数值
        def safe_get(key, default=0):
            value = raw_data.get(key, default)
            try:
                if value is None or value == '' or str(value).lower() in ['nan', 'none', '--']:
                    return default
                num_value = float(value)
                # 检查是否为NaN或无穷大
                if math.isnan(num_value) or math.isinf(num_value):
                    return default
                return num_value
            except (ValueError, TypeError):
                return default
        
        # 1-5: 盈利能力指标
        indicators['净利润率'] = safe_get('净利润率')
        indicators['净资产收益率'] = safe_get('净资产收益率')
        indicators['总资产收益率'] = safe_get('总资产收益率')
        indicators['毛利率'] = safe_get('毛利率')
        indicators['营业利润率'] = safe_get('营业利润率')
        
        # 6-10: 偿债能力指标
        indicators['流动比率'] = safe_get('流动比率')
        indicators['速动比率'] = safe_get('速动比率')
        indicators['资产负债率'] = safe_get('资产负债率')
        indicators['产权比率'] = safe_get('产权比率')
        indicators['利息保障倍数'] = safe_get('利息保障倍数')
        
        # 11-15: 营运能力指标
        indicators['总资产周转率'] = safe_get('总资产周转率')
        indicators['存货周转率'] = safe_get('存货周转率')
        indicators['应收账款周转率'] = safe_get('应收账款周转率')
        indicators['流动资产周转率'] = safe_get('流动资产周转率')
        indicators['固定资产周转率'] = safe_get('固定资产周转率')
        
        # 16-20: 发展能力指标
        indicators['营收同比增长率'] = safe_get('营收同比增长率')
        indicators['净利润同比增长率'] = safe_get('净利润同比增长率')
        indicators['总资产增长率'] = safe_get('总资产增长率')
        indicators['净资产增长率'] = safe_get('净资产增长率')
        indicators['经营现金流增长率'] = safe_get('经营现金流增长率')
        
        # 21-25: 市场表现指标
        indicators['市盈率'] = safe_get('市盈率')
        indicators['市净率'] = safe_get('市净率')
        indicators['市销率'] = safe_get('市销率')
        indicators['PEG比率'] = safe_get('PEG比率')
        indicators['股息收益率'] = safe_get('股息收益率')
        
        # 计算一些衍生指标
        try:
            # 如果有基础数据，计算一些关键比率
            revenue = safe_get('营业收入')
            net_income = safe_get('净利润')
            total_assets = safe_get('总资产')
            shareholders_equity = safe_get('股东权益')
            
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