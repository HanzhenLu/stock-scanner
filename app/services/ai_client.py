import pandas as pd
import time
from typing import Optional

from app.logger import logger
from app.utils.sse_manager import StreamingSender
from app.utils.config import GenerationConfig
from app.services.prompt_builder import build_enhanced_ai_analysis_prompt, build_K_graph_table_prompt, build_news_section, \
                                        build_news_summary_prompt, build_value_prompt

def generate_ai_analysis(analysis_data:dict, generation_config:GenerationConfig,
                         enable_streaming:bool=False, streamer:StreamingSender=None) -> str:
    """生成AI增强分析 - 支持流式输出"""
    try:
        logger.info("🤖 开始AI深度分析...")
        
        stock_code = analysis_data['stock_code']
        stock_name = analysis_data['stock_name']
        scores = analysis_data['scores']
        technical_analysis = analysis_data['technical_analysis']
        fundamental_data = analysis_data['fundamental_data']
        sentiment_analysis = analysis_data['sentiment_analysis']
        price_info = analysis_data['price_info']
        
        no_thinking_config = generation_config.model_copy()
        no_thinking_config.extra_parm = {"chat_template_kwargs": {"enable_thinking": False}}
        K_graph_conclusion = k_graph_analysis(stock_name, analysis_data['k_graph_table'], no_thinking_config)
        news_summary = news_summarize(stock_name, sentiment_analysis, no_thinking_config)
        value_analysis = value_analyze(stock_code, stock_name, fundamental_data, price_info, no_thinking_config, streamer)
        
        # 构建增强版AI分析提示词
        prompt = build_enhanced_ai_analysis_prompt(
            stock_code, stock_name, scores, technical_analysis, 
            fundamental_data, news_summary, price_info, K_graph_conclusion, value_analysis,
            analysis_data["avg_price"], analysis_data["position_percent"]
        )
        streamer.send_prompt("llm-prompt", prompt)
        
        # 设置AI流式内容处理
        ai_content_buffer = ""
        
        def ai_stream_callback(content):
            """AI流式内容回调"""
            nonlocal ai_content_buffer
            ai_content_buffer += content
            # 实时发送AI流式内容
            streamer.send_ai_stream(content)
        
        # 调用AI API（支持流式）
        ai_response = _call_ai_api(prompt, generation_config, enable_streaming, ai_stream_callback)
        
        if ai_response:
            logger.info("✅ AI深度分析完成")
            return ai_response
        else:
            logger.warning("⚠️ AI API不可用，使用高级分析模式")
            return None
            
    except Exception as e:
        logger.error(f"AI分析失败: {e}")
        return None
    
def k_graph_analysis(stock_name:str, price_data:pd.DataFrame, generation_config:GenerationConfig) -> str:
    prompt = build_K_graph_table_prompt(stock_name, price_data)
    ai_response = _call_ai_api(prompt, generation_config)
    if ai_response:
        logger.info("✅ K graph表格读取完成")
        return ai_response
    else:
        logger.warning("⚠️ K graph表格读取失败")
        return None
    
def news_summarize(stock_name:str, sentiment_analysis:dict, generation_config:GenerationConfig) -> str:
    news_text = build_news_section(
        sentiment_analysis.get('company_news', []),
        sentiment_analysis.get('research_reports', [])
    )
    prompt = build_news_summary_prompt(stock_name, news_text)
    ai_response = _call_ai_api(prompt, generation_config)
    if ai_response:
        logger.info("✅ 新闻总结完成")
        return ai_response
    else:
        logger.warning("⚠️ 新闻总结失败")
        return None
    
def value_analyze(stock_code:str, stock_name:str, fundamental_data:dict, price_info:dict, generation_config:GenerationConfig, streamer:StreamingSender) -> str:
    prompt = build_value_prompt(stock_code, stock_name, fundamental_data, price_info)
    streamer.send_prompt("value-prompt", prompt)
    ai_response = _call_ai_api(prompt, generation_config)
    if ai_response:
        logger.info("✅ 价值分析完成")
        return ai_response
    else:
        logger.warning("⚠️ 价值分析失败")
        return None

