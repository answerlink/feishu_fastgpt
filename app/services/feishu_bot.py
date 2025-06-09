import json
import logging
import aiohttp
import asyncio
import re
import os
import tempfile
from typing import Dict, Any, Optional
from app.core.config import settings
from app.core.logger import setup_logger
from app.services.aichat_service import AIChatService

logger = setup_logger("feishu_bot")

class FeishuBotService:
    """飞书机器人服务"""
    
    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.base_url = settings.FEISHU_HOST
        
        # 获取应用配置中的AI Chat设置
        self.app_config = None
        for app in settings.FEISHU_APPS:
            if app.app_id == app_id:
                self.app_config = app
                break
        
        # 初始化AI Chat服务
        self.aichat_service = None
        if self.app_config and hasattr(self.app_config, 'aichat_enable') and self.app_config.aichat_enable:
            aichat_url = getattr(self.app_config, 'aichat_url', None)
            aichat_key = getattr(self.app_config, 'aichat_key', None)
            
            if aichat_url and aichat_key:
                self.aichat_service = AIChatService(aichat_url, aichat_key)
                logger.info(f"启用AI Chat服务: {aichat_url}")
            else:
                logger.warning("AI Chat配置不完整，将使用默认回复")
        else:
            logger.info("AI Chat功能未启用，将使用默认回复")
    
    async def get_tenant_access_token(self) -> str:
        """获取tenant_access_token（简化版，专门用于机器人）"""
        url = f"{self.base_url}/open-apis/auth/v3/tenant_access_token/internal"
        data = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }
        
        # 使用临时的客户端会话避免事件循环冲突
        async with aiohttp.ClientSession() as client:
            async with client.post(url, json=data) as response:
                result = await response.json()
                if result.get("code") != 0:
                    raise Exception(f"获取tenant_access_token失败: {result}")
                return result["tenant_access_token"]
    
    async def handle_message(self, event_data: Dict[str, Any]) -> bool:
        """处理接收到的消息"""
        try:
            # 解析消息数据
            message = event_data.get("event", {})
            sender = message.get("sender", {})
            message_content = message.get("message", {})
            
            # 获取发送者信息
            sender_id = sender.get("sender_id", {}).get("user_id")
            sender_type = sender.get("sender_type")
            
            # 获取消息内容
            content = message_content.get("content", "{}")
            message_type = message_content.get("message_type", "text")
            chat_id = message_content.get("chat_id")
            chat_type = message_content.get("chat_type")
            
            logger.info(f"处理消息 - 发送者: {sender_id}, 类型: {message_type}, 聊天: {chat_id} ({chat_type})")
            
            # 检查聊天类型配置，决定是否回复
            should_reply = False
            if chat_type == "p2p":
                # 单聊：检查aichat_reply_p2p配置
                should_reply = getattr(self.app_config, 'aichat_reply_p2p', True)
                logger.info(f"单聊消息，配置允许回复: {should_reply}")
            elif chat_type == "group":
                # 群聊：检查aichat_reply_group配置
                should_reply = getattr(self.app_config, 'aichat_reply_group', False)
                logger.info(f"群聊消息，配置允许回复: {should_reply}")
            else:
                logger.warning(f"未知聊天类型: {chat_type}")
                return True  # 对于未知类型，直接返回成功但不处理
            
            # 如果配置不允许回复，直接返回
            if not should_reply:
                logger.info(f"根据配置，{chat_type}类型聊天不回复消息")
                return True
            
            # 解析文本消息
            if message_type == "text":
                text_content = json.loads(content).get("text", "")
                logger.info(f"收到文本消息: {text_content}")
                
                # 确定接收者和接收者类型
                receive_id = None
                receive_id_type = None
                
                if chat_type == "p2p":
                    # 单聊，发送给发送者
                    receive_id = sender_id
                    receive_id_type = "user_id"
                elif chat_type == "group":
                    # 群聊，发送到群聊
                    receive_id = chat_id
                    receive_id_type = "chat_id"
                
                if not receive_id:
                    logger.error("无法确定消息接收者")
                    return False
                
                # 优先尝试使用流式卡片回复
                if self.aichat_service:
                    try:
                        logger.info("尝试使用流式卡片回复")
                        await self.generate_streaming_reply(text_content, sender_id, receive_id, receive_id_type)
                        logger.info("流式卡片回复已发送")
                        return True
                    except Exception as e:
                        logger.error(f"流式卡片回复失败，回退到普通文本回复: {str(e)}")
                        # 继续执行普通文本回复
                
                # 普通文本回复（回退方案）
                reply_text = await self.generate_reply(text_content, sender_id)
                await self.send_text_message(receive_id, reply_text, receive_id_type=receive_id_type)
                
            return True
            
        except Exception as e:
            logger.error(f"处理消息失败: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            return False
    
    async def get_collection_download_url(self, collection_id: str) -> Optional[str]:
        """获取collection的下载链接"""
        try:
            # 获取配置
            read_collection_url = getattr(self.app_config, 'aichat_read_collection_url', None)
            read_collection_key = getattr(self.app_config, 'aichat_read_collection_key', None)
            
            if not read_collection_url or not read_collection_key:
                logger.warning("AI Chat读取集合配置不完整，无法获取下载链接")
                return None
            
            headers = {
                "Authorization": f"Bearer {read_collection_key}",
                "Content-Type": "application/json"
            }
            
            body_data = {
                "collectionId": collection_id
            }
            
            # 使用临时的客户端会话
            async with aiohttp.ClientSession() as client:
                async with client.post(read_collection_url, json=body_data, headers=headers) as response:
                    result = await response.json()
                    
                    if result.get("code") == 200:
                        data = result.get("data", {})
                        file_value = data.get("value", "")
                        
                        if file_value and file_value.startswith("/"):
                            # 从read_collection_url中提取host部分
                            from urllib.parse import urlparse
                            parsed_url = urlparse(read_collection_url)
                            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
                            
                            # 拼接完整的下载链接
                            download_url = base_url + file_value
                            # logger.debug(f"获取到collection下载链接: {download_url}")
                            return download_url
                        else:
                            logger.warning(f"collection返回的value格式不正确: {file_value}")
                            return None
                    else:
                        logger.error(f"获取collection下载链接失败: {result}")
                        return None
                        
        except Exception as e:
            logger.error(f"获取collection下载链接异常: {str(e)}")
            return None

    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """获取用户详细信息"""
        try:
            token = await self.get_tenant_access_token()
            url = f"{self.base_url}/open-apis/contact/v3/users/{user_id}?user_id_type=user_id"
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            # 使用临时的客户端会话避免事件循环冲突
            async with aiohttp.ClientSession() as client:
                async with client.get(url, headers=headers) as response:
                    result = await response.json()
                    
                    if result.get("code") == 0:
                        user_data = result.get("data", {}).get("user", {})
                        
                        # 提取需要的字段
                        mobile = user_data.get("mobile", "")
                        name = user_data.get("name", "")
                        en_name = user_data.get("en_name", "")
                        user_id = user_data.get("user_id", "")
                        
                        # 处理姓名显示格式
                        display_name = name
                        if name and en_name:
                            display_name = f"{name}（{en_name}）"
                        elif en_name and not name:
                            display_name = en_name
                        
                        logger.info(f"获取用户信息成功: {display_name} ({user_id})")
                        
                        return {
                            "mobile": mobile,
                            "name": display_name,
                            "user_id": user_id,
                            "success": True
                        }
                    else:
                        logger.error(f"获取用户信息失败: {result}")
                        return {
                            "mobile": "",
                            "name": "用户",
                            "user_id": user_id,
                            "success": False
                        }
                        
        except Exception as e:
            logger.error(f"获取用户信息异常: {str(e)}")
            return {
                "mobile": "",
                "name": "用户", 
                "user_id": user_id,
                "success": False
            }

    async def generate_reply(self, user_message: str, user_id: str) -> str:
        """生成回复内容"""
        try:
            # 如果启用了AI Chat服务，优先使用AI回复
            if self.aichat_service:
                logger.info(f"使用AI Chat服务生成回复: user_id {user_id}, {user_message[:50]}...")
                
                # 获取用户详细信息
                user_info = await self.get_user_info(user_id)
                
                # 调用AI Chat接口
                ai_reply = await self.aichat_service.chat_completion(
                    chat_id="feishu_user_" + user_id,
                    message=user_message,
                    variables={
                        "feishu_user_id": user_info["user_id"],
                        "feishu_mobile": user_info["mobile"],
                        "feishu_name": user_info["name"]
                    }
                )
                
                if ai_reply and ai_reply.strip():
                    logger.info(f"AI回复成功，长度: {len(ai_reply)}")
                    return ai_reply
                else:
                    logger.warning("AI回复为空，使用默认回复")
            
            # 如果AI服务不可用或返回空内容，使用默认的关键词回复
            return self._get_default_reply(user_message)
            
        except Exception as e:
            logger.error(f"生成回复异常: {str(e)}")
            # 出现异常时返回默认回复
            return self._get_default_reply(user_message)

    async def generate_streaming_reply(self, user_message: str, user_id: str, receive_id: str, 
                                     receive_id_type: str = "user_id") -> str:
        """生成流式回复内容（使用卡片流式更新）"""
        try:
            # 如果启用了AI Chat服务，使用流式卡片回复
            if self.aichat_service:
                logger.info(f"使用AI Chat流式服务生成回复: user_id {user_id}, {user_message[:50]}...")
                
                # 获取用户详细信息
                user_info = await self.get_user_info(user_id)
                
                # 初始化当前卡片内容状态
                current_card_state = {
                    "user_message": user_message,
                    "sender_name": user_info["name"],  # 使用用户真实姓名
                    "status": "🔄 **正在准备**...",
                    "think_title": "💭 **准备思考中...**",
                    "think_content": "",
                    "answer_content": "",
                    "references_title": "📚 **知识库引用** (0)",
                    "references_content": "",
                    "image_cache": {},  # 添加图片缓存：{原始URL: 飞书img_key}
                    "processing_images": set()  # 添加正在处理的图片URL集合
                }
                
                # 1. 创建流式卡片
                card_content = self._build_card_content(current_card_state)
                card_result = await self._create_card_entity(card_content)
                
                if card_result.get("code") != 0:
                    logger.error(f"创建流式卡片失败: {card_result}")
                    # 回退到普通文本回复
                    return await self.generate_reply(user_message, user_id)
                
                card_id = card_result.get("data", {}).get("card_id")
                if not card_id:
                    logger.error("创建流式卡片成功但未获取到card_id")
                    return await self.generate_reply(user_message, user_id)
                
                # 2. 发送初始卡片消息
                send_result = await self._send_card_message_by_id(receive_id, card_id, receive_id_type)
                if send_result.get("code") != 0:
                    logger.error(f"发送流式卡片消息失败: {send_result}")
                    return await self.generate_reply(user_message, user_id)
                
                logger.info(f"流式卡片已发送: card_id={card_id}")
                
                # 3. 流式更新卡片内容
                sequence_counter = 1
                sequence_lock = asyncio.Lock()  # 序列号锁，确保并发安全
                think_title_updated = False  # 思考标题更新标志
                answer_title_updated = False  # 答案标题更新标志
                
                async def on_status_callback(status_text: str):
                    nonlocal sequence_counter, current_card_state
                    
                    # 在锁内部分配序列号并更新时间
                    async with sequence_lock:
                        current_sequence = sequence_counter
                        sequence_counter += 1
                        
                        # 更新卡片状态存储
                        current_card_state["status"] = status_text
                    
                        # 直接在锁内执行更新，避免异步任务的序列号冲突
                        update_result = await self._update_card_element_content(
                            card_id, "status", status_text, current_sequence
                        )
                        
                        if update_result.get("code") == 0:
                            # logger.debug(f"更新状态成功: {status_text}")
                            pass
                        else:
                            logger.error(f"更新状态失败: {update_result}")
                
                async def on_think_callback(think_text: str):
                    nonlocal sequence_counter, think_title_updated, current_card_state

                    async with sequence_lock:
                        # 首次有思考内容时，设置思考标题和思考内容（不受频率限制）
                        if not think_title_updated and think_text:
                            think_sequence = sequence_counter
                            sequence_counter += 1
                            think_title_updated = True  # 立即设置标志位
                            
                            think_title = "💭 **思考过程**"
                            current_card_state["think_title"] = think_title
                            current_card_state["think_content"] = " "

                            # 构建完整的卡片内容
                            complete_card_content = self._build_card_content(current_card_state)
                            
                            # 使用新的API进行全量更新
                            logger.info(f"准备进行引用内容全量更新: 思考部分")
                            update_result = await self._update_card_settings(card_id, complete_card_content, think_sequence)
                            
                            if update_result.get("code") == 0:
                                logger.info(f"全量更新思考面板标题成功: {think_title}")
                            else:
                                logger.error(f"全量更新思考面板标题失败: {update_result}")
                                think_title_updated = False  # 失败时重置标志位

                        think_sequence = sequence_counter
                        sequence_counter += 1
                        current_card_state["think_content"] = think_text
                        # 更新思考内容
                        update_result = await self._update_card_element_content(
                            card_id, "think_content", think_text, think_sequence
                        )
                        
                        if update_result.get("code") == 0:
                            # logger.debug(f"更新思考过程成功: 长度={len(think_text)}")
                            pass
                        else:
                            logger.error(f"更新思考过程失败: {update_result}")
                
                async def on_answer_callback(answer_text: str):
                    nonlocal sequence_counter, answer_title_updated, current_card_state
                    
                    # 处理文本中的图片链接（使用缓存避免重复处理）
                    try:
                        processed_answer_text = await self._process_images_in_text_with_cache(
                            answer_text, current_card_state["image_cache"], current_card_state["processing_images"]
                        )
                        
                        # 使用处理后的文本
                        answer_text = processed_answer_text
                        
                    except Exception as e:
                        logger.error(f"处理答案文本中的图片失败: {str(e)}")
                        # 图片处理失败时继续使用原文本
                    
                    # 构建答案内容
                    answer_content = f"**回答**\n\n{answer_text}"
                    current_card_state["answer_content"] = answer_content
                    
                    async with sequence_lock:
                        # 首次更新答案时，更新思考面板标题和答案内容（不受频率限制）
                        if not answer_title_updated and answer_text:
                            answer_sequence = sequence_counter
                            sequence_counter += 1
                            answer_title_updated = True  # 立即设置标志位
                            
                            think_title = "💭 **已完成思考**"
                            current_card_state["think_title"] = think_title
                            current_card_state["answer_content"] = " "
                            # 构建完整的卡片内容
                            complete_card_content = self._build_card_content(current_card_state)
                            
                            # 使用新的API进行全量更新
                            logger.info(f"准备进行引用内容全量更新: 答案部分")
                            update_result = await self._update_card_settings(card_id, complete_card_content, answer_sequence)
                            
                            if update_result.get("code") == 0:
                                logger.info(f"全量更新答案面板标题成功: {think_title}")
                            else:
                                logger.error(f"全量更新答案面板标题失败: {update_result}")
                                answer_title_updated = False  # 失败时重置标志位
                        
                        answer_sequence = sequence_counter
                        sequence_counter += 1
                        # 更新答案部分
                        update_result = await self._update_card_element_content(
                            card_id, "answer", answer_content, answer_sequence
                        )
                        
                        if update_result.get("code") == 0:
                            # logger.debug(f"更新答案成功: 长度={len(answer_text)}")
                            pass
                        else:
                            logger.error(f"更新答案失败: {update_result}")
                
                async def on_references_callback(references_data: list):
                    """处理引用数据回调"""
                    nonlocal sequence_counter, current_card_state
                    
                    try:
                        if references_data:
                            logger.info(f"收到 {len(references_data)} 条引用数据")
                            
                            # 更新卡片状态中的引用信息
                            current_card_state["references_title"] = f"📚 **知识库引用** ({len(references_data)})"
                            
                            # 构建引用内容
                            current_card_state["references_content"] = await self._get_references_content(references_data)

                            # 使用全量更新卡片
                            async with sequence_lock:
                                ref_sequence = sequence_counter
                                sequence_counter += 1
                                
                                # 构建完整的卡片内容
                                complete_card_content = self._build_card_content(current_card_state)
                                
                                # 使用新的API进行全量更新
                                logger.info(f"准备进行引用内容全量更新: 引用部分")
                                update_result = await self._update_card_settings(card_id, complete_card_content, ref_sequence)
                                
                                if update_result.get("code") == 0:
                                    logger.info(f"引用内容全量更新成功")
                                else:
                                    logger.error(f"引用内容全量更新失败: {update_result}")
                        else:
                            logger.debug("引用数据为空，跳过更新")
                    except Exception as e:
                        logger.error(f"处理引用数据异常: {str(e)}")
                
                # 调用AI Chat详细流式接口（使用新的回调结构）
                ai_reply = await self.aichat_service.chat_completion_streaming_enhanced(
                    chat_id="feishu_user_" + user_id,
                    message=user_message,
                    variables={
                        "feishu_user_id": user_info["user_id"],
                        "feishu_mobile": user_info["mobile"],
                        "feishu_name": user_info["name"]
                    },
                    on_status_callback=on_status_callback,
                    on_think_callback=on_think_callback,
                    on_answer_callback=on_answer_callback,
                    on_references_callback=on_references_callback
                )
                
                if ai_reply and ai_reply.strip():
                    logger.info(f"AI流式回复成功，长度: {len(ai_reply)}")
                    return ai_reply
                else:
                    logger.warning("AI流式回复为空")
                    # 更新卡片显示错误信息
                    error_content = "**回答**\n\n抱歉，我暂时无法理解您的问题，请换个方式提问。"
                    await self._update_card_element_content(card_id, "answer", error_content, sequence_counter)
                    return "抱歉，我暂时无法理解您的问题，请换个方式提问。"
            
            # 如果AI服务不可用，使用默认回复
            return self._get_default_reply(user_message)
            
        except Exception as e:
            logger.error(f"生成流式回复异常: {str(e)}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            # 出现异常时返回默认回复
            return self._get_default_reply(user_message)

    def _build_card_content(self, card_state: Dict[str, str] = None) -> Dict[str, Any]:
        """构建卡片内容（统一方法）
        
        Args:
            card_state: 当前卡片状态字典（用于更新时）
            sender_name: 发送者名称（用于创建时）
            
        Returns:
            Dict[str, Any]: 完整的卡片内容
        """
        
        # 构建基础卡片结构
        card = {
            "schema": "2.0",
            "header": {
                "title": {
                    "content": "🤖 AI助手",
                    "tag": "plain_text"
                }
            },
            "config": {
                "streaming_mode": True,
                "update_multi": True,
                "summary": {
                    "content": "AI正在思考中..."
                },
                "streaming_config": {
                    "print_frequency_ms": {
                        "default": 70,
                        "android": 70,
                        "ios": 70,
                        "pc": 70
                    },
                    "print_step": {
                        "default": 3
                    },
                    "print_strategy": "fast"
                }
            },
            "body": {
                "elements": []
            }
        }
        
        elements = card["body"]["elements"]
        
        # 1. 用户消息（总是显示）
        user_msg = card_state.get('user_message', "")
        sender_name = card_state.get('sender_name', "用户")
        if user_msg:
            elements.append({
                "tag": "markdown",
                "content": f"> {sender_name}：{user_msg}",
                "element_id": "refer"
            })
        else:
            elements.append({
                "tag": "markdown", 
                "content": "> 正在处理您的问题...",
                "element_id": "refer"
            })
        
        # 2. 状态显示（如果有状态且不为空）
        status = card_state.get("status", "")
        if status:
            elements.append({"tag": "hr"})
            elements.append({
                "tag": "markdown",
                "content": status,
                "element_id": "status"
            })
        
        # 3. 思考过程（如果有思考内容）
        think_content = card_state.get("think_content", "")
        think_title = card_state.get("think_title", "")
        
        if think_content:
            elements.append({"tag": "hr"})
            elements.append({
                "tag": "collapsible_panel",
                "expanded": True,
                "header": {
                    "title": {
                        "tag": "markdown",
                        "content": think_title,
                        "element_id": "think"
                    },
                    "width": "auto_when_fold",
                    "vertical_align": "center",
                    "padding": "4px 0px 4px 8px",
                    "icon": {
                        "tag": "standard_icon",
                        "token": "down-small-ccm_outlined",
                        "color": "",
                        "size": "16px 16px"
                    },
                    "icon_position": "follow_text",
                    "icon_expanded_angle": -180
                },
                "vertical_spacing": "8px",
                "padding": "8px 8px 8px 8px",
                "elements": [
                    {
                        "tag": "markdown",
                        "content": think_content,
                        "element_id": "think_content"
                    }
                ]
            })
        
        # 4. 答案内容（如果有答案）
        answer_content = card_state.get("answer_content", "")
        if answer_content:
            # 如果前面有内容，添加分割线
            if len(elements) > 1:
                elements.append({"tag": "hr"})
            elements.append({
                "tag": "markdown",
                "content": answer_content,
                "element_id": "answer"
            })
        
        # 5. 引用内容（如果有引用）
        references_content = card_state.get("references_content", "")
        references_title = card_state.get("references_title", "")
        
        if references_content:
            elements.append({"tag": "hr"})
            elements.append({
                "tag": "collapsible_panel",
                "expanded": False,
                "header": {
                    "title": {
                        "tag": "markdown",
                        "content": references_title,
                        "element_id": "references_title"
                    },
                    "width": "auto_when_fold",
                    "vertical_align": "center",
                    "padding": "4px 0px 4px 8px",
                    "icon": {
                        "tag": "standard_icon",
                        "token": "down-small-ccm_outlined",
                        "color": "blue",
                        "size": "16px 16px"
                    },
                    "icon_position": "follow_text",
                    "icon_expanded_angle": -180
                },
                "vertical_spacing": "4px",
                "padding": "8px 8px 8px 8px",
                "background_style": "grey",
                "element_id": "references_panel",
                "elements": [
                    {
                        "tag": "markdown",
                        "content": references_content,
                        "element_id": "references_content"
                    }
                ]
            })
        
        return card

    async def _create_card_entity(self, card_content: Dict[str, Any]) -> dict:
        """创建卡片实体（内部方法）"""
        import json
        
        try:
            token = await self.get_tenant_access_token()
            url = f"{self.base_url}/open-apis/cardkit/v1/cards"
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            # 按照正确的API格式构建请求体
            body_data = {
                "data": json.dumps(card_content),  # 将卡片内容序列化为JSON字符串
                "type": "card_json"
            }
            
            logger.info(f"创建卡片实体: {body_data}")
            
            # 使用临时的客户端会话避免事件循环冲突
            async with aiohttp.ClientSession() as client:
                async with client.post(url, json=body_data, headers=headers) as response:
                    result = await response.json()
                    
                    if result.get("code") == 0:
                        card_id = result.get("data", {}).get("card_id")
                        logger.info(f"卡片实体创建成功: card_id={card_id}")
                        return {
                            "code": 0,
                            "data": {"card_id": card_id}
                        }
                    else:
                        logger.error(f"创建卡片实体失败: {result}")
                        return {
                            "code": result.get("code", -1),
                            "msg": result.get("msg", "创建卡片实体失败")
                        }
                    
        except Exception as e:
            logger.error(f"创建卡片实体异常: {str(e)}")
            return {
                "code": -1,
                "msg": f"创建卡片实体异常: {str(e)}"
            }

    async def _send_card_message_by_id(self, receive_id: str, card_id: str, receive_id_type: str = "user_id") -> dict:
        """使用卡片ID发送卡片消息"""
        try:
            message_data = {
                "receive_id": receive_id,
                "msg_type": "interactive",
                "content": json.dumps({
                    "type": "card",
                    "data": {"card_id": card_id}
                })
            }
            
            token = await self.get_tenant_access_token()
            url = f"{self.base_url}/open-apis/im/v1/messages?receive_id_type={receive_id_type}"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            # 使用临时的客户端会话避免事件循环冲突
            async with aiohttp.ClientSession() as client:
                async with client.post(url, json=message_data, headers=headers) as response:
                    result = await response.json()
                    
                    if result.get("code") == 0:
                        return {
                            "code": 0,
                            "data": result.get("data", {})
                        }
                    else:
                        logger.error(f"发送卡片消息失败: {result}")
                        return {
                            "code": result.get("code", -1),
                            "msg": result.get("msg", "发送卡片消息失败")
                        }
                    
        except Exception as e:
            logger.error(f"发送卡片消息异常: {str(e)}")
            return {
                "code": -1,
                "msg": f"发送卡片消息异常: {str(e)}"
            }

    async def _update_card_streaming_text(self, card_id: str, element_id: str, text_content: str) -> dict:
        """流式更新卡片文本内容（内部方法）"""
        try:
            token = await self.get_tenant_access_token()
            url = f"{self.base_url}/open-apis/interactive/v1/card/{card_id}/update_streaming_text"
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            body_data = {
                "element_id": element_id,
                "content": text_content
            }
            
            # 使用临时的客户端会话避免事件循环冲突
            async with aiohttp.ClientSession() as client:
                async with client.patch(url, json=body_data, headers=headers) as response:
                    result = await response.json()
                    
                    if result.get("code") == 0:
                        return {
                            "code": 0,
                            "data": result.get("data", {})
                        }
                    else:
                        logger.debug(f"流式更新卡片文本失败: {result}")
                        return {
                            "code": result.get("code", -1),
                            "msg": result.get("msg", "流式更新卡片文本失败")
                        }
                    
        except Exception as e:
            logger.error(f"流式更新卡片文本异常: {str(e)}")
            return {
                "code": -1,
                "msg": f"流式更新卡片文本异常: {str(e)}"
            }

    async def _update_card_element_content(self, card_id: str, element_id: str, content: str, sequence: int = 1) -> dict:
        """使用新的API更新卡片元素内容
        
        Args:
            card_id: 卡片实体ID
            element_id: 元素ID (refer/think/think_content/answer/references_content)
            content: 更新的内容
            sequence: 序列号，用于控制更新顺序
            
        Returns:
            dict: 更新结果
        """
        try:
            token = await self.get_tenant_access_token()
            url = f"{self.base_url}/open-apis/cardkit/v1/cards/{card_id}/elements/{element_id}/content"
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            body_data = {
                "content": content,
                "sequence": sequence
            }
            
            # 使用临时的客户端会话避免事件循环冲突
            async with aiohttp.ClientSession() as client:
                async with client.put(url, json=body_data, headers=headers) as response:
                    result = await response.json()
                    
                    if result.get("code") == 0:
                        # logger.debug(f"卡片元素更新成功: element_id={element_id}, sequence={sequence}")
                        return {
                            "code": 0,
                            "data": result.get("data", {})
                        }
                    else:
                        logger.debug(f"卡片元素更新失败: {result}")
                        return {
                            "code": result.get("code", -1),
                            "msg": result.get("msg", "卡片元素更新失败")
                        }
                    
        except Exception as e:
            logger.error(f"卡片元素更新异常: {str(e)}")
            return {
                "code": -1,
                "msg": f"卡片元素更新异常: {str(e)}"
            }

    async def _get_references_content(self, references_data: list) -> str:
        """构建引用内容
        
        Args:
            references_data: 引用数据列表，每个元素包含 {source_name, content, module_name, collection_id}
        """
        try:
            if not references_data:
                return None
            
            # 构建引用内容
            references_content = ""
            for i, ref in enumerate(references_data, 1):
                source_name = ref.get("source_name", "未知来源")
                content = ref.get("content", "")
                module_name = ref.get("module_name", "未知模块")
                collection_id = ref.get("collection_id", "")
                
                # 限制内容长度，避免卡片过长
                content_preview = content[:300] + "..." if len(content) > 300 else content
                
                # 构建基础引用信息
                ref_content = f"""**{i}. {source_name}**
> 📂 来源模块：{module_name}

```
{content_preview}
```"""
                
                # 如果有collection_id，尝试获取下载链接
                if collection_id:
                    try:
                        download_url = await self.get_collection_download_url(collection_id)
                        if download_url:
                            # 使用飞书支持的HTML Link标签格式
                            ref_content += f"\n\n🔗 <link url=\"{download_url}\">点击下载原文件</link>"
                        else:
                            ref_content += f"\n\n📄 文档ID: {collection_id}"
                    except Exception as e:
                        logger.warning(f"获取collection_id {collection_id} 下载链接失败: {str(e)}")
                        ref_content += f"\n\n📄 文档ID: {collection_id}"
                
                references_content += ref_content + "\n\n---\n\n"
            
            return references_content.strip()
        except Exception as e:
            logger.error(f"构建引用内容异常: {str(e)}")
            return None

    async def _close_streaming_mode(self, card_id: str) -> dict:
        """关闭流式模式（内部方法）"""
        try:
            token = await self.get_tenant_access_token()
            url = f"{self.base_url}/open-apis/interactive/v1/card/{card_id}/update_config"
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            body_data = {
                "config": {
                    "streaming_mode": False
                }
            }
            
            # 使用临时的客户端会话避免事件循环冲突
            async with aiohttp.ClientSession() as client:
                async with client.patch(url, json=body_data, headers=headers) as response:
                    result = await response.json()
                    
                    if result.get("code") == 0:
                        return {
                            "code": 0,
                            "data": result.get("data", {})
                        }
                    else:
                        logger.error(f"关闭流式模式失败: {result}")
                        return {
                            "code": result.get("code", -1),
                            "msg": result.get("msg", "关闭流式模式失败")
                        }
                    
        except Exception as e:
            logger.error(f"关闭流式模式异常: {str(e)}")
            return {
                "code": -1,
                "msg": f"关闭流式模式异常: {str(e)}"
            }
    
    def _get_default_reply(self, user_message: str) -> str:
        """获取默认回复（关键词匹配）"""
        if "帮助" in user_message or "help" in user_message.lower():
            return """🤖 飞书机器人帮助：
            
1. 发送任意消息与我对话
2. 输入"文档"查看文档功能
3. 输入"知识库"查看知识库功能
4. 输入"帮助"查看此帮助信息

有什么问题随时问我哦～"""
        
        elif "文档" in user_message:
            return "📄 文档功能：\n- 创建文档\n- 搜索文档\n- 文档协作\n\n请告诉我你想要什么文档操作？"
        
        elif "知识库" in user_message:
            return "📚 知识库功能：\n- 知识搜索\n- 知识管理\n- 智能问答\n\n请输入你想要查询的内容？"
        
        else:
            # 默认智能回复
            return f'收到你的消息：{user_message}\n\n我是飞书智能助手，可以帮你处理文档和知识库相关的工作。输入"帮助"了解更多功能。'
    
    async def send_text_message(self, receive_id: str, text: str, receive_id_type: str = "user_id") -> bool:
        """发送文本消息"""
        try:
            message_data = {
                "receive_id": receive_id,
                "msg_type": "text",
                "content": json.dumps({"text": text})
            }
            
            logger.info(f"发送消息到 {receive_id} ({receive_id_type}): {text[:100]}...")
            
            # 获取access token
            token = await self.get_tenant_access_token()
            
            # 使用正确的发送消息API
            url = f"{self.base_url}/open-apis/im/v1/messages?receive_id_type={receive_id_type}"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            # 使用临时的客户端会话避免事件循环冲突
            async with aiohttp.ClientSession() as client:
                async with client.post(url, json=message_data, headers=headers) as response:
                    result = await response.json()
                    
                    if result.get("code") == 0:
                        logger.info(f"消息发送成功")
                        return True
                    else:
                        logger.error(f"消息发送失败: {result}")
                        return False
            
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            return False
    
    async def send_card_message(self, receive_id: str, card_content: Dict, receive_id_type: str = "user_id") -> bool:
        """发送卡片消息"""
        try:
            message_data = {
                "receive_id": receive_id,
                "msg_type": "interactive",
                "content": json.dumps(card_content)
            }
            
            logger.info(f"发送卡片消息到 {receive_id} ({receive_id_type})")
            
            # 获取access token
            token = await self.get_tenant_access_token()
            
            # 使用正确的发送消息API
            url = f"{self.base_url}/open-apis/im/v1/messages?receive_id_type={receive_id_type}"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            # 使用临时的客户端会话避免事件循环冲突
            async with aiohttp.ClientSession() as client:
                async with client.post(url, json=message_data, headers=headers) as response:
                    result = await response.json()
                    
                    if result.get("code") == 0:
                        logger.info(f"卡片消息发送成功")
                        return True
                    else:
                        logger.error(f"卡片消息发送失败: {result}")
                        return False
            
        except Exception as e:
            logger.error(f"发送卡片消息失败: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            return False
    
    async def close(self):
        """关闭服务"""
        if self.aichat_service:
            await self.aichat_service.close()
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()

    async def _update_card_settings(self, card_id: str, card_content: Dict[str, Any], sequence: int = 1) -> dict:
        """使用新的API全量更新卡片设置和内容
        
        Args:
            card_id: 卡片实体ID
            card_content: 完整的卡片内容
            sequence: 序列号，用于控制更新顺序
            
        Returns:
            dict: 更新结果
        """
        try:
            token = await self.get_tenant_access_token()
            url = f"{self.base_url}/open-apis/cardkit/v1/cards/{card_id}"
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            # 构建请求体，按照官方API格式
            body_data = {
                "card": {
                    "data": json.dumps(card_content),  # 卡片内容序列化为JSON字符串
                    "type": "card_json"
                },
                "sequence": sequence
            }
            
            # logger.info(f"全量更新卡片请求: card_content={card_content}")
            
            # 使用临时的客户端会话避免事件循环冲突
            async with aiohttp.ClientSession() as client:
                async with client.put(url, json=body_data, headers=headers) as response:
                    result = await response.json()
                    
                    if result.get("code") == 0:
                        logger.debug(f"卡片全量更新成功: card_id={card_id}, sequence={sequence}")
                        return {
                            "code": 0,
                            "data": result.get("data", {})
                        }
                    else:
                        logger.debug(f"卡片全量更新失败: {result}")
                        return {
                            "code": result.get("code", -1),
                            "msg": result.get("msg", "卡片全量更新失败")
                        }
                    
        except Exception as e:
            # logger.error(f"卡片全量更新异常: {str(e)}")
            return {
                "code": -1,
                "msg": f"卡片全量更新异常: {str(e)}"
            }

    async def _download_image(self, image_url: str) -> Optional[str]:
        """下载图片到本地临时文件
        
        Args:
            image_url: 图片URL
            
        Returns:
            str: 本地文件路径，失败返回None
        """
        try:
            # 创建临时文件
            suffix = os.path.splitext(image_url.split('?')[0])[-1] or '.jpg'
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            temp_path = temp_file.name
            temp_file.close()
            
            logger.info(f"开始下载图片: {image_url}")
            
            # 下载图片
            async with aiohttp.ClientSession() as client:
                async with client.get(image_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        with open(temp_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                        
                        logger.info(f"图片下载成功: {image_url} -> {temp_path}")
                        return temp_path
                    else:
                        logger.error(f"下载图片失败，状态码: {response.status}, URL: {image_url}")
                        os.unlink(temp_path)  # 删除临时文件
                        return None
                        
        except Exception as e:
            logger.error(f"下载图片异常: {str(e)}, URL: {image_url}")
            # 清理可能创建的临时文件
            if 'temp_path' in locals() and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except:
                    pass
            return None

    async def _upload_image_to_feishu(self, image_path: str) -> Optional[str]:
        """上传图片到飞书图床
        
        Args:
            image_path: 本地图片文件路径
            
        Returns:
            str: 飞书图片key，失败返回None
        """
        try:
            if not os.path.exists(image_path):
                logger.error(f"图片文件不存在: {image_path}")
                return None
            
            # 获取access token
            token = await self.get_tenant_access_token()
            url = f"{self.base_url}/open-apis/im/v1/images"
            
            headers = {
                "Authorization": f"Bearer {token}"
            }
            
            # 构建multipart/form-data请求
            with open(image_path, 'rb') as f:
                data = aiohttp.FormData()
                data.add_field('image_type', 'message')
                data.add_field('image', f, filename=os.path.basename(image_path), 
                             content_type='application/octet-stream')
                
                async with aiohttp.ClientSession() as client:
                    async with client.post(url, headers=headers, data=data) as response:
                        result = await response.json()
                        
                        if result.get("code") == 0:
                            image_key = result.get("data", {}).get("image_key")
                            logger.info(f"图片上传到飞书成功: {image_path} -> {image_key}")
                            return image_key
                        else:
                            logger.error(f"上传图片到飞书失败: {result}")
                            return None
                            
        except Exception as e:
            logger.error(f"上传图片到飞书异常: {str(e)}")
            return None
        finally:
            # 清理临时文件
            try:
                if os.path.exists(image_path):
                    os.unlink(image_path)
                    logger.debug(f"清理临时文件: {image_path}")
            except Exception as e:
                logger.warning(f"清理临时文件失败: {str(e)}")

    async def _process_images_in_text_with_cache(self, text: str, image_cache: dict, processing_images: set) -> str:
        """处理文本中的图片链接，使用缓存避免重复处理
        
        Args:
            text: 包含markdown图片链接的文本
            image_cache: 图片缓存字典，键为原始URL，值为飞书img_key
            processing_images: 正在处理的图片URL集合
            
        Returns:
            str: 处理后的文本，图片链接已替换为飞书格式
        """
        try:
            # 匹配markdown格式的图片：![alt](url)
            image_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
            matches = re.finditer(image_pattern, text)
            
            # 存储需要替换的内容
            replacements = []
            
            for match in matches:
                alt_text = match.group(1)
                image_url = match.group(2)
                full_match = match.group(0)
                
                # 检查是否已经是飞书图片格式（避免重复处理）
                if image_url.startswith('img_'):
                    logger.debug(f"图片已是飞书格式，跳过: {image_url}")
                    continue
                
                # 处理相对路径图片（以 / 开头的路径）
                original_url = image_url  # 保存原始URL用于缓存键
                if image_url.startswith('/') and self.app_config:
                    fastgpt_url = getattr(self.app_config, 'fastgpt_url', None)
                    if fastgpt_url:
                        # 拼接完整URL
                        full_image_url = fastgpt_url.rstrip('/') + image_url
                        logger.info(f"检测到相对路径图片，转换为完整URL: {image_url} -> {full_image_url}")
                        image_url = full_image_url
                    else:
                        logger.warning(f"fastgpt_url未配置，无法处理相对路径图片: {image_url}")
                        continue
                
                # 检查缓存中是否已有处理结果（使用原始URL作为缓存键）
                cache_key = original_url
                if cache_key in image_cache:
                    image_key = image_cache[cache_key]
                    new_link = f"![{alt_text}]({image_key})"
                    replacements.append((full_match, new_link))
                    # logger.debug(f"使用缓存图片: {cache_key} -> {image_key}")
                    continue
                
                # 检查是否正在处理中（使用原始URL作为键）
                if cache_key in processing_images:
                    logger.debug(f"图片正在处理中，跳过: {cache_key}")
                    continue
                
                # 新图片，需要下载和上传
                logger.info(f"发现新图片链接，开始处理: {image_url}")
                logger.debug(f"缓存中没有找到此URL，当前缓存: {list(image_cache.keys())}")
                
                # 标记为处理中（使用原始URL作为键）
                processing_images.add(cache_key)
                
                try:
                    local_path = await self._download_image(image_url)
                    if not local_path:
                        logger.warning(f"下载图片失败，保留原链接: {image_url}")
                        continue
                    
                    # 上传到飞书图床
                    image_key = await self._upload_image_to_feishu(local_path)
                    if image_key:
                        # 飞书图片格式：![alt](img_key)
                        new_link = f"![{alt_text}]({image_key})"
                        replacements.append((full_match, new_link))
                        # 缓存处理结果（使用原始URL作为缓存键）
                        image_cache[cache_key] = image_key
                        logger.info(f"新图片处理成功: {image_url} -> {image_key}")
                        logger.debug(f"已添加到缓存，当前缓存大小: {len(image_cache)}")
                    else:
                        logger.warning(f"上传图片到飞书失败，保留原链接: {image_url}")
                        
                finally:
                    # 无论成功失败，都要从处理中集合移除（使用原始URL作为键）
                    processing_images.discard(cache_key)
                    logger.debug(f"从处理中集合移除: {cache_key}")
            
            # 执行替换
            processed_text = text
            for old_link, new_link in replacements:
                processed_text = processed_text.replace(old_link, new_link)
            
            return processed_text
            
        except Exception as e:
            logger.error(f"处理图片链接异常: {str(e)}")
            return text  # 出错时返回原文本
    