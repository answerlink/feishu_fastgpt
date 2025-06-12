from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, delete
import aiohttp
from app.core.config import settings
from app.core.logger import setup_logger
from app.models.feishu_token import FeishuToken
from app.models.doc_subscription import DocSubscription
from app.models.space_subscription import SpaceSubscription
import asyncio
import time

logger = setup_logger("feishu_service")

class FeishuService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.base_url = settings.FEISHU_HOST
        self.token_expire_buffer = settings.TOKEN_EXPIRE_BUFFER
        # 改为在每次请求时创建会话，而不是在构造函数中创建
        self._client = None
        # 支持订阅的文档类型
        self.supported_file_types = ["docx", "sheet", "file"]
        
        # 图片下载QPS限制器 (5 QPS)
        self._image_download_semaphore = asyncio.Semaphore(5)  # 同时最多5个请求
        self._last_image_download_time = 0  # 上次下载时间
        self._image_download_interval = 0.2  # 200ms间隔，确保不超过5 QPS

    @property
    def client(self):
        """懒加载客户端会话
        
        注意：在事件循环冲突的情况下，某些方法会直接使用临时的aiohttp.ClientSession()
        """
        if self._client is None or self._client.closed:
            self._client = aiohttp.ClientSession()
        return self._client

    async def get_tenant_access_token(self, app_id: str) -> str:
        """获取tenant_access_token，如果即将过期则自动刷新"""
        # 从数据库获取token
        result = await self.db.execute(
            select(FeishuToken).where(FeishuToken.app_id == app_id)
        )
        token = result.scalar_one_or_none()
        
        # 如果token不存在或即将过期，则刷新
        if not token or token.expire_time <= datetime.now() + timedelta(seconds=self.token_expire_buffer):
            token = await self._refresh_tenant_access_token(app_id)
            
        return token.tenant_access_token if token else None

    async def _refresh_tenant_access_token(self, app_id: str) -> Optional[FeishuToken]:
        """刷新tenant_access_token"""
        # 获取应用配置
        app_config = next((app for app in settings.FEISHU_APPS if app.app_id == app_id), None)
        if not app_config:
            raise ValueError(f"未找到应用配置: {app_id}")

        # 调用飞书API获取新token
        url = f"{self.base_url}/open-apis/auth/v3/tenant_access_token/internal"
        data = {
            "app_id": app_config.app_id,
            "app_secret": app_config.app_secret
        }
        
        # 使用临时的客户端会话避免事件循环冲突
        async with aiohttp.ClientSession() as client:
            async with client.post(url, json=data) as response:
                result = await response.json()
                if result.get("code") != 0:
                    raise Exception(f"获取tenant_access_token失败: {result}")
                
                # 更新数据库
                token_query = await self.db.execute(
                    select(FeishuToken).where(FeishuToken.app_id == app_id)
                )
                token = token_query.scalar_one_or_none()
                
                if not token:
                    token = FeishuToken(app_id=app_id)
                    self.db.add(token)
                
                token.tenant_access_token = result["tenant_access_token"]
                token.expire_time = datetime.now() + timedelta(seconds=result["expire"])
                await self.db.commit()
                await self.db.refresh(token)
                
                return token

    async def get_wiki_spaces(self, app_id: str, page_token: str = None) -> dict:
        """获取知识空间列表"""
        token = await self.get_tenant_access_token(app_id)
        url = f"{self.base_url}/open-apis/wiki/v2/spaces"
        
        params = {"page_size": 50}
        if page_token:
            params["page_token"] = page_token
            
        headers = {
            "Authorization": f"Bearer {token}"
        }
        
        async with self.client.get(url, params=params, headers=headers) as response:
            result = await response.json()
            if result.get("code") == 0:
                return {
                    "code": 0,
                    "data": result.get("data", {})
                }
            return {
                "code": result.get("code", -1),
                "msg": result.get("msg", "获取知识空间列表失败")
            }

    async def get_wiki_nodes(self, app_id: str, space_id: str, parent_node_token: str = None) -> dict:
        """获取知识空间节点列表
        
        支持分页查询，自动获取所有页面的数据
        
        Args:
            app_id: 应用ID
            space_id: 知识空间ID
            parent_node_token: 父节点Token，可选
            
        Returns:
            dict: 包含所有节点的数据
        """
        token = await self.get_tenant_access_token(app_id)
        url = f"{self.base_url}/open-apis/wiki/v2/spaces/{space_id}/nodes"
        
        all_items = []
        page_token = None
        
        while True:
            params = {
                "page_size": 50  # 固定设置每页50条
            }
            
            if parent_node_token:
                params["parent_node_token"] = parent_node_token
                
            if page_token:
                params["page_token"] = page_token
                
            headers = {
                "Authorization": f"Bearer {token}"
            }
            
            try:
                async with self.client.get(url, params=params, headers=headers) as response:
                    result = await response.json()
                    
                    if result.get("code") != 0:
                        logger.error(f"获取知识空间节点列表失败: space_id={space_id}, parent_node_token={parent_node_token}, error={result.get('msg')}")
                        return {
                            "code": result.get("code", -1),
                            "msg": result.get("msg", "获取知识空间节点列表失败")
                        }
                    
                    data = result.get("data", {})
                    items = data.get("items", [])
                    all_items.extend(items)
                    
                    # 检查是否还有更多页面
                    has_more = data.get("has_more", False)
                    if not has_more:
                        break
                        
                    # 获取下一页的page_token
                    page_token = data.get("page_token")
                    if not page_token:
                        break
                        
                    logger.info(f"获取知识空间节点列表第{len(all_items)//50 + 1}页: space_id={space_id}, parent_node_token={parent_node_token}, 本页{len(items)}个节点")
                    
            except Exception as e:
                logger.error(f"获取知识空间节点列表异常: space_id={space_id}, parent_node_token={parent_node_token}, error={str(e)}")
                return {
                    "code": -1,
                    "msg": f"获取知识空间节点列表异常: {str(e)}"
                }
        
        logger.info(f"成功获取知识空间节点列表: space_id={space_id}, parent_node_token={parent_node_token}, 总计{len(all_items)}个节点")
        
        return {
            "code": 0,
            "data": {
                "items": all_items,
                "total_count": len(all_items)
            }
        }

    async def get_doc_content(self, app_id: str, doc_token: str, doc_type: str = "docx", 
                              content_type: str = "markdown", lang: str = "zh", 
                              use_filtered_blocks: bool = True) -> dict:
        """获取文档内容（调用飞书API 支持docx格式飞书云文档和sheet格式电子表格）
        
        Args:
            app_id: 应用ID
            doc_token: 文档Token
            doc_type: 文档类型，如docx、sheet
            content_type: 内容类型，如markdown
            lang: 语言
            use_filtered_blocks: 是否使用我们自己实现的filtered-blocks处理逻辑，默认True
            
        Returns:
            dict: 文档内容
        """
        
        # 如果是电子表格，使用专门的处理方法
        if doc_type == "sheet":
            logger.info(f"处理电子表格文档: doc_token={doc_token}")
            return await self.get_sheet_doc_content(app_id, doc_token)
        
        # 如果使用我们自己实现的filtered-blocks处理逻辑
        if use_filtered_blocks and doc_type == "docx":
            try:
                logger.info(f"使用filtered-blocks方式获取文档内容: doc_token={doc_token}")
                
                # 获取所有文档块
                blocks_result = await self.get_all_document_blocks(app_id, doc_token)
                
                if blocks_result.get("code") != 0:
                    logger.error(f"获取文档块失败: doc_token={doc_token}, error={blocks_result.get('msg')}")
                    # 如果获取块失败，回退到原始API
                    logger.info(f"回退到原始API获取文档内容: doc_token={doc_token}")
                    return await self._get_doc_content_original_api(app_id, doc_token, doc_type, content_type, lang)
                
                # 获取文档块列表
                blocks = blocks_result.get("data", {}).get("items", [])
                total_blocks = len(blocks)
                
                logger.info(f"成功获取文档块: doc_token={doc_token}, 总块数={total_blocks}")
                
                if total_blocks == 0:
                    logger.warning(f"文档中没有块: doc_token={doc_token}")
                    return {
                        "code": 0,
                        "data": {
                            "content": "",
                            "revision": 0
                        }
                    }
                
                # 使用DocBlockFilter组织块
                from app.utils.doc_block_filter import DocBlockFilter
                from app.utils.block_to_markdown import BlockToMarkdown
                
                organized_result = DocBlockFilter.organize_blocks(blocks)
                filtered_blocks = organized_result["blocks"]
                
                # 使用BlockToMarkdown将块转换为Markdown
                markdown_content = await BlockToMarkdown.convert(filtered_blocks, app_id=app_id)
                
                # 优化Markdown内容，将HTML表格转换为标准Markdown格式
                try:
                    from app.utils.markdown_converter import optimize_markdown_content
                    optimized_content = optimize_markdown_content(markdown_content)
                    logger.info(f"成功优化Markdown内容: doc_token={doc_token}, 原始长度={len(markdown_content)}, 优化后长度={len(optimized_content)}")
                    markdown_content = optimized_content
                except Exception as e:
                    logger.warning(f"Markdown优化失败，使用原始内容: doc_token={doc_token}, 错误={str(e)}")
                
                # 注意：图片处理已经在get_all_document_blocks中完成，这里不需要重复处理
                
                logger.info(f"使用filtered-blocks成功获取文档内容: doc_token={doc_token}, 内容长度={len(markdown_content)}")
                
                return {
                    "code": 0,
                    "data": {
                        "content": markdown_content,
                        "revision": 0,  # filtered-blocks方式无法获取revision，设为0
                        "method": "filtered-blocks"
                    }
                }
                
            except Exception as e:
                logger.error(f"使用filtered-blocks获取文档内容异常: doc_token={doc_token}, error={str(e)}")
                # 如果异常，回退到原始API
                logger.info(f"回退到原始API获取文档内容: doc_token={doc_token}")
                return await self._get_doc_content_original_api(app_id, doc_token, doc_type, content_type, lang)
        
        # 使用原始飞书API
        return await self._get_doc_content_original_api(app_id, doc_token, doc_type, content_type, lang)
    
    async def _get_doc_content_original_api(self, app_id: str, doc_token: str, doc_type: str = "docx", 
                                            content_type: str = "markdown", lang: str = "zh") -> dict:
        """使用原始飞书API获取文档内容
        
        Args:
            app_id: 应用ID
            doc_token: 文档Token
            doc_type: 文档类型，如docx
            content_type: 内容类型，如markdown
            lang: 语言
            
        Returns:
            dict: 文档内容
        """
        logger.info(f"使用原始API获取文档内容: doc_token={doc_token}")
        
        token = await self.get_tenant_access_token(app_id)
        url = f"{self.base_url}/open-apis/docs/v1/content"
            
        params = {
            "doc_token": doc_token,
            "doc_type": doc_type,
            "content_type": content_type,
            "lang": lang
        }
            
        headers = {
            "Authorization": f"Bearer {token}"
        }
        
        async with self.client.get(url, params=params, headers=headers) as response:
            result = await response.json()
            if result.get("code") == 0:
                # 为原始API的返回结果添加method标识
                data = result.get("data", {})
                data["method"] = "original-api"
                
                return {
                    "code": 0,
                    "data": data
                }
            
            error_msg = result.get("msg", "获取文档内容失败")
            logger.error(f"获取文档内容失败: doc_token={doc_token}, error={error_msg}")
            
            # 检查错误消息，如果是文档被删除或无权限，则删除数据库中的记录
            if "docs deleted" in error_msg.lower() or "no permission" in error_msg.lower():
                logger.info(f"文档已被删除或无权限访问，将从数据库中删除记录: doc_token={doc_token}")
                try:
                    # 查询数据库中是否存在该记录
                    query = await self.db.execute(
                        select(DocSubscription).where(
                            DocSubscription.app_id == app_id,
                            DocSubscription.file_token == doc_token
                        )
                    )
                    doc_record = query.scalar_one_or_none()
                    
                    if doc_record:
                        # 如果文档有collection_id，先删除FastGPT中的对应知识
                        if doc_record.collection_id:
                            try:
                                # 导入FastGPT服务
                                from app.services.fastgpt_service import FastGPTService
                                
                                # 创建FastGPT服务实例
                                fastgpt_service = FastGPTService(app_id)
                                
                                # 调用删除API
                                delete_result = await fastgpt_service.delete_collection(doc_record.collection_id)
                                
                                if delete_result.get("code") == 200:
                                    logger.info(f"已从FastGPT知识库中删除无效文档: collection_id={doc_record.collection_id}")
                                else:
                                    logger.error(f"从FastGPT知识库中删除无效文档失败: collection_id={doc_record.collection_id}, error={delete_result.get('msg')}")
                                
                                # 关闭FastGPT服务
                                await fastgpt_service.close()
                                
                            except Exception as e:
                                logger.error(f"调用FastGPT删除API异常: collection_id={doc_record.collection_id}, error={str(e)}")
                        
                        # 删除数据库记录
                        await self.db.execute(
                            delete(DocSubscription).where(
                                DocSubscription.app_id == app_id,
                                DocSubscription.file_token == doc_token
                            )
                        )
                        await self.db.commit()
                        logger.info(f"已从数据库中删除无效文档记录: doc_token={doc_token}")
                except Exception as e:
                    logger.error(f"删除无效文档记录失败: doc_token={doc_token}, error={str(e)}")
            
            return {
                "code": result.get("code", -1),
                "msg": error_msg
            }

    async def subscribe_doc_events(self, app_id: str, file_token: str, file_type: str, title: str = None, space_id: str = None, obj_edit_time: str = None, hierarchy_path: str = None) -> dict:
        """订阅云文档事件
        
        使用POST方法订阅文档事件，无需指定event_type参数，API会自动订阅所有可用事件
        同时在数据库中记录订阅状态，避免重复订阅
        
        Args:
            app_id: 应用ID
            file_token: 文档Token
            file_type: 文档类型，如docx、sheet、bitable、file
            title: 文档标题（可选）
            space_id: 所属知识空间ID（可选）
            obj_edit_time: 文档最后编辑时间（可选）
            hierarchy_path: 文档层级路径（可选），使用###分隔
            
        Returns:
            dict: 订阅结果
        """
        
        # 过滤掉标题为空或"未命名"的文档
        if not title or title.strip() == "" or title.strip() == "未命名":
            logger.info(f"文档标题为空或未命名，跳过订阅: file_token={file_token}, title={title}")
            return {
                "code": 0,
                "msg": "文档标题为空或未命名，跳过订阅",
                "data": {"skipped": True}
            }

        # 检查文件类型是否支持
        if file_type not in self.supported_file_types:
            return {
                "code": -1,
                "msg": f"不支持的文件类型: {file_type}，目前仅支持: {', '.join(self.supported_file_types)}"
            }
        
        # 先查询数据库，检查是否存在记录（无论状态如何）
        query = await self.db.execute(
            select(DocSubscription).where(
                DocSubscription.app_id == app_id,
                DocSubscription.file_token == file_token
            )
        )
        existing = query.scalar_one_or_none()
        
        # 统一解析obj_edit_time为datetime对象
        edit_time = None
        if obj_edit_time:
            try:
                # 尝试解析时间戳（秒级或毫秒级）
                timestamp = int(obj_edit_time)
                # 判断是秒级还是毫秒级时间戳
                if len(obj_edit_time) == 10:  # 秒级时间戳
                    edit_time = datetime.fromtimestamp(timestamp)
                else:  # 毫秒级时间戳
                    edit_time = datetime.fromtimestamp(timestamp / 1000)
            except Exception as e:
                logger.error(f"解析文档编辑时间失败: {str(e)}, obj_edit_time={obj_edit_time}")
        
        # 如果已有记录且状态为已订阅，检查是否需要更新信息
        if existing and existing.status == 1:
            need_update = False
            hierarchy_changed = False
            
            # 检查并更新层级路径和标题
            if hierarchy_path and (existing.hierarchy_path is None or existing.hierarchy_path != hierarchy_path):
                existing.hierarchy_path = hierarchy_path
                # 层级路径变了，同时更新标题
                if title:
                    existing.title = title
                need_update = True
                hierarchy_changed = True
                logger.info(f"更新文档层级路径: file_token={file_token}, hierarchy_path={hierarchy_path}")
            
            # 检查并更新编辑时间
            if edit_time and (existing.obj_edit_time is None or existing.obj_edit_time < edit_time):
                existing.obj_edit_time = edit_time
                need_update = True
                logger.info(f"更新文档编辑时间: file_token={file_token}, obj_edit_time={obj_edit_time}")
            
            # 如果需要更新，提交到数据库
            if need_update:
                await self.db.commit()
            
            # 如果目录发生变化，同步到FastGPT，删除旧的文件集合，创建新的文件集合
            if hierarchy_changed:
                try:
                    # 导入需要的模块（在方法内部导入避免循环依赖）
                    from app.api.v1.endpoints.document import SyncDocToAIChatRequest, sync_document_to_aichat
                    
                    # 创建同步请求
                    sync_request = SyncDocToAIChatRequest(
                        app_id=app_id,
                        file_token=file_token,
                        file_type=file_type,
                        hierarchy_changed=True  # 传入目录变化标志
                    )
                    
                    # 调用同步方法
                    result = await sync_document_to_aichat(sync_request, self)
                    
                    if result.get("code") == 0:
                        logger.info(f"文档目录变化，成功同步到FastGPT: file_token={file_token}, new_path={hierarchy_path}")
                    else:
                        logger.error(f"文档目录变化，同步到FastGPT失败: file_token={file_token}, error={result.get('msg')}")
                except Exception as e:
                    logger.error(f"文档目录变化，同步到FastGPT异常: file_token={file_token}, error={str(e)}")
            
            logger.info(f"文档已订阅, 文档名称: {existing.title}, 跳过: file_token={file_token}, file_type={file_type}")
            return {
                "code": 0,
                "msg": "文档已订阅",
                "data": {"already_subscribed": True}
            }
            
        # PDF文件不需要调用订阅接口，直接创建本地记录即可
        if file_type.lower() == "pdf":
            logger.info(f"PDF文件无需调用订阅接口，直接创建本地记录: file_token={file_token}")
            
            # 创建或更新订阅记录
            if existing:
                # 更新现有记录
                existing.status = 1
                existing.file_type = file_type
                # 如果层级路径变了，同时更新标题
                if hierarchy_path:
                    existing.hierarchy_path = hierarchy_path
                    if title:
                        existing.title = title
                    logger.info(f"更新PDF文件层级路径: file_token={file_token}, hierarchy_path={hierarchy_path}")
                if space_id and not existing.space_id:
                    existing.space_id = space_id
                if edit_time:
                    existing.obj_edit_time = edit_time
                existing.updated_at = func.now()
                await self.db.commit()
                logger.info(f"成功更新PDF文件记录, 文档名称: {title}, file_token={file_token}")
            else:
                # 创建新记录
                subscription = DocSubscription(
                    app_id=app_id,
                    file_token=file_token,
                    file_type=file_type,
                    title=title,
                    space_id=space_id,
                    status=1,
                    obj_edit_time=edit_time,
                    hierarchy_path=hierarchy_path
                )
                self.db.add(subscription)
                await self.db.commit()
                logger.info(f"成功创建PDF文件记录, 文档名称: {title}, file_token={file_token}, hierarchy_path={hierarchy_path}")
            
            # 如果提供了空间ID，更新空间的文档数量
            if space_id:
                await self.update_space_doc_count(app_id, space_id)
            
            return {
                "code": 0,
                "data": {"pdf_file": True}
            }

        # 对于docx等云文档，调用飞书API进行订阅
        token = await self.get_tenant_access_token(app_id)
        url = f"{self.base_url}/open-apis/drive/v1/files/{file_token}/subscribe"
        
        params = {
            "file_type": file_type
        }
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        try:
            async with self.client.post(url, params=params, headers=headers) as response:
                result = await response.json()
                if result.get("code") == 0:
                    # 订阅成功，记录到数据库或更新现有记录
                    if existing:
                        # 更新现有记录
                        existing.status = 1
                        existing.file_type = file_type  # 确保类型正确
                        # 如果层级路径变了，同时更新标题
                        if hierarchy_path:
                            existing.hierarchy_path = hierarchy_path
                            if title:
                                existing.title = title
                            logger.info(f"更新文档层级路径: file_token={file_token}, hierarchy_path={hierarchy_path}")
                        if space_id and not existing.space_id:
                            existing.space_id = space_id
                        if edit_time:
                            existing.obj_edit_time = edit_time
                        existing.updated_at = func.now()
                        await self.db.commit()
                        logger.info(f"成功重新订阅文档并更新数据库记录, 文档名称: {title}, file_token={file_token}, file_type={file_type}")
                    else:
                        # 创建新记录
                        subscription = DocSubscription(
                            app_id=app_id,
                            file_token=file_token,
                            file_type=file_type,
                            title=title,
                            space_id=space_id,
                            status=1,
                            obj_edit_time=edit_time,
                            hierarchy_path=hierarchy_path
                        )
                        self.db.add(subscription)
                        await self.db.commit()
                        logger.info(f"成功订阅文档并创建数据库记录, 文档名称: {title}, file_token={file_token}, file_type={file_type}, hierarchy_path={hierarchy_path}")
                    
                    # 如果提供了空间ID，更新空间的文档数量
                    if space_id:
                        await self.update_space_doc_count(app_id, space_id)
                    
                    return {
                        "code": 0,
                        "data": result.get("data", {})
                    }
                else:
                    logger.error(f"订阅文档事件失败：file_token={file_token}, file_type={file_type}, error={result}")
                    return {
                        "code": result.get("code", -1),
                        "msg": result.get("msg", "订阅文档事件失败")
                    }
        except Exception as e:
            logger.error(f"订阅文档事件异常：file_token={file_token}, file_type={file_type}, error={str(e)}")
            return {
                "code": -1,
                "msg": f"订阅文档事件异常: {str(e)}"
            }
            
    async def get_doc_subscribe_status(self, app_id: str, file_token: str, file_type: str) -> dict:
        """获取文档订阅状态
        
        Args:
            app_id: 应用ID
            file_token: 文档Token
            file_type: 文档类型，如docx
            
        Returns:
            dict: 订阅状态
        """
        # 检查文件类型是否支持
        if file_type not in self.supported_file_types:
            return {
                "code": -1,
                "msg": f"不支持的文件类型: {file_type}，目前仅支持: {', '.join(self.supported_file_types)}"
            }
            
        token = await self.get_tenant_access_token(app_id)
        url = f"{self.base_url}/open-apis/drive/v1/files/{file_token}/get_subscribe"
        
        params = {
            "file_type": file_type
        }
        
        headers = {
            "Authorization": f"Bearer {token}"
        }
        
        try:
            async with self.client.get(url, params=params, headers=headers) as response:
                result = await response.json()
                if result.get("code") == 0:
                    logger.info(f"成功获取文档订阅状态：file_token={file_token}, file_type={file_type}")
                    return {
                        "code": 0,
                        "data": result.get("data", {})
                    }
                else:
                    logger.error(f"获取文档订阅状态失败：file_token={file_token}, file_type={file_type}, error={result}")
                    return {
                        "code": result.get("code", -1),
                        "msg": result.get("msg", "获取文档订阅状态失败")
                    }
        except Exception as e:
            logger.error(f"获取文档订阅状态异常：file_token={file_token}, file_type={file_type}, error={str(e)}")
            return {
                "code": -1,
                "msg": f"获取文档订阅状态异常: {str(e)}"
            }
    
    async def subscribe_space_documents(self, app_id: str, space_id: str) -> dict:
        """订阅知识空间下所有文档事件
        
        递归遍历知识空间的所有节点，找到所有docx类型的文档并订阅事件
        仅订阅数据库中未记录的文档，并记录知识空间订阅状态
        
        Args:
            app_id: 应用ID
            space_id: 知识空间ID
            
        Returns:
            dict: 订阅结果统计
        """
        logger.info(f"开始订阅知识空间文档: space_id={space_id}")
        
        # 获取空间信息
        space_info = await self.get_wiki_space(app_id, space_id)
        space_name = None
        space_type = None
        
        if space_info.get("code") == 0 and space_info.get("data"):
            space_data = space_info.get("data")
            space_obj = space_data.get("space", {})
            space_name = space_obj.get("name")
            space_type = space_obj.get("space_type", "wiki")
        
        # 更新空间订阅状态
        await self.update_space_subscription(
            app_id, 
            space_id, 
            status=1, 
            space_info={"name": space_name, "type": space_type}
        )
        
        # 结果统计
        result = {
            "code": 0,
            "msg": "订阅知识空间文档完成",
            "data": {
                "total": 0,
                "success": 0,
                "failed": 0,
                "skipped": 0,
                "already_subscribed": 0,
                "space_name": space_name,
                "space_type": space_type,
                "details": []
            }
        }
        
        # 递归处理所有节点
        await self._process_space_nodes(app_id, space_id, None, result["data"])
        
        # 更新消息
        result["msg"] = f"订阅完成: 共{result['data']['total']}个节点, {result['data']['success']}个新订阅, {result['data']['already_subscribed']}个已订阅, {result['data']['failed']}个失败, {result['data']['skipped']}个跳过"
        logger.info(result["msg"])
        
        # 确保空间文档数量是最新的
        await self.update_space_doc_count(app_id, space_id)
        
        return result
            
    async def _process_space_nodes(self, app_id: str, space_id: str, parent_node_token: str = None, result: dict = None, parent_path: str = None):
        """递归处理知识空间节点，订阅所有docx类型文档
        
        Args:
            app_id: 应用ID
            space_id: 知识空间ID
            parent_node_token: 父节点Token
            result: 结果统计字典
            parent_path: 父节点路径，用于构建hierarchy_path
        """
        if result is None:
            result = {
                "total": 0,
                "success": 0,
                "failed": 0,
                "skipped": 0,
                "already_subscribed": 0,
                "details": []
            }
        
        # 获取当前层级的节点
        nodes_result = await self.get_wiki_nodes(app_id, space_id, parent_node_token)
        
        if nodes_result.get("code") != 0:
            logger.error(f"获取知识空间节点失败: space_id={space_id}, parent_node_token={parent_node_token}")
            return result
        
        nodes = nodes_result.get("data", {}).get("items", [])
        
        # 遍历所有节点
        for node in nodes:
            result["total"] += 1
            
            # 检查是否是docx类型的文档或pdf文件
            obj_type = node.get("obj_type")
            obj_token = node.get("obj_token")
            node_token = node.get("node_token")
            title = node.get("title", "")
            obj_edit_time = node.get("obj_edit_time")  # 获取文档最后编辑时间
            
            # 构建当前节点的层级路径
            current_path = title
            if parent_path:
                current_path = f"{parent_path}###{title}"
            
            detail = {
                "node_token": node_token,
                "title": title,
                "obj_type": obj_type,
                "obj_token": obj_token,
                "hierarchy_path": current_path
            }
            
            # 过滤掉标题为空或"未命名"的文档
            if not title or title.strip() == "" or title.strip() == "未命名":
                result["skipped"] += 1
                detail["status"] = "skipped"
                detail["reason"] = f"文档标题为空或未命名，跳过: {title}"
                result["details"].append(detail)
                continue
            
            if obj_token:
                # 订阅文档
                subscribe_result = await self.subscribe_doc_events(
                    app_id, 
                    obj_token, 
                    obj_type,  # 传递正确的文件类型(docx或file)
                    title,
                    space_id,
                    obj_edit_time,  # 传递文档最后编辑时间
                    current_path  # 传递层级路径
                )
                
                if subscribe_result.get("code") == 0:
                    if subscribe_result.get("data", {}).get("already_subscribed"):
                        result["already_subscribed"] += 1
                        detail["status"] = "already_subscribed"
                    else:
                        result["success"] += 1
                        detail["status"] = "success"
                else:
                    result["failed"] += 1
                    detail["status"] = "failed"
                    detail["error"] = subscribe_result.get("msg")
            else:
                # 不是支持的文件类型，跳过
                result["skipped"] += 1
                detail["status"] = "skipped"
                detail["reason"] = f"不支持的文件类型: {obj_type}, 标题: {title}"
                
            result["details"].append(detail)
            
            # 如果有子节点，递归处理
            if node.get("has_child"):
                await self._process_space_nodes(app_id, space_id, node_token, result, current_path)
                
        return result
            
    async def unsubscribe_doc_events(self, app_id: str, file_token: str, file_type: str) -> dict:
        """取消订阅云文档事件
        
        Args:
            app_id: 应用ID
            file_token: 文档Token
            file_type: 文档类型，如docx、sheet、bitable、file
            
        Returns:
            dict: 取消订阅结果
        """
        # 检查文件类型是否支持
        if file_type not in self.supported_file_types:
            return {
                "code": -1,
                "msg": f"不支持的文件类型: {file_type}，目前仅支持: {', '.join(self.supported_file_types)}"
            }
            
        token = await self.get_tenant_access_token(app_id)
        url = f"{self.base_url}/open-apis/drive/v1/files/{file_token}/delete_subscribe"
        
        params = {
            "file_type": file_type
        }
        
        headers = {
            "Authorization": f"Bearer {token}"
        }
        
        try:
            async with self.client.delete(url, params=params, headers=headers) as response:
                result = await response.json()
                if result.get("code") == 0:
                    # 更新数据库中的订阅状态
                    await self.db.execute(
                        update(DocSubscription)
                        .where(
                            DocSubscription.app_id == app_id,
                            DocSubscription.file_token == file_token
                        )
                        .values(status=0)
                    )
                    await self.db.commit()
                    
                    logger.info(f"成功取消订阅文档事件并更新数据库：file_token={file_token}, file_type={file_type}")
                    return {
                        "code": 0,
                        "data": result.get("data", {})
                    }
                else:
                    logger.error(f"取消订阅文档事件失败：file_token={file_token}, file_type={file_type}, error={result}")
                    return {
                        "code": result.get("code", -1),
                        "msg": result.get("msg", "取消订阅文档事件失败")
                    }
        except Exception as e:
            logger.error(f"取消订阅文档事件异常：file_token={file_token}, file_type={file_type}, error={str(e)}")
            return {
                "code": -1,
                "msg": f"取消订阅文档事件异常: {str(e)}"
            }

    async def get_subscribed_documents(self, app_id: str) -> dict:
        """获取已订阅的文档列表
        
        Args:
            app_id: 应用ID
            
        Returns:
            dict: 已订阅文档列表，包含编辑时间和AI知识库更新时间
        """
        try:
            query = await self.db.execute(
                select(DocSubscription)
                .where(
                    DocSubscription.app_id == app_id,
                    DocSubscription.status == 1
                )
            )
            subscriptions = query.scalars().all()
            
            docs = []
            for sub in subscriptions:
                docs.append({
                    "file_token": sub.file_token,
                    "file_type": sub.file_type,
                    "title": sub.title,
                    "space_id": sub.space_id,
                    "subscribed_at": sub.created_at.isoformat() if sub.created_at else None,
                    "obj_edit_time": sub.obj_edit_time.isoformat() if sub.obj_edit_time else None,
                    "aichat_update_time": sub.aichat_update_time.isoformat() if sub.aichat_update_time else None
                })
                
            return {
                "code": 0,
                "data": {
                    "total": len(docs),
                    "items": docs
                }
            }
        except Exception as e:
            logger.error(f"获取已订阅文档列表失败: {str(e)}")
            return {
                "code": -1,
                "msg": f"获取已订阅文档列表失败: {str(e)}"
            }
            
    async def get_docs_for_aichat_sync(self, app_id: str, limit: int = 100, file_token: str = None) -> dict:
        """获取需要同步到AI知识库的文档列表
        
        获取满足以下条件的文档:
        1. 已订阅
        2. obj_edit_time > aichat_update_time 或 aichat_update_time为空
        
        如果指定file_token，则只返回该文档的信息，不考虑上述条件2
        
        Args:
            app_id: 应用ID
            limit: 返回的最大文档数量，默认100
            file_token: 指定文档Token，可选
            
        Returns:
            dict: 需要同步的文档列表
        """
        try:
            if file_token:
                # 如果指定了file_token，只查询该文档
                query = await self.db.execute(
                    select(DocSubscription)
                    .where(
                        DocSubscription.app_id == app_id,
                        DocSubscription.file_token == file_token,
                        DocSubscription.status == 1
                    )
                )
            else:
                # 否则查询所有需要同步的文档
                query = await self.db.execute(
                    select(DocSubscription)
                    .where(
                        DocSubscription.app_id == app_id,
                        DocSubscription.status == 1,
                        (DocSubscription.obj_edit_time > DocSubscription.aichat_update_time) | 
                        (DocSubscription.aichat_update_time == None)
                    )
                    .order_by(DocSubscription.obj_edit_time.desc())
                    # .limit(limit)
                )
            
            subscriptions = query.scalars().all()
            
            docs = []
            for sub in subscriptions:
                docs.append({
                    "file_token": sub.file_token,
                    "file_type": sub.file_type,
                    "title": sub.title,
                    "space_id": sub.space_id,
                    "hierarchy_path": sub.hierarchy_path,
                    "obj_edit_time": sub.obj_edit_time.isoformat() if sub.obj_edit_time else None,
                    "aichat_update_time": sub.aichat_update_time.isoformat() if sub.aichat_update_time else None
                })
                
            return {
                "code": 0,
                "data": {
                    "total": len(docs),
                    "items": docs
                }
            }
        except Exception as e:
            logger.error(f"获取需要同步的文档列表失败: {str(e)}")
            return {
                "code": -1,
                "msg": f"获取需要同步的文档列表失败: {str(e)}"
            }

    async def close(self):
        """关闭客户端会话"""
        if self._client and not self._client.closed:
            await self._client.close()
            self._client = None
            
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

    async def get_space_subscriptions(self, app_id: str) -> dict:
        """获取已订阅的知识空间列表
        
        Args:
            app_id: 应用ID
            
        Returns:
            dict: 已订阅知识空间列表
        """
        try:
            query = await self.db.execute(
                select(SpaceSubscription)
                .where(
                    SpaceSubscription.app_id == app_id
                )
                .order_by(SpaceSubscription.status.desc(), SpaceSubscription.updated_at.desc())
            )
            subscriptions = query.scalars().all()
            
            spaces = []
            for sub in subscriptions:
                spaces.append({
                    "space_id": sub.space_id,
                    "space_name": sub.space_name,
                    "space_type": sub.space_type,
                    "status": sub.status,
                    "doc_count": sub.doc_count,
                    "last_sync_time": sub.last_sync_time.isoformat() if sub.last_sync_time else None,
                    "subscribed_at": sub.created_at.isoformat() if sub.created_at else None
                })
            
            return {
                "code": 0,
                "data": {
                    "total": len(spaces),
                    "items": spaces
                }
            }
        except Exception as e:
            logger.error(f"获取已订阅知识空间列表异常：app_id={app_id}, error={str(e)}")
            return {
                "code": -1,
                "msg": f"获取已订阅知识空间列表异常: {str(e)}"
            }
            
    async def update_space_subscription(self, app_id: str, space_id: str, status: int = 1, space_info: dict = None) -> dict:
        """更新知识空间订阅状态
        
        Args:
            app_id: 应用ID
            space_id: 知识空间ID
            status: 订阅状态，1为已订阅，0为已取消
            space_info: 空间信息，包含name和type等
            
        Returns:
            dict: 更新结果
        """
        try:
            # 查询是否存在记录
            query = await self.db.execute(
                select(SpaceSubscription).where(
                    SpaceSubscription.app_id == app_id,
                    SpaceSubscription.space_id == space_id
                )
            )
            existing = query.scalar_one_or_none()
            
            now = datetime.now()
            
            if existing:
                # 更新现有记录
                existing.status = status
                if space_info:
                    if space_info.get("name"):
                        existing.space_name = space_info.get("name")
                    if space_info.get("type"):
                        existing.space_type = space_info.get("type")
                
                if status == 1:  # 如果是订阅状态，更新同步时间
                    existing.last_sync_time = now
                
                await self.db.commit()
                logger.info(f"更新知识空间订阅状态：space_id={space_id}, status={status}")
            else:
                # 创建新记录
                space_name = space_info.get("name") if space_info else None
                space_type = space_info.get("type") if space_info else None
                
                subscription = SpaceSubscription(
                    app_id=app_id,
                    space_id=space_id,
                    space_name=space_name,
                    space_type=space_type,
                    status=status,
                    last_sync_time=now if status == 1 else None
                )
                self.db.add(subscription)
                await self.db.commit()
                logger.info(f"创建知识空间订阅记录：space_id={space_id}, status={status}")
            
            return {
                "code": 0,
                "msg": "更新知识空间订阅状态成功"
            }
        except Exception as e:
            logger.error(f"更新知识空间订阅状态异常：app_id={app_id}, space_id={space_id}, error={str(e)}")
            return {
                "code": -1,
                "msg": f"更新知识空间订阅状态异常: {str(e)}"
            }
            
    async def update_space_doc_count(self, app_id: str, space_id: str) -> dict:
        """更新知识空间已订阅文档数量
        
        Args:
            app_id: 应用ID
            space_id: 知识空间ID
            
        Returns:
            dict: 更新结果
        """
        from app.models.space_subscription import SpaceSubscription
        from app.models.doc_subscription import DocSubscription
        from sqlalchemy import func
        
        try:
            # 查询该空间下已订阅的文档数量
            count_query = await self.db.execute(
                select(func.count())
                .select_from(DocSubscription)
                .where(
                    DocSubscription.app_id == app_id,
                    DocSubscription.space_id == space_id,
                    DocSubscription.status == 1
                )
            )
            doc_count = count_query.scalar_one() or 0
            
            # 更新空间订阅记录
            query = await self.db.execute(
                select(SpaceSubscription).where(
                    SpaceSubscription.app_id == app_id,
                    SpaceSubscription.space_id == space_id
                )
            )
            space_sub = query.scalar_one_or_none()
            
            if space_sub:
                space_sub.doc_count = doc_count
                await self.db.commit()
                logger.info(f"更新知识空间文档数量：space_id={space_id}, doc_count={doc_count}")
                
                return {
                    "code": 0,
                    "msg": "更新知识空间文档数量成功",
                    "data": {"doc_count": doc_count}
                }
            else:
                return {
                    "code": -1,
                    "msg": f"未找到知识空间订阅记录: space_id={space_id}"
                }
        except Exception as e:
            logger.error(f"更新知识空间文档数量异常：app_id={app_id}, space_id={space_id}, error={str(e)}")
            return {
                "code": -1,
                "msg": f"更新知识空间文档数量异常: {str(e)}"
            }

    async def get_wiki_space(self, app_id: str, space_id: str) -> dict:
        """获取单个知识空间信息
        
        Args:
            app_id: 应用ID
            space_id: 知识空间ID
            
        Returns:
            dict: 知识空间信息
        """
        logger.info(f"开始获取知识空间信息: app_id={app_id}, space_id={space_id}")
        token = await self.get_tenant_access_token(app_id)
        url = f"{self.base_url}/open-apis/wiki/v2/spaces/{space_id}"
        
        headers = {
            "Authorization": f"Bearer {token}"
        }
        
        logger.info(f"发送请求获取知识空间信息: url={url}")
        try:
            async with self.client.get(url, headers=headers) as response:
                result = await response.json()
                logger.info(f"获取知识空间信息响应: {result}")
                if result.get("code") == 0:
                    # 提取出空间名称供日志使用
                    space_name = "未知"
                    if result.get("data") and result.get("data").get("space"):
                        space_name = result.get("data").get("space").get("name", "未知")
                    logger.info(f"成功获取知识空间信息: space_name={space_name}, 数据={result.get('data', {})}")
                    return {
                        "code": 0,
                        "data": result.get("data", {})
                    }
                logger.error(f"获取知识空间信息失败: code={result.get('code')}, msg={result.get('msg')}")
                return {
                    "code": result.get("code", -1),
                    "msg": result.get("msg", "获取知识空间信息失败")
                }
        except Exception as e:
            logger.error(f"获取知识空间信息异常: {str(e)}")
            return {
                "code": -1,
                "msg": f"获取知识空间信息异常: {str(e)}"
            }

    async def update_doc_aichat_time(self, app_id: str, file_token: str, success: bool = True) -> bool:
        """更新文档AI知识库同步时间
        
        仅更新文档的AI知识库同步时间记录，不执行实际的同步操作
        
        Args:
            app_id: 应用ID
            file_token: 文档Token
            success: 同步是否成功，默认为True
            
        Returns:
            bool: 更新是否成功
        """
        try:
            # 查询文档信息
            query = await self.db.execute(
                select(DocSubscription).where(
                    DocSubscription.app_id == app_id,
                    DocSubscription.file_token == file_token
                )
            )
            doc = query.scalar_one_or_none()
            
            if not doc:
                logger.error(f"更新AI知识库同步时间失败: 找不到文档记录 file_token={file_token}")
                return False
            
            # 更新为当前时间
            await self.db.execute(
                update(DocSubscription)
                .where(
                    DocSubscription.app_id == app_id,
                    DocSubscription.file_token == file_token
                )
                .values(aichat_update_time=func.now())
            )
            await self.db.commit()
            logger.info(f"更新文档AI知识库同步时间: file_token={file_token}")
            
            return True
        except Exception as e:
            logger.error(f"更新文档AI知识库同步时间失败: file_token={file_token}, error={str(e)}")
            return False

    async def download_file(self, app_id: str, file_token: str, output_path: str) -> dict:
        """下载飞书云空间中的文件
        
        Args:
            app_id: 应用ID
            file_token: 文件Token
            output_path: 输出文件路径
            
        Returns:
            dict: 下载结果
        """
        token = await self.get_tenant_access_token(app_id)
        url = f"{self.base_url}/open-apis/drive/v1/files/{file_token}/download"
        
        headers = {
            "Authorization": f"Bearer {token}"
        }
        
        try:
            # 创建输出文件的目录（如果不存在）
            import os
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            
            async with self.client.get(url, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    
                    # 根据不同的状态码提供更友好的错误信息
                    if response.status == 404:
                        error_msg = "文件不存在或已被删除，可能是文件token已过期"
                        logger.error(f"下载文件失败 (404): file_token={file_token}, 原因: {error_msg}")
                    elif response.status == 403:
                        error_msg = "无权限访问文件，可能是token无效或文件权限不足"
                        logger.error(f"下载文件失败 (403): file_token={file_token}, 原因: {error_msg}")
                    elif response.status == 401:
                        error_msg = "认证失败，可能是access_token已过期"
                        logger.error(f"下载文件失败 (401): file_token={file_token}, 原因: {error_msg}")
                    elif response.status >= 500:
                        error_msg = "飞书服务器内部错误，请稍后重试"
                        logger.error(f"下载文件失败 ({response.status}): file_token={file_token}, 原因: {error_msg}, 响应: {error_text}")
                    else:
                        error_msg = f"下载失败 (HTTP {response.status})"
                        logger.error(f"下载文件失败: file_token={file_token}, status={response.status}, error={error_text}")
                    
                    return {
                        "code": -1,
                        "msg": error_msg,
                        "status_code": response.status,
                        "error_details": error_text
                    }
                
                # 检查响应内容大小
                content_length = response.headers.get('content-length')
                if content_length:
                    file_size = int(content_length)
                    if file_size == 0:
                        logger.warning(f"下载的文件大小为0: file_token={file_token}")
                
                # 将响应内容写入文件
                content = await response.read()
                with open(output_path, 'wb') as f:
                    f.write(content)
                
                actual_size = len(content)
                logger.info(f"成功下载文件: file_token={file_token}, 输出文件: {output_path}, 文件大小: {actual_size}字节")
                
                return {
                    "code": 0,
                    "data": {
                        "file_path": output_path,
                        "file_size": actual_size
                    }
                }
        except Exception as e:
            logger.error(f"下载文件异常: file_token={file_token}, error={str(e)}")
            return {
                "code": -1,
                "msg": f"下载文件异常: {str(e)}"
            }

    async def get_document_blocks(self, app_id: str, doc_token: str, page_token: str = None) -> dict:
        """获取文档所有块
        
        获取云文档中的所有块信息，包括图片块（block_type=27）
        
        Args:
            app_id: 应用ID
            doc_token: 文档Token
            page_size: 每页块数，默认500
            page_token: 分页标记，首次请求不需要
            
        Returns:
            dict: 文档块列表
        """
        token = await self.get_tenant_access_token(app_id)
        url = f"{self.base_url}/open-apis/docx/v1/documents/{doc_token}/blocks"
        
        params = {
            "page_size": 500
        }
        if page_token:
            params["page_token"] = page_token
            
        headers = {
            "Authorization": f"Bearer {token}"
        }
        
        try:
            async with self.client.get(url, params=params, headers=headers) as response:
                result = await response.json()
                if result.get("code") == 0:
                    logger.info(f"成功获取文档块列表: doc_token={doc_token}, 块数={len(result.get('data', {}).get('items', []))}")
                    return {
                        "code": 0,
                        "data": result.get("data", {})
                    }
                logger.error(f"获取文档块列表失败: doc_token={doc_token}, error={result}")
                return {
                    "code": result.get("code", -1),
                    "msg": result.get("msg", "获取文档块列表失败")
                }
        except Exception as e:
            logger.error(f"获取文档块列表异常: doc_token={doc_token}, error={str(e)}")
            return {
                "code": -1,
                "msg": f"获取文档块列表异常: {str(e)}"
            }
    
    async def get_all_document_blocks(self, app_id: str, doc_token: str, process_images: bool = True) -> dict:
        """获取文档的所有块（自动处理分页）
        
        Args:
            app_id: 应用ID
            doc_token: 文档Token
            process_images: 是否处理图片块，默认True
            
        Returns:
            dict: 所有文档块
        """
        import asyncio
        
        all_blocks = []
        page_token = None
        has_more = True
        page_count = 0
        
        while has_more:
            page_count += 1
            logger.debug(f"获取文档块第{page_count}页: doc_token={doc_token}, page_token={page_token}")
            
            result = await self.get_document_blocks(app_id, doc_token, page_token=page_token)
            
            if result.get("code") != 0:
                return result
            
            data = result.get("data", {})
            blocks = data.get("items", [])
            all_blocks.extend(blocks)
            
            # 检查是否有更多页
            has_more = data.get("has_more", False)
            page_token = data.get("page_token")
            
            logger.debug(f"第{page_count}页获取到{len(blocks)}个块, has_more={has_more}, page_token={page_token}")
            
            if not page_token and has_more:
                logger.error(f"获取文档块列表分页错误: 声明有更多块但未提供page_token")
                has_more = False
        
            # 如果还有更多页，添加200毫秒延迟避免触发飞书API限流（每秒5次请求）
            if has_more:
                logger.debug("等待200毫秒避免API限流...")
                await asyncio.sleep(0.2)
        
        logger.info(f"成功获取文档所有块: doc_token={doc_token}, 总块数={len(all_blocks)}, 总页数={page_count}")
        
        # 如果需要处理图片，则下载图片并替换图片块内容
        if process_images:
            all_blocks = await self._process_image_blocks(app_id, doc_token, all_blocks)
        
        return {
            "code": 0,
            "data": {
                "items": all_blocks,
                "total": len(all_blocks)
            }
        }
    
    async def _process_image_blocks(self, app_id: str, doc_token: str, blocks: list) -> list:
        """处理图片块，下载图片并替换为本地URL
        
        Args:
            app_id: 应用ID
            doc_token: 文档Token
            blocks: 文档块列表
            
        Returns:
            list: 处理后的文档块列表
        """
        try:
            from app.utils.image_bed import image_bed
            
            # 统计图片块数量
            image_blocks_count = sum(1 for block in blocks if block.get("block_type") == 27)
            
            if image_blocks_count == 0:
                logger.info(f"文档中没有图片块: doc_token={doc_token}")
                return blocks
            
            logger.info(f"开始处理文档中的图片块: doc_token={doc_token}, 图片数量={image_blocks_count}")
            
            processed_blocks = []
            processed_count = 0
            failed_count = 0
            
            for block in blocks:
                if block.get("block_type") == 27:  # 图片块
                    image_token = block.get("image", {}).get("token")
                    
                    if image_token:
                        # 下载并存储图片
                        image_info = await image_bed.download_and_store_image(
                            feishu_service=self,
                            app_id=app_id,
                            image_token=image_token
                        )
                        
                        if image_info:
                            # 创建新的图片块，使用本地URL
                            new_block = block.copy()
                            new_block["image"] = {
                                "token": image_info["filename"],  # 使用新的UUID文件名
                                "width": block.get("image", {}).get("width"),
                                "height": block.get("image", {}).get("height"),
                                "local_url": image_info["url"],  # 添加本地URL
                                "original_token": image_token,  # 保留原始token用于调试
                                "file_size": image_info["size"]
                            }
                            processed_blocks.append(new_block)
                            processed_count += 1
                            logger.debug(f"成功处理图片块: {image_token} -> {image_info['url']}")
                        else:
                            # 如果下载失败，保留原始块但添加错误标记
                            error_block = block.copy()
                            error_block["image"]["download_error"] = True
                            processed_blocks.append(error_block)
                            failed_count += 1
                            logger.error(f"处理图片块失败: {image_token}")
                    else:
                        # 如果没有image_token，保留原始块
                        processed_blocks.append(block)
                        logger.warning(f"图片块缺少image_token: block_id={block.get('block_id')}")
                else:
                    # 非图片块，直接添加
                    processed_blocks.append(block)
            
            logger.info(f"完成图片块处理: doc_token={doc_token}, 成功={processed_count}, 失败={failed_count}, 总计={image_blocks_count}")
            
            return processed_blocks
            
        except Exception as e:
            logger.error(f"处理图片块异常: doc_token={doc_token}, error={str(e)}")
            # 如果处理失败，返回原始块列表
            return blocks
    
    async def get_document_images(self, app_id: str, doc_token: str) -> dict:
        """获取文档中的所有图片块信息
        
        Args:
            app_id: 应用ID
            doc_token: 文档Token
            
        Returns:
            dict: 图片块列表（包含image_token）
        """
        # 获取所有块
        blocks_result = await self.get_all_document_blocks(app_id, doc_token)
        
        if blocks_result.get("code") != 0:
            return blocks_result
        
        # 筛选图片块（block_type=27）
        all_blocks = blocks_result.get("data", {}).get("items", [])
        image_blocks = []
        
        for block in all_blocks:
            if block.get("block_type") == 27:  # 图片块
                image_info = {
                    "block_id": block.get("block_id"),
                    "image_token": block.get("image", {}).get("token"),
                    "image_width": block.get("image", {}).get("width"),
                    "image_height": block.get("image", {}).get("height")
                }
                image_blocks.append(image_info)
        
        logger.info(f"成功获取文档图片块: doc_token={doc_token}, 图片数={len(image_blocks)}")
        return {
            "code": 0,
            "data": {
                "items": image_blocks,
                "total": len(image_blocks)
            }
        }
    
    async def download_image(self, app_id: str, image_token: str, output_path: str) -> dict:
        """下载文档中的图片（带QPS限制和重试机制）
        
        Args:
            app_id: 应用ID
            image_token: 图片Token
            output_path: 输出文件路径
            
        Returns:
            dict: 下载结果
        """
        # QPS限制：确保间隔时间
        async with self._image_download_semaphore:
            current_time = time.time()
            time_since_last = current_time - self._last_image_download_time
            
            if time_since_last < self._image_download_interval:
                sleep_time = self._image_download_interval - time_since_last
                logger.debug(f"QPS限制，等待 {sleep_time:.3f}s: image_token={image_token}")
                await asyncio.sleep(sleep_time)
            
            self._last_image_download_time = time.time()
            
            # 最多重试3次
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    result = await self._download_image_once(app_id, image_token, output_path)
                    
                    # 如果是频率限制错误，等待更长时间后重试
                    if result.get("code") == -1 and "99991400" in str(result.get("msg", "")):
                        if attempt < max_retries - 1:
                            wait_time = (attempt + 1) * 2  # 2s, 4s, 6s
                            logger.warning(f"遇到频率限制，第{attempt+1}次重试，等待{wait_time}s: image_token={image_token}")
                            await asyncio.sleep(wait_time)
                            continue
                    
                    return result
                    
                except Exception as e:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 1  # 1s, 2s, 3s
                        logger.warning(f"下载图片异常，第{attempt+1}次重试，等待{wait_time}s: image_token={image_token}, error={str(e)}")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"下载图片最终失败: image_token={image_token}, error={str(e)}")
                        return {
                            "code": -1,
                            "msg": f"下载图片最终失败: {str(e)}"
                        }
    
    async def _download_image_once(self, app_id: str, image_token: str, output_path: str) -> dict:
        """执行单次图片下载
        
        Args:
            app_id: 应用ID
            image_token: 图片Token
            output_path: 输出文件路径
            
        Returns:
            dict: 下载结果
        """
        token = await self.get_tenant_access_token(app_id)
        url = f"{self.base_url}/open-apis/drive/v1/medias/{image_token}/download"
        
        headers = {
            "Authorization": f"Bearer {token}"
        }
        
        try:
            # 创建输出文件的目录（如果不存在）
            import os
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            
            async with self.client.get(url, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"下载图片失败: image_token={image_token}, status={response.status}, error={error_text}")
                    return {
                        "code": -1,
                        "msg": f"下载图片失败: {error_text}"
                    }
                
                # 将响应内容写入文件
                with open(output_path, 'wb') as f:
                    f.write(await response.read())
                
                file_size = os.path.getsize(output_path)
                logger.info(f"成功下载图片: image_token={image_token}, 输出文件: {output_path}, 大小: {file_size}字节")
                return {
                    "code": 0,
                    "data": {
                        "file_path": output_path,
                        "file_size": file_size
                    }
                }
        except Exception as e:
            logger.error(f"下载图片异常: image_token={image_token}, error={str(e)}")
            return {
                "code": -1,
                "msg": f"下载图片异常: {str(e)}"
            }

    async def get_spreadsheet_sheets(self, app_id: str, spreadsheet_token: str) -> dict:
        """获取电子表格的工作表列表
        
        Args:
            app_id: 应用ID
            spreadsheet_token: 电子表格Token
            
        Returns:
            dict: 工作表列表
        """
        token = await self.get_tenant_access_token(app_id)
        url = f"{self.base_url}/open-apis/sheets/v3/spreadsheets/{spreadsheet_token}/sheets/query"
        
        headers = {
            "Authorization": f"Bearer {token}"
        }
        
        try:
            async with self.client.get(url, headers=headers) as response:
                result = await response.json()
                if result.get("code") == 0:
                    sheets = result.get("data", {}).get("sheets", [])
                    logger.info(f"成功获取电子表格工作表列表: spreadsheet_token={spreadsheet_token}, 工作表数={len(sheets)}")
                    return {
                        "code": 0,
                        "data": result.get("data", {})
                    }
                logger.error(f"获取电子表格工作表列表失败: spreadsheet_token={spreadsheet_token}, error={result}")
                return {
                    "code": result.get("code", -1),
                    "msg": result.get("msg", "获取工作表列表失败")
                }
        except Exception as e:
            logger.error(f"获取电子表格工作表列表异常: spreadsheet_token={spreadsheet_token}, error={str(e)}")
            return {
                "code": -1,
                "msg": f"获取工作表列表异常: {str(e)}"
            }

    async def get_sheet_info(self, app_id: str, spreadsheet_token: str, sheet_id: str) -> dict:
        """获取单个工作表信息
        
        Args:
            app_id: 应用ID
            spreadsheet_token: 电子表格Token
            sheet_id: 工作表ID
            
        Returns:
            dict: 工作表信息
        """
        token = await self.get_tenant_access_token(app_id)
        url = f"{self.base_url}/open-apis/sheets/v3/spreadsheets/{spreadsheet_token}/sheets/{sheet_id}"
        
        headers = {
            "Authorization": f"Bearer {token}"
        }
        
        try:
            async with self.client.get(url, headers=headers) as response:
                result = await response.json()
                if result.get("code") == 0:
                    sheet_info = result.get("data", {}).get("sheet", {})
                    logger.info(f"成功获取工作表信息: sheet_id={sheet_id}, title={sheet_info.get('title')}")
                    return {
                        "code": 0,
                        "data": result.get("data", {})
                    }
                logger.error(f"获取工作表信息失败: spreadsheet_token={spreadsheet_token}, sheet_id={sheet_id}, error={result}")
                return {
                    "code": result.get("code", -1),
                    "msg": result.get("msg", "获取工作表信息失败")
                }
        except Exception as e:
            logger.error(f"获取工作表信息异常: spreadsheet_token={spreadsheet_token}, sheet_id={sheet_id}, error={str(e)}")
            return {
                "code": -1,
                "msg": f"获取工作表信息异常: {str(e)}"
            }

    async def get_sheet_content(self, app_id: str, spreadsheet_token: str, sheet_id: str, 
                               range_str: str = None, value_render_option: str = "ToString",
                               date_time_render_option: str = "FormattedString") -> dict:
        """获取工作表内容（读取单元格数据）
        
        Args:
            app_id: 应用ID
            spreadsheet_token: 电子表格Token  
            sheet_id: 工作表ID
            range_str: 读取范围，如"A1:Z100"，为空则读取整个工作表
            value_render_option: 单元格数据格式，可选值：ToString、Formula、FormattedValue、UnformattedValue
            date_time_render_option: 日期时间格式，可选值：FormattedString（默认返回格式化字符串）
            
        Returns:
            dict: 工作表内容数据
        """
        token = await self.get_tenant_access_token(app_id)
        
        # 构建range参数，格式为 <sheetId>!<开始位置>:<结束位置>
        if range_str:
            range_param = f"{sheet_id}!{range_str}"
        else:
            # 如果没有指定范围，读取整个工作表（使用一个较大的范围）
            range_param = f"{sheet_id}!A1:ZZ1000"
        
        # 使用v2 API
        url = f"{self.base_url}/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/values/{range_param}"
        
        # 构建查询参数
        params = {
            "valueRenderOption": value_render_option,
            "dateTimeRenderOption": date_time_render_option
        }
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        # 添加调试日志
        logger.info(f"准备调用飞书API: URL={url}")
        logger.info(f"查询参数: {params}")
        logger.info(f"Range参数: {range_param}")
        
        try:
            async with self.client.get(url, params=params, headers=headers) as response:
                # 添加响应状态日志
                logger.info(f"API响应状态: {response.status}")
                
                result = await response.json()
                
                # 添加详细的响应日志
                logger.info(f"API响应结果: code={result.get('code')}, msg={result.get('msg', 'N/A')}")
                
                if result.get("code") == 0:
                    data = result.get("data", {})
                    value_range = data.get("valueRange", {})
                    values = value_range.get("values", [])
                    
                    # 详细记录数据结构
                    logger.info(f"返回数据结构: {list(data.keys())}")
                    if value_range:
                        logger.info(f"valueRange结构: {list(value_range.keys())}")
                    logger.info(f"values类型: {type(values)}, 长度: {len(values) if values else 0}")
                    
                    # 如果有数据，记录前几行
                    if values:
                        logger.info(f"前3行数据示例: {values[:3]}")
                    else:
                        logger.warning(f"API返回成功但values为空: valueRange={value_range}")
                    
                    logger.info(f"成功获取工作表内容: sheet_id={sheet_id}, 范围={range_param}, 数据行数={len(values)}")
                    
                    # 为了保持兼容性，我们将values放到data的顶层
                    result_data = result.get("data", {}).copy()
                    result_data["values"] = values
                    
                    return {
                        "code": 0,
                        "data": result_data
                    }
                    
                logger.error(f"获取工作表内容失败: spreadsheet_token={spreadsheet_token}, sheet_id={sheet_id}, error={result}")
                return {
                    "code": result.get("code", -1),
                    "msg": result.get("msg", "获取工作表内容失败")
                }
        except Exception as e:
            logger.error(f"获取工作表内容异常: spreadsheet_token={spreadsheet_token}, sheet_id={sheet_id}, error={str(e)}")
            return {
                "code": -1,
                "msg": f"获取工作表内容异常: {str(e)}"
            }

    async def get_sheet_doc_content(self, app_id: str, spreadsheet_token: str) -> dict:
        """获取电子表格的完整内容（包含所有工作表）
        
        Args:
            app_id: 应用ID
            spreadsheet_token: 电子表格Token
            
        Returns:
            dict: 电子表格的Markdown格式内容
        """
        try:
            # 1. 获取所有工作表列表
            sheets_result = await self.get_spreadsheet_sheets(app_id, spreadsheet_token)
            if sheets_result.get("code") != 0:
                return sheets_result
            
            sheets = sheets_result.get("data", {}).get("sheets", [])
            if not sheets:
                logger.warning(f"电子表格中没有工作表: spreadsheet_token={spreadsheet_token}")
                return {
                    "code": 0,
                    "data": {
                        "content": "# 电子表格\n\n此表格暂无数据。",
                        "revision": 0,
                        "method": "sheet-api"
                    }
                }
            
            # 2. 获取每个工作表的内容并转换为Markdown
            from app.utils.sheet_converter import SheetConverter
            converter = SheetConverter()
            
            markdown_content = f"# 电子表格内容\n\n"
            processed_sheets = 0
            
            for sheet in sheets:
                sheet_id = sheet.get("sheet_id")
                sheet_title = sheet.get("title", f"工作表{sheet.get('index', 0) + 1}")
                
                # 跳过隐藏的工作表
                if sheet.get("hidden", False):
                    logger.info(f"跳过隐藏工作表: {sheet_title}")
                    continue
                
                logger.info(f"处理工作表: {sheet_title} (ID: {sheet_id})")
                
                # 获取工作表的网格属性，用于确定实际数据范围
                grid_properties = sheet.get("grid_properties", {})
                row_count = grid_properties.get("row_count", 1000)
                column_count = grid_properties.get("column_count", 26)
                
                # 计算合适的读取范围，避免读取过多空数据
                # 限制最大读取范围，防止超过API限制
                max_rows = min(row_count, 500)  # 最多读取500行
                max_cols = min(column_count, 50)  # 最多读取50列（到列AX）
                
                # 将列数转换为列字母
                def num_to_col_letter(n):
                    result = ""
                    while n > 0:
                        n -= 1
                        result = chr(65 + n % 26) + result
                        n //= 26
                    return result
                
                end_col = num_to_col_letter(max_cols)
                range_str = f"A1:{end_col}{max_rows}"
                
                logger.info(f"工作表 {sheet_title} 读取范围: {range_str}")
                
                # 获取工作表内容，使用ToString格式以获得格式化的数据
                content_result = await self.get_sheet_content(
                    app_id, 
                    spreadsheet_token, 
                    sheet_id, 
                    range_str,
                    "ToString",  # 使用ToString格式，与成功的curl请求保持一致
                    "FormattedString"  # 日期时间使用格式化字符串
                )
                
                if content_result.get("code") != 0:
                    logger.error(f"获取工作表内容失败: {sheet_title}, error={content_result.get('msg')}")
                    markdown_content += f"## {sheet_title}\n\n获取工作表内容失败: {content_result.get('msg')}\n\n"
                    continue
                
                # 转换为Markdown表格
                values = content_result.get("data", {}).get("values", [])
                if not values:
                    markdown_content += f"## {sheet_title}\n\n此工作表暂无数据。\n\n"
                    continue
                
                # 过滤空行（所有单元格都为空的行）
                filtered_values = []
                for row in values:
                    if any(str(cell).strip() for cell in row if cell is not None):
                        filtered_values.append(row)
                
                if not filtered_values:
                    markdown_content += f"## {sheet_title}\n\n此工作表暂无有效数据。\n\n"
                    continue
                
                # 使用SheetConverter转换数据
                sheet_markdown = converter.convert_to_markdown(filtered_values, sheet_title)
                markdown_content += sheet_markdown + "\n\n"
                processed_sheets += 1
                
                # 添加间隔，避免API频率限制
                if processed_sheets > 0 and processed_sheets % 3 == 0:
                    await asyncio.sleep(0.2)  # 每处理3个工作表暂停200ms
            
            logger.info(f"成功获取电子表格内容: spreadsheet_token={spreadsheet_token}, 处理工作表数={processed_sheets}, 内容长度={len(markdown_content)}")
            
            return {
                "code": 0,
                "data": {
                    "content": markdown_content.strip(),
                    "revision": 0,
                    "method": "sheet-api-v2",
                    "processed_sheets": processed_sheets,
                    "total_sheets": len([s for s in sheets if not s.get("hidden", False)])
                }
            }
            
        except Exception as e:
            logger.error(f"获取电子表格内容异常: spreadsheet_token={spreadsheet_token}, error={str(e)}")
            return {
                "code": -1,
                "msg": f"获取电子表格内容异常: {str(e)}"
            }