def _call_ai_api(prompt: str, generation_config: GenerationConfig, 
                 enable_streaming: bool = False, stream_callback = None) -> Optional[str]:
    """调用AI API - 支持流式输出，失败时最多重试2次，共尝试3次"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if generation_config.server_name == 'openai':
                result = _call_openai_api(prompt, generation_config, enable_streaming, stream_callback)
                if result is not None:
                    return result

            elif generation_config.server_name == 'anthropic':
                result = _call_claude_api(prompt, generation_config, enable_streaming, stream_callback)
                if result is not None:
                    return result
                
            elif generation_config.server_name == 'zhipu':
                result = _call_zhipu_api(prompt, generation_config, enable_streaming, stream_callback)
                if result is not None:
                    return result

            # 如果返回了 None，也视为失败，进行重试
            logger.warning(f"API 调用返回 None，第 {attempt + 1} 次尝试失败，正在重试...")

        except Exception as e:
            logger.error(f"AI API调用异常（第 {attempt + 1} 次尝试）: {e}")
            time.sleep(1)
        
        # 如果不是最后一次尝试，等待一段时间再重试（指数退避可选）
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)  # 可选：加入指数退避
        else:
            logger.error("已尝试 3 次，全部失败，放弃重试。")
    
    return None

def _call_openai_api(prompt:str, generation_config:GenerationConfig, 
                     enable_streaming:bool=False, stream_callback:bool=None) -> str:
    """调用OpenAI API - 支持流式输出"""
    try:
        import openai
        
        logger.info(f"正在调用OpenAI {generation_config.model_name} 进行深度分析...")
        
        messages = [
            {"role": "system", "content": "你是一位资深的股票分析师，具有丰富的市场经验和深厚的金融知识。请提供专业、客观、有深度的股票分析。"},
            {"role": "user", "content": prompt}
        ]
        
        # 检测OpenAI库版本并使用相应的API
        try:
            client = openai.OpenAI(api_key=generation_config.api_key)
            if generation_config.api_base_url:
                client.base_url = generation_config.api_base_url
            
            if enable_streaming and stream_callback:
                # 流式调用
                response = client.chat.completions.create(
                    model=generation_config.model_name,
                    messages=messages,
                    max_tokens=generation_config.max_tokens,
                    temperature=generation_config.temperature,
                    stream=True,
                    extra_body=generation_config.extra_parm
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
                    model=generation_config.model_name,
                    messages=messages,
                    max_tokens=generation_config.max_tokens,
                    temperature=generation_config.temperature,
                    extra_body=generation_config.extra_parm
                )
                return response.choices[0].message.content
                
        except Exception as api_error:
            logger.error(f"OpenAI API调用错误: {api_error}")
            return None
            
    except ImportError:
        logger.error("OpenAI库未安装")
        return None
    except Exception as e:
        logger.error(f"OpenAI API调用失败: {e}")
        return None

def _call_claude_api(prompt:str, generation_config:GenerationConfig,
                     enable_streaming:bool=False, stream_callback:bool=None) -> str:
    """调用Claude API - 支持流式输出"""
    try:
        import anthropic
        
        client = anthropic.Anthropic(api_key=generation_config.api_key)
        
        logger.info(f"正在调用Claude {generation_config.model_name} 进行深度分析...")
        
        messages = [
            {"role": "system", "content": "你是一位资深的股票分析师，具有丰富的市场经验和深厚的金融知识。请提供专业、客观、有深度的股票分析。"},
            {"role": "user", "content": prompt}
        ]
        
        if enable_streaming and stream_callback:
            # 流式调用
            with client.messages.stream(
                model=generation_config.model_name,
                max_tokens=generation_config.max_tokens,
                messages=messages
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
                model=generation_config.model_name,
                max_tokens=generation_config.max_tokens,
                messages=messages
            )
            
            return response.content[0].text
        
    except Exception as e:
        logger.error(f"Claude API调用失败: {e}")
        return None

def _call_zhipu_api(prompt:str, generation_config:GenerationConfig, enable_streaming:bool=False, stream_callback:bool=None) -> str:
    """调用智谱AI API - 支持流式输出"""
    try:
        import zhipuai
        
        client = zhipuai.ZhipuAI(api_key=generation_config.api_key)
        
        logger.info(f"正在调用智谱AI {generation_config.model_name} 进行深度分析...")
        
        messages = [
            {"role": "system", "content": "你是一位资深的股票分析师，具有丰富的市场经验和深厚的金融知识。请提供专业、客观、有深度的股票分析。"},
            {"role": "user", "content": prompt}
        ]
        
        try:
            if enable_streaming and stream_callback:
                # 流式调用
                response = client.chat.completions.create(
                    model=generation_config.model_name,
                    messages=messages,
                    temperature=generation_config.temperature,
                    max_tokens=generation_config.max_tokens,
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
                    model=generation_config.model_name,
                    messages=messages,
                    temperature=generation_config.temperature,
                    max_tokens=generation_config.max_tokens
                )
                return response.choices[0].message.content
                
        except Exception as api_error:
            logger.error(f"智谱AI API调用错误: {api_error}")
            return None

    except ImportError:
        logger.error("智谱AI库未安装")
        return None
        
    except Exception as e:
        logger.error(f"智谱AI API调用失败: {e}")
        return None