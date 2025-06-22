from typing import Dict, List, Optional
from pydantic import BaseModel
import json
from pathlib import Path

class FeishuApp(BaseModel):
    """飞书应用配置"""
    app_id: str
    app_secret: str
    app_name: str = ""  # 应用名称，可选
    dataset_sync: bool = True  # 是否启用数据集同步功能，默认启用
    fastgpt_url: Optional[str] = None  # FastGPT API地址，可选
    fastgpt_key: Optional[str] = None  # FastGPT API密钥，可选
    vector_model: Optional[str] = None # FastGPT vector_model，可选
    agent_model: Optional[str] = None  # FastGPT agent_model，可选
    vlm_model: Optional[str] = None  # FastGPT vlm_model，可选
    
    # 摘要LLM相关配置
    summary_llm_api_url: Optional[str] = None  # 摘要LLM API地址
    summary_llm_api_key: Optional[str] = None  # 摘要LLM API密钥
    summary_llm_model: Optional[str] = None  # 摘要LLM模型
    
    # 图床相关配置
    image_bed_base_url: Optional[str] = None  # 图床基础URL
    image_bed_vlm_api_url: Optional[str] = None  # VLM API地址
    image_bed_vlm_api_key: Optional[str] = None  # VLM API密钥
    image_bed_vlm_model: Optional[str] = None  # VLM模型
    image_bed_vlm_model_prompt: Optional[str] = None  # VLM提示词
    
    # AI Chat相关配置
    aichat_enable: Optional[bool] = False  # 是否启用AI Chat功能
    aichat_url: Optional[str] = None  # AI Chat API地址
    aichat_key: Optional[str] = None  # AI Chat API密钥
    aichat_support_stop_streaming: Optional[bool] = False  # 是否支持停止流式回答
    aichat_client_download_host: Optional[str] = None  # AI Chat读取集合API地址
    aichat_read_collection_url: Optional[str] = None  # AI Chat读取集合API地址
    aichat_read_collection_key: Optional[str] = None  # AI Chat读取集合API密钥
    asr_api_url: Optional[str] = None  # ASR API地址
    asr_api_key: Optional[str] = None  # ASR API密钥
    aichat_reply_p2p: Optional[bool] = True  # 是否在私聊中回复
    aichat_reply_group: Optional[bool] = False  # 是否在群聊中回复
    user_memory_enable: Optional[bool] = True  # 是否启用用户记忆功能

class Settings(BaseModel):
    """应用配置"""
    # 应用配置
    APP_NAME: str = "feishu-plus"
    DEBUG: bool = False
    API_V1_STR: str = "/api/v1"
    
    # 数据库配置
    DB_HOST: str
    DB_PORT: int
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str
    SQLALCHEMY_ECHO: bool = False  # 是否打印SQL语句
    SQLALCHEMY_POOL_SIZE: int = 5  # 连接池大小
    SQLALCHEMY_POOL_TIMEOUT: int = 10  # 连接超时时间
    SQLALCHEMY_POOL_RECYCLE: int = 3600  # 连接回收时间
    
    # 飞书应用配置列表
    FEISHU_APPS: List[FeishuApp]
    
    # 飞书API配置
    FEISHU_HOST: str = "https://open.feishu.cn"
    TOKEN_EXPIRE_BUFFER: int = 300  # Token过期前5分钟刷新
    
    # FastGPT配置
    FASTGPT_ENABLED: bool = False  # 是否启用FastGPT，根据应用配置自动判断
    
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        return f"mysql+aiomysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        
    def __init__(self, **data):
        super().__init__(**data)
        # 自动判断是否启用FastGPT，只要有一个应用配置了FastGPT URL和KEY，就认为启用
        self.FASTGPT_ENABLED = any(
            app.fastgpt_url and app.fastgpt_key
            for app in self.FEISHU_APPS
        )

def get_config(env: str = "dev") -> Settings:
    """获取配置"""
    config_dir = Path(__file__).parent.parent.parent / "config"
    config_file = config_dir / f"config.{env}.json"
    
    if not config_file.exists():
        config_file = config_dir / "config.json"  # 默认配置文件
    
    if not config_file.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_file}")
    
    with open(config_file, "r", encoding="utf-8") as f:
        config_data = json.load(f)
    
    return Settings(**config_data)

settings = get_config() 