import os
import json
from pydantic import BaseModel, Field
from datetime import datetime

from app.logger import logger

class GenerationConfig(BaseModel):
    server_name: str = "openai"
    model_name: str = "gpt-3.5-turbo"
    max_tokens: int = 4096
    temperature: float = 0.7
    extra_parm: dict[str, str] = {}
    api_base_url: str = "https://api.openai.com/v1"
    api_key: str = ""

class AnalysisWeights(BaseModel):
    technical: float = 0.4
    fundamental: float = 0.4
    sentiment: float = 0.2
    
class CacheConfig(BaseModel):
    price_hours: int = 6
    fundamental_hours: int = 6
    news_hours: int = 2
    
class StreamingConfig(BaseModel):
    enabled: bool = False
    show_thinking: bool = False
    delay: float = 0.05

class AnalysisParams(BaseModel):
    max_news_count: int = 100
    technical_period_days: int = 180
    financial_indicators_count: int = 25

class WebAuth(BaseModel):
    enabled: bool = False
    password: str = ""
    session_timeout: int = 3600
    
class Metadata(BaseModel):
    version: str = "3.0.0-web-streaming"
    created: str = Field(default_factory=lambda: datetime.now().isoformat())
    description: str = "Web版AI股票分析系统配置文件"

class WebConfig(BaseModel):
    generation: GenerationConfig = GenerationConfig()
    analysis_weights: AnalysisWeights = AnalysisWeights()
    cache: CacheConfig = CacheConfig()
    streaming: StreamingConfig = StreamingConfig()
    analysis_params: AnalysisParams = AnalysisParams()
    web_auth: WebAuth = WebAuth()
    _metadata: Metadata = Metadata()

def get_default_config() -> WebConfig:
    """获取Web版默认配置"""
    return WebConfig()

def load_config(config_file:str) -> WebConfig:
    """加载JSON配置文件"""
    try:
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            logger.info(f"✅ 成功加载配置文件: {config_file}")
            return WebConfig.model_validate_json(json.dumps(config))
        else:
            logger.warning(f"⚠️ 配置文件 {config_file} 不存在，使用默认配置")
            default_config = get_default_config()
            save_config(config_file, default_config)
            return default_config
            
    except json.JSONDecodeError as e:
        logger.error(f"❌ 配置文件格式错误: {e}")
        logger.info("使用默认配置并备份错误文件")
        
        if os.path.exists(config_file):
            backup_name = f"{config_file}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            os.rename(config_file, backup_name)
            logger.info(f"错误配置文件已备份为: {backup_name}")
        
        default_config = get_default_config()
        save_config(config_file, default_config)
        return default_config
        
    except Exception as e:
        logger.error(f"❌ 加载配置文件失败: {e}")
        return get_default_config()
    
def save_config(config_file:str, config:WebConfig):
    """保存配置到文件"""
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config.model_dump(), f, ensure_ascii=False, indent=4)
        logger.info(f"✅ 配置文件已保存: {config_file}")
    except Exception as e:
        logger.error(f"❌ 保存配置文件失败: {e}")