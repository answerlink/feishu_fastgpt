#!/usr/bin/env python3
"""
VLM (Vision Language Model) 服务工具类

用于调用VLM API获取图片描述
"""

import aiohttp
import base64
from pathlib import Path
from typing import Optional, Dict, Any
from app.core.logger import setup_logger
from app.core.config import settings

logger = setup_logger("vlm_service")

class VLMService:
    """VLM图片描述服务"""
    
    def __init__(self, app_id: str):
        """初始化VLM服务
        
        Args:
            app_id: 应用ID，用于获取对应的VLM配置
        """
        # 获取应用配置
        self.app_config = next((app for app in settings.FEISHU_APPS if app.app_id == app_id), None)
        if not self.app_config:
            raise ValueError(f"未找到应用配置: {app_id}")
            
        self.api_url = getattr(self.app_config, 'image_bed_vlm_api_url', None)
        self.api_key = getattr(self.app_config, 'image_bed_vlm_api_key', None)
        self.model = getattr(self.app_config, 'image_bed_vlm_model', '')
        self.prompt = getattr(self.app_config, 'image_bed_vlm_model_prompt', '请用20字以内简洁描述这张图片内容，不要加任何前缀，直接给出描述，参考论文引用图例的格式。')
        self.enabled = getattr(self.app_config, 'image_bed_vlm_enable', False)
        
        self._client = None
    
    @property
    def client(self):
        """懒加载客户端会话"""
        if self._client is None or self._client.closed:
            self._client = aiohttp.ClientSession()
        return self._client
    
    async def close(self):
        """关闭客户端会话"""
        if self._client and not self._client.closed:
            await self._client.close()
            self._client = None
    
    def is_enabled(self) -> bool:
        """检查VLM服务是否启用"""
        return self.enabled and self.api_url and self.api_key
    
    def _encode_image_to_base64(self, image_path: str) -> Optional[str]:
        """将图片文件编码为base64
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            str: base64编码的图片数据，失败返回None
        """
        try:
            image_file = Path(image_path)
            if not image_file.exists():
                logger.error(f"图片文件不存在: {image_path}")
                return None
            
            with open(image_file, "rb") as f:
                image_data = f.read()
            
            # 获取文件扩展名来确定MIME类型
            extension = image_file.suffix.lower()
            mime_type_map = {
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.gif': 'image/gif',
                '.webp': 'image/webp'
            }
            mime_type = mime_type_map.get(extension, 'image/png')
            
            # 编码为base64
            base64_data = base64.b64encode(image_data).decode('utf-8')
            return f"data:{mime_type};base64,{base64_data}"
            
        except Exception as e:
            logger.error(f"图片编码失败: {image_path}, 错误: {str(e)}")
            return None
    
    async def get_image_description(self, image_path: str) -> Optional[str]:
        """获取图片描述
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            str: 图片描述，失败返回None
        """
        if not self.is_enabled():
            logger.debug("VLM服务未启用，跳过图片描述获取")
            return None
        
        try:
            # 编码图片
            base64_image = self._encode_image_to_base64(image_path)
            if not base64_image:
                return None
            
            # 构建请求数据
            request_data = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": self.prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": base64_image
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 100,
                "temperature": 0.1
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            logger.debug(f"调用VLM API获取图片描述: {image_path}")
            
            async with self.client.post(self.api_url, json=request_data, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"VLM API调用失败: status={response.status}, error={error_text}")
                    return None
                
                result = await response.json()
                
                # 解析响应
                if "choices" in result and len(result["choices"]) > 0:
                    description = result["choices"][0]["message"]["content"].strip()
                    logger.info(f"成功获取图片描述: {image_path} -> {description}")
                    return description
                else:
                    logger.error(f"VLM API响应格式异常: {result}")
                    return None
                    
        except Exception as e:
            logger.error(f"获取图片描述异常: {image_path}, 错误: {str(e)}")
            return None
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close() 