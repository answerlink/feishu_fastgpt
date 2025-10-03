#!/usr/bin/env python3
"""
VLM (Vision Language Model) 服务工具类

用于调用VLM API获取图片描述
"""

import aiohttp
import base64
import hashlib
import json
import os
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
        
        # 缓存文件路径
        self.cache_file = Path("temp/vlm_cache.json")
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
        """检查VLM服务是否启用
        
        通过检查4个VLM相关配置是否都存在来判断是否启用
        """
        return all([
            self.api_url,
            self.api_key,
            self.model,
            self.prompt
        ])
    
    def _load_cache(self) -> Dict[str, str]:
        """加载缓存文件
        
        Returns:
            Dict[str, str]: 图片路径到描述的映射
        """
        try:
            if not self.cache_file.exists():
                return {}
            
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                return cache_data.get('descriptions', {})
        except Exception as e:
            logger.warning(f"加载VLM缓存失败: {str(e)}")
            return {}
    
    def _save_cache(self, cache_data: Dict[str, str]) -> None:
        """保存缓存文件
        
        Args:
            cache_data: 图片路径到描述的映射
        """
        try:
            # 确保目录存在
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 保存缓存数据
            cache_content = {
                'descriptions': cache_data,
                'last_updated': str(Path().cwd())  # 可以添加时间戳等元数据
            }
            
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_content, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.warning(f"保存VLM缓存失败: {str(e)}")
    
    def _get_cache_key(self, image_path: str) -> str:
        """生成缓存键（图片内容哈希）
        
        Args:
            image_path: 图片路径
            
        Returns:
            str: 基于图片内容的SHA256哈希
        """
        try:
            image_file = Path(image_path)
            if not image_file.exists():
                return str(image_file)
            hasher = hashlib.sha256()
            with open(image_file, 'rb') as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b''):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception:
            # 退化为路径，确保不抛异常
            return str(image_path)
    
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
        """获取图片描述（带缓存）
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            str: 图片描述，失败返回None
        """
        if not self.is_enabled():
            logger.debug("VLM服务未启用，跳过图片描述获取")
            return None
        
        # 检查缓存
        cache_key = self._get_cache_key(image_path)
        cache_data = self._load_cache()
        
        if cache_key in cache_data:
            cached_description = cache_data[cache_key]
            logger.debug(f"使用缓存图片描述: {image_path} -> {cached_description}")
            return cached_description
        
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
                "temperature": 0.1,
                "enable_thinking": False,
                "chat_template_kwargs": {
                    "enable_thinking": False
                }
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
                    
                    # 保存到缓存
                    cache_data[cache_key] = description
                    self._save_cache(cache_data)
                    logger.debug(f"已保存图片描述到缓存: {image_path}")
                    
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