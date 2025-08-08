import json
import math
import numpy as np

def format_dict_data(data_dict:dict, max_items:int=5) -> str:
    """格式化字典数据"""
    if not data_dict:
        return "无数据"
    
    formatted = ""
    for i, (key, value) in enumerate(data_dict.items()):
        if i >= max_items:
            break
        formatted += f"- {key}: {value}\n"
    
    return formatted if formatted else "无有效数据"

def format_list_data(data_list:list, max_items:int=3) -> str:
    """格式化列表数据"""
    if not data_list:
        return "无数据"
    
    formatted = ""
    for i, item in enumerate(data_list):
        if i >= max_items:
            break
        if isinstance(item, dict):
            # 取字典的前几个键值对
            item_str = ", ".join([f"{k}: {v}" for k, v in list(item.items())[:max_items]])
            formatted += f"- {item_str}\n"
        else:
            formatted += f"- {item}\n"
    
    return formatted if formatted else "无有效数据"

def clean_data_for_json(obj):
    """清理数据中的NaN、Infinity、日期等无效值，使其能够正确序列化为JSON"""
    import pandas as pd
    from datetime import datetime, date, time
    
    if isinstance(obj, dict):
        return {key: clean_data_for_json(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [clean_data_for_json(item) for item in obj]
    elif isinstance(obj, tuple):
        return [clean_data_for_json(item) for item in obj]
    elif isinstance(obj, (int, float)):
        if math.isnan(obj):
            return None
        elif math.isinf(obj):
            return None
        else:
            return obj
    elif isinstance(obj, np.ndarray):
        return clean_data_for_json(obj.tolist())
    elif isinstance(obj, (np.integer, np.floating)):
        if np.isnan(obj):
            return None
        elif np.isinf(obj):
            return None
        else:
            return obj.item()
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat() if hasattr(obj, 'isoformat') else str(obj)
    elif isinstance(obj, time):
        return obj.isoformat()
    elif isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    elif isinstance(obj, pd.NaT.__class__):
        return None
    elif pd.isna(obj):
        return None
    elif hasattr(obj, 'to_dict'):  # DataFrame或Series
        try:
            return clean_data_for_json(obj.to_dict())
        except:
            return str(obj)
    elif hasattr(obj, 'item'):  # numpy标量
        try:
            return clean_data_for_json(obj.item())
        except:
            return str(obj)
    elif obj is None:
        return None
    elif isinstance(obj, (str, bool)):
        return obj
    else:
        # 对于其他不可序列化的对象，转换为字符串
        try:
            # 尝试直接序列化测试
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)