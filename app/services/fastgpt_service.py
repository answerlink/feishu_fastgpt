import aiohttp
import json
from typing import Optional, Dict, List, Any
from app.core.config import settings
from app.core.logger import setup_logger
from datetime import datetime

logger = setup_logger("fastgpt_service")

class FastGPTService:
    """FastGPT知识库服务
    
    实现与FastGPT平台的交互，包括知识库的创建、获取和管理等功能
    """
    
    def __init__(self, app_id: str):
        """初始化FastGPT服务
        
        Args:
            app_id: 应用ID，用于获取对应的FastGPT配置
        """
        # 获取应用配置
        self.app_config = next((app for app in settings.FEISHU_APPS if app.app_id == app_id), None)
        if not self.app_config:
            raise ValueError(f"未找到应用配置: {app_id}")
            
        self.base_url = self.app_config.fastgpt_url
        self.api_key = self.app_config.fastgpt_key
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
    
    async def _request(self, method: str, path: str, data: dict = None) -> dict:
        """发送请求到FastGPT API
        
        Args:
            method: 请求方法，如GET、POST等
            path: API路径
            data: 请求数据
            
        Returns:
            dict: API响应数据
        """
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with self.client.request(method, url, headers=headers, json=data) as response:
                response_data = await response.json()
                
                if response.status != 200 or response_data.get("code") != 200:
                    logger.error(f"FastGPT API请求失败: {response.status} - {json.dumps(response_data)}")
                    return {
                        "code": response_data.get("code", response.status),
                        "message": response_data.get("message", "请求失败"),
                        "data": None
                    }
                
                return response_data
        except Exception as e:
            logger.error(f"FastGPT API请求异常: {str(e)}")
            return {
                "code": 500,
                "message": f"请求异常: {str(e)}",
                "data": None
            }
    
    async def create_folder(self, name: str, parent_id: str = None) -> dict:
        """创建知识库文件夹
        
        Args:
            name: 文件夹名称
            parent_id: 父文件夹ID，可选
            
        Returns:
            dict: 创建结果，包含新文件夹ID
        """
        data = {
            "parentId": parent_id,
            "name": name,
            "type": "folder",
            "avatar": "/imgs/files/folder.svg",
            "intro": ""
        }
        
        result = await self._request("POST", "/api/core/dataset/create", data)
        
        if result.get("code") == 200:
            logger.info(f"成功创建知识库文件夹: {name}, ID: {result.get('data')}")
        else:
            logger.error(f"创建知识库文件夹失败: {name}, 错误: {result.get('message')}")
            
        return result
    
    async def create_dataset(self, name: str, intro: str = "", parent_id: str = None) -> dict:
        """创建知识库
        
        Args:
            name: 知识库名称
            intro: 知识库介绍
            parent_id: 父文件夹ID，可选
            
        Returns:
            dict: 创建结果，包含新知识库ID
        """
        # 从应用配置中获取模型信息
        vector_model = self.app_config.vector_model
        agent_model = self.app_config.agent_model
        vlm_model = self.app_config.vlm_model

        data = {
            "parentId": parent_id,
            "type": "dataset",
            "avatar": "/icon/logo.svg",
            "name": name,
            "intro": intro,
            "vectorModel": vector_model,
            "agentModel": agent_model,
            "vlmModel": vlm_model
        }
        
        result = await self._request("POST", "/api/core/dataset/create", data)
        
        if result.get("code") == 200:
            logger.info(f"成功创建知识库: {name}, ID: {result.get('data')}, vector_model: {vector_model}, agent_model: {agent_model}, vlm_model: {vlm_model}")
        else:
            logger.error(f"创建知识库失败: {name}, 错误: {result.get('message')}")
            
        return result
    
    async def get_dataset_list(self, parent_id: str = None) -> dict:
        """获取知识库列表
        
        Args:
            parent_id: 父文件夹ID，可选。如不提供，获取根目录下的知识库和文件夹
            
        Returns:
            dict: 知识库列表
        """
        data = {
            "parentId": parent_id or ""
        }
        
        result = await self._request("POST", "/api/core/dataset/list", data)
        
        if result.get("code") == 200:
            datasets = result.get("data", [])
            logger.info(f"成功获取知识库列表，共 {len(datasets)} 项")
        else:
            logger.error(f"获取知识库列表失败: {result.get('message')}")
            
        return result
    
    async def find_or_create_dataset(self, name: str, parent_id: str = None) -> Optional[str]:
        """查找或创建知识库
        
        先尝试在指定位置查找同名知识库，如果不存在则创建新的知识库
        
        Args:
            name: 知识库名称
            parent_id: 父文件夹ID，可选
            
        Returns:
            Optional[str]: 知识库ID，如查找和创建都失败则返回None
        """
        # 获取当前知识库列表
        list_result = await self.get_dataset_list(parent_id)
        
        if list_result.get("code") != 200:
            return None
            
        # 查找同名知识库
        datasets = list_result.get("data", [])
        for dataset in datasets:
            if dataset.get("name") == name and dataset.get("type") == "dataset":
                logger.info(f"找到已存在的知识库: {name}, ID: {dataset.get('_id')}")
                return dataset.get("_id")
        
        # 如果没找到，创建新知识库
        create_result = await self.create_dataset(name, parent_id=parent_id)
        
        if create_result.get("code") == 200:
            return create_result.get("data")
            
        return None
    
    async def upload_file_to_dataset(self, dataset_id: str, file_path: str, parent_id: str = None, chunk_size: int = 512) -> dict:
        """上传本地文件到知识库
        
        Args:
            dataset_id: 知识库ID
            file_path: 本地文件路径
            parent_id: 父文件夹ID，可选
            chunk_size: 分块大小，默认512
            
        Returns:
            dict: 上传结果
        """
        import os
        import aiofiles
        import aiohttp
        from aiohttp import FormData
        
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            return {
                "code": 400,
                "message": f"文件不存在: {file_path}",
                "data": None
            }
        
        url = f"{self.base_url}/api/core/dataset/collection/create/localFile"
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        
        # 准备表单数据
        form_data = FormData()
        form_data.add_field('file', 
                            open(file_path, 'rb'),
                            filename=os.path.basename(file_path))
        
        # 准备JSON数据
        data_json = {
            "datasetId": dataset_id,
            "parentId": "",
            "trainingType": "chunk",
            "chunkSize": chunk_size,
            "chunkSplitter": "",
            "qaPrompt": "",
            "metadata": {}  # 使用空对象
        }
        
        form_data.add_field('data', json.dumps(data_json))
        
        logger.info(f"准备上传文件到知识库: file={file_path}, dataset_id={dataset_id}")
        
        try:
            # 创建一个新的session而不使用self.client以避免内容类型冲突
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, data=form_data) as response:
                    result = await response.json()
                    
                    if response.status != 200 or result.get("code") != 200:
                        logger.error(f"上传文件到知识库失败: {response.status} - {json.dumps(result)}")
                        return {
                            "code": result.get("code", response.status),
                            "message": result.get("message", "上传失败"),
                            "data": None
                        }
                    
                    logger.info(f"成功上传文件到知识库: {file_path}, 结果: {result}")
                    return result
        except Exception as e:
            logger.error(f"上传文件到知识库异常: {str(e)}")
            return {
                "code": 500,
                "message": f"上传异常: {str(e)}",
                "data": None
            }
    
    async def check_collection_exists(self, collection_id: str) -> dict:
        """检查知识库中的文档是否存在
        
        Args:
            collection_id: 文档在FastGPT中的ID
            
        Returns:
            dict: 检查结果，包含exists字段表示文档是否存在
        """
        try:
            url = f"{self.base_url}/api/core/dataset/collection/detail"
            params = {
                "id": collection_id
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}"
            }
            
            async with self.client.get(url, params=params, headers=headers) as response:
                result = await response.json()
                if result.get("code") == 200:
                    logger.info(f"FastGPT文档存在: collection_id={collection_id}")
                    return {
                        "code": 0,
                        "exists": True,
                        "data": result.get("data")
                    }
                elif result.get("code") == 500 and "not found" in str(result.get("message", "")).lower():
                    # 文档不存在
                    logger.info(f"FastGPT文档不存在: collection_id={collection_id}")
                    return {
                        "code": 0,
                        "exists": False,
                        "data": None
                    }
                else:
                    logger.error(f"检查FastGPT文档存在性失败: collection_id={collection_id}, error={result}")
                    return {
                        "code": -1,
                        "exists": False,
                        "msg": f"检查文档存在性失败: {result.get('message', '未知错误')}"
                    }
        except Exception as e:
            logger.error(f"检查FastGPT文档存在性异常: collection_id={collection_id}, error={str(e)}")
            return {
                "code": -1,
                "exists": False,
                "msg": f"检查文档存在性异常: {str(e)}"
            }
    
    async def delete_document_from_dataset(self, collection_id: str) -> dict:
        """删除知识库中的文档
        
        Args:
            collection_id: 文档在FastGPT中的ID
            
        Returns:
            dict: 删除结果
        """
        try:
            url = f"{self.base_url}/api/core/dataset/collection/delete"
            params = {
                "id": collection_id
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}"
            }
            
            async with self.client.delete(url, params=params, headers=headers) as response:
                result = await response.json()
                if result.get("code") == 200:
                    logger.info(f"成功删除FastGPT文档: collection_id={collection_id}")
                    return {
                        "code": 0,
                        "msg": "删除文档成功"
                    }
                else:
                    logger.error(f"删除FastGPT文档失败: collection_id={collection_id}, error={result}")
                    return {
                        "code": -1,
                        "msg": f"删除文档失败: {result.get('message', '未知错误')}"
                    }
        except Exception as e:
            logger.error(f"删除FastGPT文档异常: collection_id={collection_id}, error={str(e)}")
            return {
                "code": -1,
                "msg": f"删除文档异常: {str(e)}"
            }
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口，确保关闭客户端会话"""
        await self.close()
        
    def __del__(self):
        """析构函数，确保客户端会话被关闭"""
        if hasattr(self, '_client') and self._client and not self._client.closed:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.close())
                else:
                    loop.run_until_complete(self.close())
            except Exception as e:
                logger.error(f"关闭客户端会话异常: {str(e)}") 