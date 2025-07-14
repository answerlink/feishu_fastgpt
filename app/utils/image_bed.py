#!/usr/bin/env python3
"""
图床工具类

用于处理飞书文档中的图片，包括下载、存储和URL生成
"""

import os
import uuid
import re
import time
from pathlib import Path
from typing import Dict, Optional
from app.core.logger import setup_logger

logger = setup_logger("image_bed")

class ImageBed:
    """图床管理类"""
    
    def __init__(self, base_dir: str = "static/images"):
        """初始化图床
        
        Args:
            base_dir: 图片存储基础目录
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
    def generate_image_filename(self, original_token: str = None) -> str:
        """生成图片文件名（短UUID + 时间戳）
        
        Args:
            original_token: 原始图片token（可选，仅用于日志）
            
        Returns:
            str: 新的文件名（不含扩展名）
        """
        # 使用时间戳（秒级）+ 短UUID（8位）生成更短的文件名
        timestamp = hex(int(time.time()))[2:]  # 去掉0x前缀
        short_uuid = str(uuid.uuid4()).replace('-', '')[:8]
        new_filename = f"{timestamp}{short_uuid}"
        
        if original_token:
            logger.info(f"生成新图片文件名: {original_token} -> {new_filename}")
        return new_filename
    
    def get_image_path(self, filename: str, extension: str = "png") -> Path:
        """获取图片完整路径
        
        Args:
            filename: 文件名（不含扩展名）
            extension: 文件扩展名，默认png
            
        Returns:
            Path: 图片完整路径
        """
        return self.base_dir / f"{filename}.{extension}"
    
    def get_image_url(self, filename: str, extension: str = "png", use_short_path: bool = True) -> str:
        """获取图片访问URL
        
        Args:
            filename: 文件名（不含扩展名）
            extension: 文件扩展名，默认png
            use_short_path: 是否使用短路径，True使用/img/，False使用/static/images/
            
        Returns:
            str: 图片访问URL
        """
        if use_short_path:
            return f"/img/{filename}.{extension}"
        else:
            return f"/static/images/{filename}.{extension}"
    
    async def download_and_store_image(self, feishu_service, app_id: str, image_token: str) -> Optional[Dict[str, str]]:
        """下载并存储图片
        
        Args:
            feishu_service: 飞书服务实例
            app_id: 应用ID
            image_token: 图片token
            
        Returns:
            Dict[str, str]: 包含filename、url、path等信息，失败返回None
        """
        try:
            # 生成新的文件名
            filename = self.generate_image_filename(image_token)
            
            # 默认使用png扩展名，后续可以根据实际图片类型调整
            extension = "png"
            image_path = self.get_image_path(filename, extension)
            
            # 下载图片
            download_result = await feishu_service.download_image(
                app_id=app_id,
                image_token=image_token,
                output_path=str(image_path)
            )
            
            if download_result.get("code") != 0:
                logger.error(f"下载图片失败: image_token={image_token}, error={download_result.get('msg')}")
                return None
            
            # 检查文件是否存在
            if not image_path.exists():
                logger.error(f"图片下载后文件不存在: {image_path}")
                return None
            
            file_size = image_path.stat().st_size
            short_url = self.get_image_url(filename, extension, use_short_path=True)
            legacy_url = self.get_image_url(filename, extension, use_short_path=False)
            
            logger.info(f"成功下载并存储图片: {image_token} -> {filename}.{extension}, 大小: {file_size}字节")
            
            return {
                "original_token": image_token,
                "filename": filename,
                "extension": extension,
                "path": str(image_path),
                "short_url": short_url,  # 短路径URL
                "legacy_url": legacy_url,  # 兼容性长路径URL
                "size": file_size
            }
            
        except Exception as e:
            logger.error(f"下载并存储图片异常: image_token={image_token}, error={str(e)}")
            return None
    
    def process_markdown_images(self, markdown_content: str, image_mapping: Dict[str, str]) -> str:
        """处理Markdown中的图片链接
        
        Args:
            markdown_content: 原始Markdown内容
            image_mapping: 图片token到新URL的映射 {original_token: new_url}
            
        Returns:
            str: 处理后的Markdown内容
        """
        def replace_image(match):
            # 提取图片token
            original_url = match.group(2)
            
            # 从URL中提取image_token
            # URL格式: /api/v1/documents/None/image/VB8EbvcnRoWeAbxjg4bcTki5n1c/download
            token_match = re.search(r'/image/([^/]+)/download', original_url)
            if not token_match:
                logger.warning(f"无法从URL中提取图片token，清空图片链接避免飞书安全错误: {original_url}")
                return f"![]()"  # 清空图片URL，避免飞书外链安全错误
            
            image_token = token_match.group(1)
            
            # 查找对应的新URL
            if image_token in image_mapping:
                new_url = image_mapping[image_token]
                # 返回新的图片链接，描述为空
                return f"![]({new_url})"
            else:
                logger.warning(f"未找到图片token的映射，清空图片链接避免飞书安全错误: {image_token}")
                return f"![]()"  # 清空图片URL，避免飞书外链安全错误
        
        # 匹配Markdown图片格式: ![描述](URL)
        pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        processed_content = re.sub(pattern, replace_image, markdown_content)
        
        return processed_content
    
    async def process_document_images(self, feishu_service, app_id: str, doc_token: str, markdown_content: str) -> str:
        """处理文档中的所有图片
        
        Args:
            feishu_service: 飞书服务实例
            app_id: 应用ID
            doc_token: 文档token
            markdown_content: 原始Markdown内容
            
        Returns:
            str: 处理后的Markdown内容
        """
        try:
            # 从Markdown内容中提取所有图片token
            image_tokens = self.extract_image_tokens_from_markdown(markdown_content)
            
            if not image_tokens:
                logger.info(f"文档中没有图片: doc_token={doc_token}")
                return markdown_content
            
            logger.info(f"文档中发现{len(image_tokens)}张图片: doc_token={doc_token}")
            
            # 下载并存储所有图片
            image_mapping = {}
            for image_token in image_tokens:
                image_info = await self.download_and_store_image(feishu_service, app_id, image_token)
                if image_info:
                    image_mapping[image_token] = image_info["short_url"]
                else:
                    logger.error(f"处理图片失败: {image_token}")
            
            # 替换Markdown中的图片链接
            processed_content = self.process_markdown_images(markdown_content, image_mapping)
            
            logger.info(f"成功处理文档图片: doc_token={doc_token}, 成功处理{len(image_mapping)}/{len(image_tokens)}张图片")
            
            return processed_content
            
        except Exception as e:
            logger.error(f"处理文档图片异常: doc_token={doc_token}, error={str(e)}")
            return markdown_content  # 出错时返回原始内容
    
    def extract_image_tokens_from_markdown(self, markdown_content: str) -> list:
        """从Markdown内容中提取图片token
        
        Args:
            markdown_content: Markdown内容
            
        Returns:
            list: 图片token列表
        """
        tokens = []
        
        # 匹配图片URL并提取token
        pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        matches = re.findall(pattern, markdown_content)
        
        for description, url in matches:
            # 从URL中提取image_token
            token_match = re.search(r'/image/([^/]+)/download', url)
            if token_match:
                tokens.append(token_match.group(1))
        
        return list(set(tokens))  # 去重

# 全局图床实例
image_bed = ImageBed() 