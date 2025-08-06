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