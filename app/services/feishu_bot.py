import json
import logging
import aiohttp
import asyncio
import re
import os
import tempfile
import shutil
import uuid
from typing import Dict, Any, Optional, List
from app.core.config import settings
from app.core.logger import setup_logger, setup_app_logger
from app.services.aichat_service import AIChatService
from app.utils.asr_service import ASRService
from app.services.chat_message_service import chat_message_service
from app.services.user_memory_service import UserMemoryService

# 检查是否在单应用模式
single_app_mode = os.environ.get('FEISHU_SINGLE_APP_MODE', 'false').lower() == 'true'
target_app_id = os.environ.get('FEISHU_SINGLE_APP_ID') if single_app_mode else None

# 根据模式选择logger设置方式
if single_app_mode and target_app_id:
    # 单应用模式：查找应用配置并使用专用logger
    target_app = None
    for app in settings.FEISHU_APPS:
        if app.app_id == target_app_id:
            target_app = app
            break
    
    if target_app:
        logger = setup_app_logger("feishu_bot", target_app.app_id, target_app.app_name)
    else:
        logger = setup_logger("feishu_bot")
else:
    # 多应用模式：使用全局logger
    logger = setup_logger("feishu_bot")

class FeishuBotService:
    """飞书机器人服务"""
    
    # 类级别的停止标志存储，所有实例共享
    _class_stop_flags = {}
    
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
        
        # 初始化ASR服务
        self.asr_service = None
        if self.app_config and hasattr(self.app_config, 'asr_api_url'):
            asr_api_url = getattr(self.app_config, 'asr_api_url', None)
            asr_api_key = getattr(self.app_config, 'asr_api_key', None)
            if asr_api_url:
                self.asr_service = ASRService(asr_api_url, asr_api_key)
                logger.info(f"启用ASR服务: {asr_api_url}")
                if asr_api_key:
                    logger.info("ASR API认证已配置")
            else:
                logger.info("ASR配置不完整，将跳过语音转文字")
        else:
            logger.info("ASR功能未配置，将跳过语音转文字")
        
        # 初始化群聊数据库服务
        self.chat_message_service = chat_message_service
        
        # 初始化用户记忆服务
        self.user_memory_service = UserMemoryService()
        logger.info("用户记忆服务已初始化")
    
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
    

    
    def process_mentions_and_check_bot(self, message_content: Dict[str, Any]) -> tuple[str, str, bool]:
        """处理消息中的mentions并检查是否@了机器人
        
        Args:
            message_content: 消息内容
            
        Returns:
            tuple: (raw_content, pure_content, mentioned_bot)
                - raw_content: 替换@_user_x为真实姓名后的内容
                - pure_content: 去除所有@信息后的纯净内容
                - mentioned_bot: 是否@了机器人
        """
        try:
            content = message_content.get("content", "{}")
            message_type = message_content.get("message_type", "text")
            mentions = message_content.get("mentions", [])

            if message_type != "text":
                return content, content, False
            
            # 解析文本内容
            try:
                text_content = json.loads(content).get("text", "")
            except:
                text_content = content
            
            raw_content = text_content
            pure_content = text_content
            mentioned_bot = False
            
            # 获取机器人名称（使用app_name）
            app_name = getattr(self.app_config, 'app_name', 'AI助手') if self.app_config else 'AI助手'
            
            # 处理mentions
            if mentions:
                for mention in mentions:
                    key = mention.get("key", "")  # 例如: @_user_1
                    name = mention.get("name", "")  # 例如: 徐枫
                    
                    if key and name:
                        # 检查key是否在内容中
                        if key in raw_content:
                            # 将raw_content中的@_user_x替换为@真实姓名
                            old_raw = raw_content
                            raw_content = raw_content.replace(key, f"@{name}")
                        
                        # 检查是否@了机器人（通过姓名匹配）
                        if name == app_name:
                            mentioned_bot = True
                            logger.info(f"检测到@机器人: {name}")
                        else:
                            logger.debug(f"@的是其他用户: '{name}' != '{app_name}'")
                        
                        # 从pure_content中移除@信息（包括空格）
                        if key in pure_content:
                            old_pure = pure_content
                            pure_content = pure_content.replace(key, "").strip()
                            # 如果有多个连续空格，替换为单个空格
                            import re
                            pure_content = re.sub(r'\s+', ' ', pure_content).strip()
            
            # 如果没有通过mentions检测到@机器人，再检查文本内容中是否直接包含@机器人名称
            if not mentioned_bot and f"@{app_name}" in raw_content:
                mentioned_bot = True
                logger.info(f"在文本内容中检测到@机器人: @{app_name}")
            
            logger.debug(f"消息处理结果 - 原始: '{text_content}' -> raw: '{raw_content}' -> pure: '{pure_content}' -> @bot: {mentioned_bot}")
            
            return raw_content, pure_content, mentioned_bot
            
        except Exception as e:
            logger.error(f"处理mentions异常: {str(e)}")
            # 出错时返回原内容
            try:
                text_content = json.loads(content).get("text", "")
            except:
                text_content = content
            return text_content, text_content, False
    
    def extract_mention_users(self, message_content: Dict[str, Any]) -> List[str]:
        """提取消息中@的所有用户名称
        
        Args:
            message_content: 消息内容
            
        Returns:
            List[str]: 被@的用户名称列表
        """
        try:
            mentions = message_content.get("mentions", [])
            mention_users = []
            
            for mention in mentions:
                name = mention.get("name", "")
                if name:
                    mention_users.append(name)
            
            return mention_users
            
        except Exception as e:
            logger.error(f"提取@用户列表异常: {str(e)}")
            return []
    
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
            message_id = message_content.get("message_id")
            
            logger.info(f"处理消息 - 发送者: {sender_id}, 类型: {message_type}, 聊天: {chat_id} ({chat_type})")
            
            # 获取发送者信息用于消息记录
            user_info = await self.get_user_info(sender_id)
            sender_name = user_info.get("name", "未知用户")
            
            # 获取配置项
            p2p_reply_enabled = getattr(self.app_config, 'aichat_reply_p2p', True)
            group_reply_enabled = getattr(self.app_config, 'aichat_reply_group', False)
            
            # 群聊消息记录（根据配置决定是否记录）
            mentioned_bot = False  # 初始化默认值
            if chat_type == "group" and group_reply_enabled:
                try:
                    # 处理mentions并检查是否@机器人
                    raw_content, pure_content, mentioned_bot = self.process_mentions_and_check_bot(message_content)
                    
                    # 提取@的用户列表
                    mention_users = self.extract_mention_users(message_content)
                    
                    # 获取群聊信息
                    chat_info = await self.get_chat_info(chat_id)
                    chat_name = chat_info.get("name", "未知群聊")
                    
                    # 解析消息内容用于记录
                    if message_type == "text":
                        display_raw_content = raw_content
                        display_pure_content = pure_content
                    elif message_type == "image":
                        display_raw_content = "[图片]"
                        display_pure_content = "[图片]"
                    elif message_type == "file":
                        display_raw_content = "[文件]"
                        display_pure_content = "[文件]"
                    elif message_type == "audio":
                        display_raw_content = "[语音]"
                        display_pure_content = "[语音]"
                    elif message_type == "post":
                        display_raw_content = "[富文本]"
                        display_pure_content = "[富文本]"
                    else:
                        display_raw_content = f"[{message_type}]"
                        display_pure_content = f"[{message_type}]"
                    
                    # 创建消息数据并保存到数据库
                    message_data = {
                        "app_id": self.app_id,
                        "message_id": message_id,
                        "chat_type": "group",
                        "chat_id": chat_id,
                        "chat_name": chat_name,
                        "sender_id": sender_id,
                        "sender_name": sender_name,
                        "raw_content": display_raw_content,
                        "pure_content": display_pure_content,
                        "message_type": message_type,
                        "mention_users": mention_users,
                        "mentioned_bot": mentioned_bot,
                    }
                    
                    # 保存群聊消息到数据库
                    save_success = await self.chat_message_service.save_message(message_data)
                    
                    if not save_success:
                        logger.error(f"记录群聊消息失败: 数据库保存失败")
                        return False
                    
                except Exception as e:
                    logger.error(f"记录群聊消息失败: {str(e)}")
                    # 如果上面的逻辑失败，使用默认值
                    mentioned_bot = False
            
            # 处理私聊消息记录（根据配置决定是否记录）
            if chat_type == "p2p" and p2p_reply_enabled:
                try:
                    # 解析消息内容用于记录
                    if message_type == "text":
                        display_raw_content = content.strip('"')  # 去除JSON字符串的引号
                        # 解析JSON获取纯文本内容
                        try:
                            text_data = json.loads(display_raw_content)
                            display_pure_content = text_data.get("text", display_raw_content)
                        except (json.JSONDecodeError, AttributeError):
                            display_pure_content = display_raw_content
                    elif message_type == "image":
                        display_raw_content = "[图片]"
                        display_pure_content = "[图片]"
                    elif message_type == "file":
                        display_raw_content = "[文件]"
                        display_pure_content = "[文件]"
                    elif message_type == "audio":
                        display_raw_content = "[语音]"
                        display_pure_content = "[语音]"
                    elif message_type == "post":
                        display_raw_content = "[富文本]"
                        display_pure_content = "[富文本]"
                    else:
                        display_raw_content = f"[{message_type}]"
                        display_pure_content = f"[{message_type}]"
                    
                    # 创建私聊消息数据并保存到数据库
                    message_data = {
                        "app_id": self.app_id,
                        "message_id": message_id,
                        "chat_type": "p2p",
                        "chat_id": chat_id,
                        "chat_name": "",
                        "sender_id": sender_id,
                        "sender_name": sender_name,
                        "raw_content": display_raw_content,
                        "pure_content": display_pure_content,
                        "message_type": message_type,
                        "mention_users": [],  # 私聊没有@功能
                        "mentioned_bot": False,  # 私聊不需要@机器人
                    }
                    
                    # 保存私聊消息到数据库
                    save_success = await self.chat_message_service.save_message(message_data)
                    
                    if not save_success:
                        logger.error(f"记录私聊消息失败: 数据库保存失败")
                    else:
                        logger.debug(f"私聊消息已保存: {message_id}")
                        
                except Exception as e:
                    logger.error(f"记录私聊消息失败: {str(e)}")
            
            # 检查聊天类型配置，决定是否回复
            should_reply = False
            
            if chat_type == "p2p":
                should_reply = p2p_reply_enabled
                logger.info(f"单聊消息，配置允许回复: {should_reply}")
                
            elif chat_type == "group":
                if not group_reply_enabled:
                    logger.info("群聊回复功能未启用")
                    should_reply = False
                else:
                    trigger_mode = getattr(self.app_config, 'aichat_reply_group_trigger_mode', 'at')
                    if trigger_mode == "at":
                        # at模式：只有@机器人时才回复
                        # mentioned_bot已经在上面的群聊消息记录部分设置了
                        should_reply = mentioned_bot
                    elif trigger_mode == "all":
                        # all模式：回复所有消息
                        should_reply = True
                    elif trigger_mode == "auto":
                        # auto模式：自动判断（暂时未实现，默认为at模式）
                        # mentioned_bot已经在上面的群聊消息记录部分设置了
                        should_reply = mentioned_bot
                        logger.info(f"自动模式@检测结果: {mentioned_bot}")
                    else:
                        logger.warning(f"未知的群聊触发模式: {trigger_mode}")
                        should_reply = False
            else:
                logger.warning(f"未知聊天类型: {chat_type}")
                return True  # 对于未知类型，直接返回成功但不处理
            
            # 如果配置不允许回复，直接返回
            if not should_reply:
                logger.info(f"根据配置，{chat_type}类型聊天不回复消息 (mentioned_bot: {mentioned_bot})")
                return True
            
            # 处理语音消息
            if message_type == "audio":
                try:
                    # 解析语音消息内容
                    audio_content = json.loads(content)
                    file_key = audio_content.get("file_key")
                    duration = audio_content.get("duration", 0)
                    
                    logger.info(f"收到语音消息: file_key={file_key}, duration={duration}ms")
                    
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
                        logger.error("无法确定音频消息接收者")
                        return True  # 继续处理，不算错误
                    
                    # 下载语音文件
                    if file_key:
                        # 获取tenant_access_token
                        token = await self.get_tenant_access_token()
                        logger.info(f"获取到tenant_access_token: {token[:10]}...")
                        
                        # 构建下载URL (添加type参数，语音消息类型为audio)
                        url = f"{self.base_url}/open-apis/im/v1/messages/{message_id}/resources/{file_key}?type=file"
                        headers = {
                            "Authorization": f"Bearer {token}"
                        }
                        
                        logger.info(f"准备下载语音文件: {url}")
                        
                        # 创建临时目录用于存储语音文件
                        temp_dir = os.path.join(os.getcwd(), "temp", "audio")
                        os.makedirs(temp_dir, exist_ok=True)
                        logger.info(f"创建临时目录: {temp_dir}")
                        
                        # 下载文件
                        async with aiohttp.ClientSession() as client:
                            logger.info("开始下载语音文件...")
                            async with client.get(url, headers=headers) as response:
                                logger.info(f"下载响应状态码: {response.status}")
                                if response.status == 200:
                                    # 保存音频文件（opus格式）
                                    audio_file_name = f"{file_key}.opus"
                                    audio_file_path = os.path.join(temp_dir, audio_file_name)
                                    
                                    # 保存音频文件
                                    content = await response.read()
                                    logger.info(f"下载到文件大小: {len(content)} bytes")
                                    
                                    with open(audio_file_path, "wb") as f:
                                        f.write(content)
                                    
                                    logger.info(f"语音文件下载成功: {audio_file_path}")
                                    
                                    # 直接进行语音转文字(ASR)处理
                                    if self.asr_service:
                                        await self._process_audio_transcription(audio_file_path, sender_id, receive_id, receive_id_type)
                                    else:
                                        logger.info("ASR服务未配置，跳过语音转文字")
                                    
                                else:
                                    error_text = await response.text()
                                    logger.error(f"下载语音文件失败: {response.status}, 错误信息: {error_text}")
                    
                except Exception as e:
                    logger.error(f"处理语音消息失败: {str(e)}")
                    import traceback
                    logger.error(f"错误详情: {traceback.format_exc()}")
            
            # 解析文本消息
            elif message_type == "text":
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
                        
                        # 构建消息内容（群聊时可能需要包含上下文）
                        message_content_for_ai = [{"type": "text", "text": text_content}]
                        
                        # 如果是群聊且@了机器人，添加群聊上下文并使用pure_content
                        if chat_type == "group" and mentioned_bot:
                            # 使用pure_content作为真正的问题内容
                            _, pure_text_content, _ = self.process_mentions_and_check_bot(message_content)
                            
                            context = await self.get_group_chat_context(self.app_id, chat_id, context_limit=2)
                            if context:
                                # 将上下文添加到消息前面，使用pure_content作为当前问题
                                context_message = f"群聊上下文:\n{context}\n\n当前问题: {pure_text_content}"
                                message_content_for_ai = [{"type": "text", "text": context_message}]
                                logger.info(f"群聊回复包含上下文，上下文长度: {len(context)}，纯净问题: '{pure_text_content}'")
                            else:
                                # 没有上下文时直接使用pure_content
                                message_content_for_ai = [{"type": "text", "text": pure_text_content}]
                                logger.info(f"群聊回复无上下文，纯净问题: '{pure_text_content}'")
                        
                        await self.generate_streaming_reply(message_content_for_ai, sender_id, receive_id, receive_id_type)
                        logger.info("流式卡片回复已发送")
                        
                        # 调度用户记忆提取任务
                        await self._schedule_memory_extraction(
                            sender_id, message_content_for_ai, chat_id, chat_type, sender_name
                        )
                        
                        return True
                    except Exception as e:
                        logger.error(f"流式卡片回复失败，回退到普通文本回复: {str(e)}")
                        # 继续执行普通文本回复
                        self._get_default_reply(text_content)
            
            # 处理文件消息
            elif message_type == "file":
                try:
                    # 解析文件消息内容
                    file_content = json.loads(content)
                    file_key = file_content.get("file_key")
                    file_name = file_content.get("file_name", "未知文件")
                    
                    logger.info(f"收到文件消息: file_key={file_key}, file_name={file_name}")
                    
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
                        logger.error("无法确定文件消息接收者")
                        return False
                    
                    # 下载文件并处理
                    if file_key:
                        # 下载文件并获取base64数据
                        file_info = await self._download_and_process_file(message_id, file_key, file_name)
                        
                        if file_info.get("success") and file_info.get("file_url"):
                            # 构建多模态消息内容（文件格式）
                            multimodal_content = [
                                {
                                    "type": "file_url",
                                    "name": file_name,
                                    "url": file_info["file_url"]
                                },
                                {
                                    "type": "text", 
                                    "text": "请简述这个文档内容"
                                }
                            ]
                            
                            logger.info(f"构建文件消息: 文件名='{file_name}', file_url={file_info['file_url']}")
                            
                            # 使用流式卡片回复
                            if self.aichat_service:
                                try:
                                    logger.info("使用流式卡片回复文件消息")
                                    await self.generate_streaming_reply(multimodal_content, sender_id, receive_id, receive_id_type)
                                    logger.info("文件消息流式卡片回复已发送")
                                    
                                    # 调度用户记忆提取任务
                                    await self._schedule_memory_extraction(
                                        sender_id, multimodal_content, chat_id, chat_type, sender_name
                                    )
                                    
                                    return True
                                except Exception as e:
                                    logger.error(f"文件消息流式卡片回复失败: {str(e)}")
                                    # 发送简单文本回复
                                    await self.send_text_message(receive_id, f"已收到文件：{file_name}，但处理失败", receive_id_type)
                            else:
                                # 没有AI服务时的默认回复
                                await self.send_text_message(receive_id, f"已收到文件：{file_name}", receive_id_type)
                        else:
                            # 文件下载失败
                            error_msg = file_info.get("error", "文件处理失败")
                            logger.error(f"文件处理失败: {error_msg}")
                            await self.send_text_message(receive_id, f"❌ 文件处理失败：{error_msg}", receive_id_type)
                    
                except Exception as e:
                    logger.error(f"处理文件消息失败: {str(e)}")
                    import traceback
                    logger.error(f"错误详情: {traceback.format_exc()}")
            
            # 处理富文本消息（图片+文字）
            elif message_type == "post":
                try:
                    post_content = json.loads(content)
                    logger.info(f"收到富文本消息: {post_content}")
                    
                    # 解析富文本内容，提取文字和图片
                    parsed_content = await self._parse_post_content(post_content, message_id)
                    text_parts = parsed_content.get("text_parts", [])
                    image_parts = parsed_content.get("image_parts", [])
                    
                    # 组合文字内容
                    combined_text = " ".join(text_parts) if text_parts else ""
                    if not combined_text:
                        combined_text = "这是什么？"  # 默认问题
                    
                    # 构建多模态消息内容
                    multimodal_content = []
                    
                    # 添加图片（如果有）
                    for img_info in image_parts:
                        if img_info.get("success") and img_info.get("base64_data"):
                            mime_type = img_info.get("mime_type", "image/jpeg")
                            multimodal_content.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{img_info['base64_data']}"
                                }
                            })
                    
                    # 添加文字内容
                    multimodal_content.append({
                        "type": "text", 
                        "text": combined_text
                    })
                    
                    logger.info(f"构建多模态消息: 文字='{combined_text}', 图片数量={len([c for c in multimodal_content if c['type'] == 'image_url'])}")
                    
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
                        logger.error("无法确定富文本消息接收者")
                        return False
                    
                    # 使用流式卡片回复
                    if self.aichat_service:
                        try:
                            logger.info("使用流式卡片回复富文本消息")
                            await self.generate_streaming_reply(multimodal_content, sender_id, receive_id, receive_id_type)
                            logger.info("富文本消息流式卡片回复已发送")
                            
                            # 调度用户记忆提取任务
                            await self._schedule_memory_extraction(
                                sender_id, multimodal_content, chat_id, chat_type, sender_name
                            )
                            
                            return True
                        except Exception as e:
                            logger.error(f"富文本消息流式卡片回复失败: {str(e)}")
                            # 发送简单文本回复
                            await self.send_text_message(receive_id, self._get_default_reply(combined_text), receive_id_type)
                    
                except Exception as e:
                    logger.error(f"处理富文本消息失败: {str(e)}")
                    import traceback
                    logger.error(f"错误详情: {traceback.format_exc()}")
            
            return True
            
        except Exception as e:
            logger.error(f"处理消息失败: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            return False
    
    async def _schedule_memory_extraction(
        self, 
        user_id: str, 
        message_content: List[Dict[str, Any]],
        chat_id: Optional[str] = None,
        chat_type: Optional[str] = None,
        nickname: Optional[str] = None
    ):
        """调度用户记忆提取任务
        
        Args:
            user_id: 用户ID
            message_content: 消息内容
            chat_id: 聊天ID（可选）
        """
        try:
            # 检查是否启用用户记忆功能
            memory_enabled = getattr(self.app_config, 'user_memory_enable', True) if self.app_config else True
            
            if not memory_enabled:
                logger.debug("用户记忆功能未启用，跳过记忆提取")
                return
            
            # 将消息内容转换为适合记忆提取的格式
            messages_for_memory = []
            
            for item in message_content:
                if item.get("type") == "text":
                    messages_for_memory.append({
                        "role": "user",
                        "content": item.get("text", "")
                    })
                elif item.get("type") == "file_url":
                    file_name = item.get("name", "未知文件")
                    messages_for_memory.append({
                        "role": "user", 
                        "content": f"用户上传了文件：{file_name}"
                    })
                elif item.get("type") == "image_url":
                    messages_for_memory.append({
                        "role": "user",
                        "content": "用户发送了图片"
                    })
            
            if messages_for_memory:
                # 调度记忆提取任务
                await self.user_memory_service.schedule_memory_extraction(
                    self.app_id, user_id, messages_for_memory, chat_id, chat_type, nickname
                )
                logger.info(f"已为用户 {user_id}@{self.app_id} 调度记忆提取任务")
            else:
                logger.debug("没有可用于记忆提取的消息内容")
                
        except Exception as e:
            logger.error(f"调度记忆提取任务失败: {e}")
    
    async def get_collection_download_url(self, collection_id: str) -> Optional[str]:
        """获取collection的下载链接"""
        try:
            # 获取配置
            read_collection_url = getattr(self.app_config, 'aichat_read_collection_url', None)
            read_collection_key = getattr(self.app_config, 'aichat_read_collection_key', None)
            client_download_host = getattr(self.app_config, 'aichat_client_download_host', None)

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
                            # 拼接完整的下载链接
                            download_url = client_download_host.rstrip('/') + file_value
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
                        open_id = user_data.get("open_id", "")

                        # 处理姓名显示格式
                        display_name_mode = getattr(self.app_config, 'user_display_name_mode', 'name_with_en_name')
                        if display_name_mode == "name_only":
                            # 模式1：只用 name（不管是否为空）
                            display_name = name
                        else:
                            # 模式2：当前逻辑（先查 name and en_name，然后 en_name and not name）
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
                            "open_id": open_id,
                            "success": True
                        }
                    else:
                        logger.error(f"获取用户信息失败: {result}")
                        return {
                            "mobile": "",
                            "name": "用户",
                            "user_id": user_id,
                            "open_id": "",
                            "success": False
                        }
                        
        except Exception as e:
            logger.error(f"获取用户信息异常: {str(e)}")
            return {
                "mobile": "",
                "name": "用户",
                "user_id": user_id,
                "open_id": "",
                "success": False
            }

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """获取群聊详细信息
        
        Args:
            chat_id: 群聊ID
            
        Returns:
            Dict[str, Any]: 群聊信息
        """
        try:
            token = await self.get_tenant_access_token()
            url = f"{self.base_url}/open-apis/im/v1/chats/{chat_id}?user_id_type=open_id"
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            # 使用临时的客户端会话避免事件循环冲突
            async with aiohttp.ClientSession() as client:
                async with client.get(url, headers=headers) as response:
                    result = await response.json()
                    
                    if result.get("code") == 0:
                        chat_data = result.get("data", {})
                        
                        # 提取需要的字段
                        avatar = chat_data.get("avatar", "")
                        name = chat_data.get("name", "")
                        description = chat_data.get("description", "")
                        chat_mode = chat_data.get("chat_mode", "")
                        chat_type = chat_data.get("chat_type", "")
                        
                        logger.info(f"获取群聊信息成功: {name} ({chat_id})")
                        
                        return {
                            "chat_id": chat_id,
                            "name": name or "未命名群聊",
                            "description": description,
                            "avatar": avatar,
                            "chat_mode": chat_mode,
                            "chat_type": chat_type,
                            "success": True
                        }
                    else:
                        logger.error(f"获取群聊信息失败: {result}")
                        return {
                            "chat_id": chat_id,
                            "name": "未知群聊",
                            "description": "",
                            "avatar": "",
                            "chat_mode": "",
                            "chat_type": "",
                            "success": False
                        }
                        
        except Exception as e:
            logger.error(f"获取群聊信息异常: {str(e)}")
            return {
                "chat_id": chat_id,
                "name": "未知群聊",
                "description": "",
                "avatar": "",
                "chat_mode": "",
                "chat_type": "",
                "success": False
            }

    async def generate_streaming_reply(self, user_message: List[Dict[str, Any]], user_id: str, receive_id: str, 
                                     receive_id_type: str = "user_id") -> str:
        """生成流式回复内容（使用卡片流式更新）"""
        try:
            # 获取用户详细信息
            user_info = await self.get_user_info(user_id)
            
            # 构建包含app_name的chat_id
            app_name = getattr(self.app_config, 'app_name', 'default') if self.app_config else 'default'
            
            # 提取用户消息文本用于卡片显示
            display_message = ""
            for item in user_message:
                if item.get("type") == "text":
                    display_message = item.get("text", "")
                    break
                elif item.get("type") == "file_url":
                    file_name = item.get("name", "未知文件")
                    display_message = f"[文件: {file_name}]"
                elif item.get("type") == "image_url":
                    display_message = f"[图片]"

            logger.info(f"使用AI Chat流式服务生成回复: user_id {user_id}, {display_message}...")
            
            # 检查是否启用用户记忆功能
            memory_enabled = getattr(self.app_config, 'user_memory_enable', True) if self.app_config else True
            user_context = ""
            
            if memory_enabled:
                try:
                    # 获取用户画像和记忆
                    logger.info(f"为用户 {user_id} 加载记忆上下文...")
                    profile = await self.user_memory_service.get_user_profile(self.app_id, user_id)
                    
                    # 搜索相关记忆（基于用户当前问题）
                    if display_message:
                        memories = await self.user_memory_service.search_memories(self.app_id, user_id, display_message, limit=5)
                        logger.info(f"搜索记忆成功: {memories}")
                    else:
                        memories = await self.user_memory_service.get_user_memories(self.app_id, user_id, limit=5)
                        logger.info(f"获取记忆成功: {memories}")
                    
                    # 格式化用户上下文
                    user_context = self.user_memory_service.format_user_context(profile, memories)
                    
                    if user_context:
                        logger.info(f"已加载用户 {user_id} 的记忆上下文，长度: {len(user_context)}")
                    else:
                        logger.info(f"用户 {user_id} 暂无记忆上下文")
                        
                except Exception as e:
                    logger.error(f"加载用户记忆失败: {e}")
                    user_context = ""
            else:
                logger.info("用户记忆功能未启用")
            
            # 初始化当前卡片内容状态
            current_card_state = {
                "user_message": display_message,
                "sender_name": user_info["name"],  # 使用用户真实姓名
                "status": "🔄 **正在准备**...",
                "think_title": "💭 **准备思考中...**",
                "think_content": "",
                "think_finished": False,
                "answer_content": "",
                "references_title": "📚 **知识引用** (0)",
                "references_content": "",
                "bot_summary": "AI正在思考中...",  # 机器人问答状态
                "image_cache": {},  # 添加图片缓存：{原始URL: 飞书img_key}
                "processing_images": set(),  # 添加正在处理的图片URL集合
                "citation_cache": {},  # 添加引用缓存：{quote_id: 引用链接}
                "processing_citations": set()  # 添加正在处理的引用ID集合
            }

            # 预先生成本次会话的 chat item id，并用于引用预览
            response_chat_item_id = str(uuid.uuid4())
            
            # 1. 创建流式卡片（不包含停止按钮）
            card_content = self._build_card_content(current_card_state)
            card_result = await self._create_card_entity(card_content)
            
            if card_result.get("code") != 0:
                logger.error(f"创建流式卡片失败: {card_result}")
                return
            
            card_id = card_result.get("data", {}).get("card_id")
            if not card_id:
                logger.error("创建流式卡片成功但未获取到card_id")
                return
            
            # 将card_id添加到状态中，用于生成停止按钮
            current_card_state["card_id"] = card_id
            
            # 初始化停止标志
            self._class_stop_flags[card_id] = False
            
            # 2. 立即更新卡片内容，添加包含真实card_id的停止按钮
            updated_card_content = self._build_card_content(current_card_state)
            await self._update_card_settings(
                card_id, updated_card_content, 1,
                current_card_state["image_cache"], current_card_state["processing_images"],
                current_card_state["citation_cache"], current_card_state["processing_citations"]
            )
            
            # 3. 发送卡片消息（现在包含真实的card_id）
            send_result = await self._send_card_message_by_id(receive_id, card_id, receive_id_type)
            if send_result.get("code") != 0:
                logger.error(f"发送流式卡片消息失败: {send_result}")
                return
            
            logger.info(f"流式卡片已发送: card_id={card_id}")
            
            # 4. 流式更新卡片内容
            sequence_counter = 2  # 从2开始，因为1已经用于更新按钮
            sequence_lock = asyncio.Lock()  # 序列号锁，确保并发安全
            think_title_updated = False  # 思考标题更新标志
            answer_title_updated = False  # 答案标题更新标志
            
            async def on_status_callback(status_text: str):
                nonlocal sequence_counter, current_card_state
                
                # 检查停止标志
                if self._class_stop_flags.get(card_id, False):
                    logger.info(f"检测到停止标志，跳过状态更新: {status_text}")
                    return
                
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

                # 检查停止标志
                if self._class_stop_flags.get(card_id, False):
                    logger.info(f"检测到停止标志，跳过思考更新: 长度={len(think_text)}")
                    return

                # 处理文本中的图片链接和知识块引用（使用缓存避免重复处理）
                try:
                    # 先处理图片链接
                    processed_think_text = await self._process_images_in_text_with_cache(
                        think_text, current_card_state["image_cache"], current_card_state["processing_images"]
                    )
                    
                    # 再处理知识块引用
                    processed_think_text = await self._process_citations_in_text_with_cache(
                        processed_think_text, current_card_state["citation_cache"], current_card_state["processing_citations"],
                        current_chat_id, response_chat_item_id
                    )
                    
                    # 使用处理后的文本
                    think_text = processed_think_text
                    
                except Exception as e:
                    logger.error(f"处理思考文本中的图片和引用失败: {str(e)}")
                    # 处理失败时继续使用原文本

                async with sequence_lock:
                    # 首次有思考内容时，设置思考标题和思考内容
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
                        update_result = await self._update_card_settings(
                            card_id, complete_card_content, think_sequence,
                            current_card_state["image_cache"], current_card_state["processing_images"],
                            current_card_state["citation_cache"], current_card_state["processing_citations"]
                        )
                        
                        if update_result.get("code") == 0:
                            logger.info(f"全量更新思考面板标题成功: {think_title}")
                        else:
                            logger.error(f"全量更新思考面板标题失败: {update_result}")
                            think_title_updated = False  # 失败时重置标志位
                    else:
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
                
                # 检查停止标志
                if self._class_stop_flags.get(card_id, False):
                    logger.info(f"检测到停止标志，跳过答案更新: 长度={len(answer_text)}")
                    return
                
                # 处理文本中的markdown表格分隔符、图片链接和知识块引用（使用缓存避免重复处理）
                try:
                    # 先处理markdown表格分隔符（飞书显示适配）
                    processed_answer_text = self._process_markdown_table_separators(answer_text)
                    
                    # 再处理图片链接
                    processed_answer_text = await self._process_images_in_text_with_cache(
                        processed_answer_text, current_card_state["image_cache"], current_card_state["processing_images"]
                    )
                    
                    # 最后处理知识块引用
                    processed_answer_text = await self._process_citations_in_text_with_cache(
                        processed_answer_text, current_card_state["citation_cache"], current_card_state["processing_citations"],
                        current_chat_id, response_chat_item_id
                    )
                    
                    # 使用处理后的文本
                    answer_text = processed_answer_text
                    
                except Exception as e:
                    logger.error(f"处理答案文本中的markdown、图片和引用失败: {str(e)}")
                    # 处理失败时继续使用原文本
                
                # 构建答案内容
                answer_content = f"💡**回答**\n\n{answer_text}"
                think_title = "💭 **已完成思考**"
                current_card_state["answer_content"] = answer_content
                current_card_state["think_title"] = think_title
                current_card_state["think_finished"] = True
                
                async with sequence_lock:
                    # 首次更新答案时，更新思考面板标题和答案内容
                    if not answer_title_updated and answer_text:
                        answer_sequence = sequence_counter
                        sequence_counter += 1
                        answer_title_updated = True  # 立即设置标志位
                        
                        # 构建完整的卡片内容
                        complete_card_content = self._build_card_content(current_card_state)
                        
                        # 使用新的API进行全量更新
                        logger.info(f"准备进行引用内容全量更新: 答案部分")
                        update_result = await self._update_card_settings(
                            card_id, complete_card_content, answer_sequence,
                            current_card_state["image_cache"], current_card_state["processing_images"],
                            current_card_state["citation_cache"], current_card_state["processing_citations"]
                        )
                        
                        if update_result.get("code") == 0:
                            logger.info(f"全量更新答案面板标题成功: {think_title}")
                        else:
                            logger.error(f"全量更新答案面板标题失败: {update_result}")
                            answer_title_updated = False  # 失败时重置标志位
                    else:
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
                            # 再次尝试构建完整的卡片内容
                            complete_card_content = self._build_card_content(current_card_state)
                            
                            # 使用新的API进行全量更新
                            logger.info(f"再次尝试准备进行引用内容全量更新: 答案部分")
                            update_result = await self._update_card_settings(
                                card_id, complete_card_content, answer_sequence,
                                current_card_state["image_cache"], current_card_state["processing_images"],
                                current_card_state["citation_cache"], current_card_state["processing_citations"]
                            )
                            
                            if update_result.get("code") == 0:
                                logger.info(f"再次尝试全量更新答案面板标题成功: {think_title}")
                            else:
                                logger.error(f"再次尝试全量更新答案面板标题失败: {update_result}")
            
            async def on_references_callback(references_data: list):
                """处理引用数据回调"""
                nonlocal sequence_counter, current_card_state
                
                # 检查停止标志
                if self._class_stop_flags.get(card_id, False):
                    logger.info(f"检测到停止标志，跳过引用更新: {len(references_data) if references_data else 0} 条引用")
                    return
                
                try:
                    if references_data:
                        logger.info(f"收到 {len(references_data)} 条引用数据")
                        
                        # 更新卡片状态中的引用信息
                        current_card_state["references_title"] = f"📚 **知识引用** ({len(references_data)})"
                        current_card_state["references_content"] = await self._get_references_content(references_data)
                    else:
                        logger.debug("引用数据为空，跳过更新")
                except Exception as e:
                    logger.error(f"处理引用数据异常: {str(e)}")
            
            # 获取用户当前的聊天会话ID
            try:
                from app.services.user_chat_session_service import UserChatSessionService
                session_service = UserChatSessionService()
                # 从user_info中提取open_id
                open_id = user_info.get("open_id", "")
                current_chat_id = session_service.get_current_chat_id(
                    app_id=self.app_id,
                    user_id=user_id,
                    app_name=app_name,
                    open_id=open_id
                )
                logger.info(f"使用聊天会话ID: {current_chat_id}")
            except Exception as e:
                # 如果获取失败，使用传统的拼接方式作为fallback
                logger.warning(f"获取聊天会话ID失败，使用fallback: {str(e)}")
                current_chat_id = f"feishu_{app_name}_user_{user_id}"
            
            # 获取用户的搜索偏好和模型偏好
            dataset_search = True  # 默认值
            web_search = False     # 默认值
            model_id = None        # 默认值
            try:
                from app.services.user_search_preference_service import UserSearchPreferenceService
                preference_service = UserSearchPreferenceService()
                dataset_search, web_search, model_id = preference_service.get_search_preference(
                    app_id=self.app_id,
                    user_id=user_id
                )
                logger.info(f"用户搜索偏好: dataset={dataset_search}, web={web_search}")
                if model_id:
                    logger.info(f"用户模型偏好: model_id={model_id}")
                else:
                    logger.info(f"用户未设置模型偏好，使用默认模型")
            except Exception as e:
                logger.warning(f"获取用户偏好失败，使用默认值: {str(e)}")
            
            # 创建停止检查函数
            def should_stop():
                return self._class_stop_flags.get(card_id, False)
            
            # 构建AI服务的variables，包含用户记忆上下文
            variables = {
                "feishu_user_id": user_info["user_id"],
                "feishu_mobile": user_info["mobile"],
                "feishu_name": user_info["name"],
                "dataset": dataset_search,
                "web": web_search,
                "user_memory_context": ""
            }
            
            # 如果用户设置了模型偏好，添加到variables中
            if model_id:
                variables["model_id"] = model_id
            
            # 如果有用户记忆上下文，添加到variables中
            if user_context and user_context.strip() != "":
                variables["user_memory_context"] = "当前用户画像和重要记忆如下：\n```" + user_context + "```"
                logger.info("已将用户记忆上下文添加到AI请求中")
            
            # 检查是否配置了 aichat_app_id，决定是否保留数据集引用
            has_aichat_app_id = bool(getattr(self.app_config, 'aichat_app_id', ''))
            
            # 调用AI Chat详细流式接口（使用新的回调结构）
            ai_answer = await self.aichat_service.chat_completion_streaming(
                chat_id=current_chat_id,
                message=user_message,
                variables=variables,
                on_status_callback=on_status_callback,
                on_think_callback=on_think_callback,
                on_answer_callback=on_answer_callback,
                on_references_callback=on_references_callback,
                should_stop_callback=should_stop,
                retain_dataset_cite=has_aichat_app_id,
                response_chat_item_id=response_chat_item_id
            )
            
            # 检查是否被用户停止
            was_stopped = self._class_stop_flags.get(card_id, False)
            
            if ai_answer:
                if was_stopped:
                    logger.info(f"AI流式回复被用户停止，部分答案长度: {len(ai_answer)}")
                    current_card_state["status"] = "❌ 答案已停止生成"
                    current_card_state["bot_summary"] = "❌回答已停止"
                else:
                    logger.info(f"AI流式回复成功，答案长度: {len(ai_answer)}")
                    current_card_state["bot_summary"] = "💡回答：" + ai_answer
                
                # 如果已有答案内容，保持现有内容；否则设置最终答案
                if not current_card_state.get("answer_content"):
                    current_card_state["answer_content"] = "💡**回答**\n\n" + ai_answer
            else:
                if was_stopped:
                    logger.info("AI流式回复被用户停止，无内容生成")
                    current_card_state["status"] = "❌ 答案已停止生成"
                    current_card_state["bot_summary"] = "❌回答已停止"
                    if not current_card_state.get("answer_content"):
                        current_card_state["answer_content"] = "❌ **回答已停止**\n\n用户已取消本次回答。"
                else:
                    logger.warning("AI流式回复为空")
                    current_card_state["answer_content"] = "抱歉，我暂时无法理解您的问题，请换个方式提问。"
                    current_card_state["bot_summary"] = "回答失败"

            # 最终更新卡片内容（完成状态，移除停止按钮）
            complete_card_content = self._build_card_content(current_card_state, finished=True)
            await self._update_card_settings(
                card_id, complete_card_content, sequence_counter,
                current_card_state["image_cache"], current_card_state["processing_images"],
                current_card_state["citation_cache"], current_card_state["processing_citations"]
            )
            
            # 清理停止标志
            if card_id in self._class_stop_flags:
                del self._class_stop_flags[card_id]
            
            return ai_answer
            
        except Exception as e:
            logger.error(f"生成流式回复异常: {str(e)}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            
            # 清理停止标志
            if 'card_id' in locals() and card_id in self._class_stop_flags:
                del self._class_stop_flags[card_id]
            
            # 出现异常时返回默认回复
            return self._get_default_reply(user_message)

    def stop_streaming_reply(self, card_id: str) -> bool:
        """停止指定卡片的流式回复
        
        Args:
            card_id: 卡片ID
            
        Returns:
            bool: 是否成功设置停止标志
        """
        self._class_stop_flags[card_id] = True
        logger.info(f"已设置停止标志: {card_id}")
        return True

    def _build_card_content(self, card_state: Dict[str, str] = None, finished: bool = False) -> Dict[str, Any]:
        """构建卡片内容（统一方法）
        
        Args:
            card_state: 当前卡片状态字典（用于更新时）
            sender_name: 发送者名称（用于创建时）
            
        Returns:
            Dict[str, Any]: 完整的卡片内容
        """
        
        # 获取应用名称，如果没有配置则使用默认值
        app_name = "🤖 AI助手"
        if self.app_config and hasattr(self.app_config, 'app_name'):
            app_name = f"🔍 {self.app_config.app_name}"
        
        # 构建基础卡片结构
        card = {
            "schema": "2.0",
            "header": {
                "title": {
                    "content": app_name,
                    "tag": "plain_text"
                }
            },
            "config": {
                "streaming_mode": not finished,
                "update_multi": True,
                "summary": {
                    "content": card_state.get("bot_summary", "AI正在思考中...")
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
                },
                "enable_forward": True,
                "width_mode": "fill"
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
                "expanded": not card_state.get("think_finished", False),
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
        
        # 6. 停止回答按钮（只在流式回复过程中显示，且应用支持停止流式回答）
        if not finished:
            # 检查应用是否支持停止流式回答
            support_stop_streaming = False
            if self.app_config and hasattr(self.app_config, 'aichat_support_stop_streaming'):
                support_stop_streaming = getattr(self.app_config, 'aichat_support_stop_streaming', False)
            
            if support_stop_streaming:
                # 获取卡片ID用于生成唯一的action_id
                card_id = card_state.get("card_id", "unknown")
                
                elements.append({"tag": "hr"})
                elements.append({
                    "tag": "button",
                    "element_id": "stop_button",
                    "text": {
                        "tag": "plain_text",
                        "content": "❌ 停止回答"
                    },
                    "type": "danger",
                    "size": "small", 
                    "width": "default",
                    "margin": "8px 0 0 0",  # 上边距
                    "behaviors": [
                        {
                            "type": "callback",
                            "value": {
                                "action": "stop_streaming",
                                "card_id": card_id
                            }
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
                
                # 如果有collection_id，判断是否为链接或需要获取下载链接
                if collection_id:
                    # 检查是否为HTTP/HTTPS链接（博查联网检索等）
                    if collection_id.startswith(('http://', 'https://')):
                        # 直接使用链接，跳转到源站
                        ref_content += f"\n\n🔗 <link url=\"{collection_id}\">点击跳转源站</link>"
                    else:
                        # 传统的collection_id，尝试获取下载链接
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
    
    async def _process_audio_transcription(self, audio_file_path: str, sender_id: str, receive_id: str, receive_id_type: str):
        """处理音频转录并回复用户
        
        Args:
            audio_file_path: 音频文件路径
            sender_id: 发送者ID
            receive_id: 接收者ID
            receive_id_type: 接收者类型
        """
        try:
            logger.info(f"开始处理音频转录: {audio_file_path}")
            
            # 使用ASR服务进行转录
            transcription_result = await self.asr_service.transcribe_audio_file(audio_file_path)
            
            if transcription_result["success"]:
                transcribed_text = transcription_result["text"]
                logger.info(f"语音转录成功: {transcribed_text}")
                
                # 如果有AI Chat服务，也可以进一步处理转录文本
                if self.aichat_service:
                    try:
                        await self.generate_streaming_reply([{"type": "text", "text": transcribed_text}], sender_id, receive_id, receive_id_type)
                        logger.info("基于转录文本的AI回复已发送")
                    except Exception as e:
                        logger.warning(f"AI处理转录文本失败: {str(e)}")
                
            else:
                error_msg = transcription_result["error"]
                logger.error(f"语音转录失败: {error_msg}")
                
                # 发送错误回复
                reply_text = "❌ 抱歉，语音转录失败，可能是音频质量问题或网络错误。"
                await self.send_text_message(receive_id, reply_text, receive_id_type)
                
        except Exception as e:
            logger.error(f"处理音频转录异常: {str(e)}")
            try:
                # 发送异常回复
                reply_text = "❌ 语音处理出现异常，请稍后重试。"
                await self.send_text_message(receive_id, reply_text, receive_id_type)
            except:
                pass  # 避免回复失败导致的二次异常

    async def _parse_post_content(self, post_content: Dict[str, Any], message_id: str) -> Dict[str, Any]:
        """解析富文本消息内容，提取文字和图片
        
        Args:
            post_content: 富文本消息内容
            message_id: 消息ID，用于下载图片
            
        Returns:
            Dict包含text_parts和image_parts
        """
        try:
            text_parts = []
            image_parts = []
            
            # 获取内容数组
            content_array = post_content.get("content", [])
            
            for paragraph in content_array:
                if isinstance(paragraph, list):
                    for element in paragraph:
                        if isinstance(element, dict):
                            tag = element.get("tag", "")
                            
                            if tag == "text":
                                # 提取文字内容
                                text = element.get("text", "")
                                if text.strip():
                                    text_parts.append(text.strip())
                                    
                            elif tag == "img":
                                # 提取图片信息
                                image_key = element.get("image_key", "")
                                width = element.get("width", 0)
                                height = element.get("height", 0)
                                
                                if image_key:
                                    logger.info(f"发现图片: image_key={image_key}, 尺寸={width}x{height}")
                                    
                                    # 下载图片并获取描述
                                    image_info = await self._download_and_analyze_image(message_id, image_key)
                                    image_info.update({
                                        "image_key": image_key,
                                        "width": width,
                                        "height": height
                                    })
                                    image_parts.append(image_info)
            
            logger.info(f"解析富文本完成: 文字段落={len(text_parts)}, 图片={len(image_parts)}")
            
            return {
                "text_parts": text_parts,
                "image_parts": image_parts
            }
            
        except Exception as e:
            logger.error(f"解析富文本内容异常: {str(e)}")
            return {
                "text_parts": [],
                "image_parts": []
            }

    async def _download_and_analyze_image(self, message_id: str, image_key: str) -> Dict[str, Any]:
        """下载图片并转换为base64
        
        Args:
            message_id: 消息ID
            image_key: 图片key
            
        Returns:
            Dict包含图片信息和base64数据
        """
        try:
            # 获取tenant_access_token
            token = await self.get_tenant_access_token()
            
            # 构建下载URL
            url = f"{self.base_url}/open-apis/im/v1/messages/{message_id}/resources/{image_key}?type=file"
            headers = {
                "Authorization": f"Bearer {token}"
            }
            
            logger.info(f"准备下载图片: {url}")
            
            # 下载图片
            async with aiohttp.ClientSession() as client:
                async with client.get(url, headers=headers) as response:
                    if response.status == 200:
                        content = await response.read()
                        logger.info(f"下载图片成功，大小: {len(content)} bytes")
                        
                        # 检测图片格式
                        if content.startswith(b'\xff\xd8\xff'):
                            mime_type = 'image/jpeg'
                        elif content.startswith(b'\x89PNG'):
                            mime_type = 'image/png'
                        elif content.startswith(b'GIF'):
                            mime_type = 'image/gif'
                        elif content.startswith(b'RIFF') and b'WEBP' in content[:12]:
                            mime_type = 'image/webp'
                        else:
                            mime_type = 'image/jpeg'  # 默认格式
                        
                        # 转换为base64
                        import base64
                        base64_data = base64.b64encode(content).decode('utf-8')
                        logger.info(f"图片转换为base64成功，格式: {mime_type}, 长度: {len(base64_data)}")
                        
                        return {
                            "file_size": len(content),
                            "base64_data": base64_data,
                            "mime_type": mime_type,
                            "success": True
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"下载图片失败: {response.status}, 错误信息: {error_text}")
                        return {
                            "description": "图片下载失败",
                            "success": False
                        }
                        
        except Exception as e:
            logger.error(f"下载和分析图片异常: {str(e)}")
            return {
                "description": "图片处理异常",
                "success": False
            }

    async def _update_card_settings(self, card_id: str, card_content: Dict[str, Any], sequence: int = 1, 
                                  image_cache: dict = None, processing_images: set = None,
                                  citation_cache: dict = None, processing_citations: set = None) -> dict:
        """使用新的API全量更新卡片设置和内容
        
        Args:
            card_id: 卡片实体ID
            card_content: 完整的卡片内容
            sequence: 序列号，用于控制更新顺序
            image_cache: 图片缓存字典
            processing_images: 正在处理的图片URL集合
            citation_cache: 引用缓存字典
            processing_citations: 正在处理的引用ID集合
            
        Returns:
            dict: 更新结果
        """
        try:
            # 如果提供了图片缓存，则处理卡片内容中的图片
            if image_cache is not None and processing_images is not None:
                card_content = await self._process_card_content_images(card_content, image_cache, processing_images)
            
            # 如果提供了引用缓存，则处理卡片内容中的引用
            if citation_cache is not None and processing_citations is not None:
                card_content = await self._process_card_content_citations(card_content, citation_cache, processing_citations)
            
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
            # 检查是否为本地图床URL，如果是则直接从文件系统读取
            if self.app_config:
                image_bed_base_url = getattr(self.app_config, 'image_bed_base_url', None)
                
                if image_bed_base_url and image_url.startswith(image_bed_base_url):
                    # 这是本地图床的图片，直接从静态文件目录读取
                    try:
                        # 从URL中提取相对路径：/static/images/filename.ext
                        # 例如：http://domain.com/static/images/abc.png -> /static/images/abc.png
                        url_path = image_url.replace(image_bed_base_url.rstrip('/'), '', 1)
                        
                        if url_path.startswith('/static/images/'):
                            # 提取图片文件名
                            match = re.search(r'/static/images/([^/?]+)', url_path)
                            if match:
                                filename = match.group(1)
                                static_image_path = os.path.join("static", "images", filename)
                                
                                if os.path.exists(static_image_path):
                                    # 创建临时文件复制
                                    suffix = os.path.splitext(filename)[-1] or '.jpg'
                                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                                    temp_path = temp_file.name
                                    temp_file.close()
                                    
                                    # 直接复制文件
                                    shutil.copy2(static_image_path, temp_path)
                                    
                                    logger.info(f"本地图片直接复制: {static_image_path} -> {temp_path}")
                                    return temp_path
                                else:
                                    logger.warning(f"本地图片文件不存在: {static_image_path}")
                                    # 继续使用HTTP下载作为回退
                    except Exception as e:
                        logger.warning(f"本地图片处理失败，回退到HTTP下载: {str(e)}")
                        # 继续使用HTTP下载作为回退
            
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

    async def _process_card_content_images(self, card_content: Dict[str, Any], image_cache: dict, processing_images: set) -> Dict[str, Any]:
        """处理卡片内容中的图片链接
        
        Args:
            card_content: 卡片内容字典
            image_cache: 图片缓存字典
            processing_images: 正在处理的图片URL集合
            
        Returns:
            Dict[str, Any]: 处理后的卡片内容
        """
        try:
            # 深拷贝卡片内容，避免修改原始数据
            import copy
            processed_content = copy.deepcopy(card_content)
            
            # 递归处理卡片内容中的所有文本字段
            await self._process_card_element_images(processed_content, image_cache, processing_images)
            
            return processed_content
            
        except Exception as e:
            logger.error(f"处理卡片内容图片异常: {str(e)}")
            return card_content  # 出错时返回原内容

    async def _process_card_element_images(self, element: Any, image_cache: dict, processing_images: set):
        """递归处理卡片元素中的图片链接
        
        Args:
            element: 卡片元素（可能是字典、列表或字符串）
            image_cache: 图片缓存字典
            processing_images: 正在处理的图片URL集合
        """
        try:
            if isinstance(element, dict):
                for key, value in element.items():
                    if key == "content" and isinstance(value, str):
                        # 处理content字段中的图片
                        element[key] = await self._process_images_in_text_with_cache(value, image_cache, processing_images)
                    else:
                        # 递归处理其他字段
                        await self._process_card_element_images(value, image_cache, processing_images)
            elif isinstance(element, list):
                for item in element:
                    await self._process_card_element_images(item, image_cache, processing_images)
            # 字符串和其他类型不需要处理
            
        except Exception as e:
            logger.error(f"处理卡片元素图片异常: {str(e)}")

    async def _process_card_content_citations(self, card_content: Dict[str, Any], citation_cache: dict, processing_citations: set) -> Dict[str, Any]:
        """处理卡片内容中的知识块引用
        
        Args:
            card_content: 卡片内容字典
            citation_cache: 引用缓存字典
            processing_citations: 正在处理的引用ID集合
            
        Returns:
            Dict[str, Any]: 处理后的卡片内容
        """
        try:
            # 深拷贝卡片内容，避免修改原始数据
            import copy
            processed_content = copy.deepcopy(card_content)
            
            # 递归处理卡片内容中的所有文本字段
            await self._process_card_element_citations(processed_content, citation_cache, processing_citations)
            
            return processed_content
            
        except Exception as e:
            logger.error(f"处理卡片内容引用异常: {str(e)}")
            return card_content  # 出错时返回原内容

    async def _process_card_element_citations(self, element: Any, citation_cache: dict, processing_citations: set):
        """递归处理卡片元素中的知识块引用
        
        Args:
            element: 卡片元素（可能是字典、列表或字符串）
            citation_cache: 引用缓存字典
            processing_citations: 正在处理的引用ID集合
        """
        try:
            if isinstance(element, dict):
                for key, value in element.items():
                    if key == "content" and isinstance(value, str):
                        # 处理content字段中的引用（但不需要chat_id，因为这是卡片更新，已经在流式过程中处理过了）
                        element[key] = await self._process_citations_in_card_content(value, citation_cache)
                    else:
                        # 递归处理其他字段
                        await self._process_card_element_citations(value, citation_cache, processing_citations)
            elif isinstance(element, list):
                for item in element:
                    await self._process_card_element_citations(item, citation_cache, processing_citations)
            # 字符串和其他类型不需要处理
            
        except Exception as e:
            logger.error(f"处理卡片元素引用异常: {str(e)}")

    async def _process_citations_in_card_content(self, text: str, citation_cache: dict) -> str:
        """处理卡片内容中的知识块引用（简化版，只使用缓存）
        
        Args:
            text: 包含知识块引用的文本
            citation_cache: 引用缓存字典
            
        Returns:
            str: 处理后的文本
        """
        try:
            # 匹配知识块引用格式：[quote_id](CITE)
            citation_pattern = r'\[([a-f0-9]{24})\]\(CITE\)'
            
            def replace_citation(match):
                quote_id = match.group(1)
                if quote_id in citation_cache:
                    preview_url = citation_cache[quote_id]
                    return f"[📌]({preview_url})"
                else:
                    # 如果缓存中没有，返回普通文本
                    return "📌"
            
            processed_text = re.sub(citation_pattern, replace_citation, text)
            return processed_text
            
        except Exception as e:
            logger.error(f"处理卡片引用异常: {str(e)}")
            return text

    def _process_markdown_table_separators(self, content: str) -> str:
        """处理并替换markdown表格分隔符
        
        1. 将空表格（只有标题行的表格）转换为引用格式
        2. 将形如 "| :----: |\n\n---" 的模式替换为简单的 "---"
        3. 处理单独的 "| :----: |" 模式
        
        这种处理专门针对飞书卡片显示，因为飞书不会展示 | :----: | 分隔符
        
        Args:
            content: 需要处理的文本内容
            
        Returns:
            str: 处理后的文本内容
        """
        # 优先处理空表格：| 标题内容 |\n| :----: |\n\n（可选地跟着---分隔线）
        # 这种表格只有标题行，没有数据行，转换为引用格式
        empty_table_pattern = r'\|\s*([^|]+?)\s*\|\n\|\s*:----:\s*\|\n\n(?:---\n\n|---\n|---$)?'
        def replace_empty_table(match):
            title_content = match.group(1).strip()
            return f"⚠️ **注意**\n> {title_content}\n\n"
        
        processed_content = re.sub(empty_table_pattern, replace_empty_table, content)
        
        # 处理 | :----: | 后面跟着换行和分隔线的完整模式
        # 需要区分两种情况：前面有换行的和前面没有换行的
        pattern1 = r'\n\|\s*:----:\s*\|\n\n---'
        processed_content = re.sub(pattern1, '\n---', processed_content)
        
        # 处理行首的 | :----: |\n\n--- 模式
        pattern2 = r'^\|\s*:----:\s*\|\n\n---'
        processed_content = re.sub(pattern2, '---', processed_content, flags=re.MULTILINE)
        
        # 处理剩余的单独 | :----: | 行
        pattern3 = r'\|\s*:----:\s*\|\n'
        processed_content = re.sub(pattern3, '\n', processed_content)
        
        # 最后处理任何剩余的 | :----: | 模式
        pattern4 = r'\|\s*:----:\s*\|'
        processed_content = re.sub(pattern4, '', processed_content)
        
        return processed_content

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
                    logger.debug(f"图片正在处理中，暂时显示为空: {cache_key}")
                    # 如果图片正在处理中，暂时设置为空的markdown图片
                    empty_link = f"![{alt_text}]()"
                    replacements.append((full_match, empty_link))
                    continue
                
                # 新图片，需要下载和上传
                logger.info(f"发现新图片链接，开始处理: {image_url}")
                logger.debug(f"缓存中没有找到此URL，当前缓存: {list(image_cache.keys())}")
                
                # 标记为处理中（使用原始URL作为键）
                processing_images.add(cache_key)
                
                try:
                    local_path = await self._download_image(image_url)
                    if not local_path:
                        logger.warning(f"下载图片失败，清空图片链接避免飞书安全错误: {image_url}")
                        # 下载失败时清空图片URL，避免飞书外链安全错误
                        empty_link = f"![{alt_text}]()"
                        replacements.append((full_match, empty_link))
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
                        logger.warning(f"上传图片到飞书失败，清空图片链接避免飞书安全错误: {image_url}")
                        # 上传失败时也清空图片URL，避免飞书外链安全错误
                        empty_link = f"![{alt_text}]()"
                        replacements.append((full_match, empty_link))
                        
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
    
    async def _process_citations_in_text_with_cache(self, text: str, citation_cache: dict, processing_citations: set, chat_id: str, chat_item_data_id: str) -> str:
        """处理文本中的知识块引用，使用缓存避免重复处理
        
        简化后的处理流程：
        1. 识别 [quote_id](CITE) 格式的知识块引用
        2. 直接构建预览URL，将参数（quote_id, app_id, chat_id）传递给前端页面
        3. 将原引用替换为 [📌](预览链接)
        4. 用户点击后，前端页面自己调用FastGPT API获取知识块数据并显示
        
        Args:
            text: 包含知识块引用的文本
            citation_cache: 引用缓存字典，键为quote_id，值为预览链接
            processing_citations: 正在处理的引用ID集合
            chat_id: 聊天ID
            
        Returns:
            str: 处理后的文本，知识块引用已替换为预览链接
        """
        try:
            # 统一处理引用格式，支持多种格式兼容：
            # 1. [quote_id](CITE) - 标准格式
            # 2. 【quote_id】(CITE) - 中文括号格式  
            # 3. 【quote_id】- 中文括号且缺少CITE标记
            # 4. [quote_id] - 英文括号且缺少CITE标记
            # 统一输出为：[quote_id](CITE) 格式
            citation_pattern = r'[\[【]([a-f0-9]{24})[\]】](\(CITE\))*'
            matches = re.finditer(citation_pattern, text)
            
            # 存储需要替换的内容
            replacements = []
            for match in matches:
                quote_id = match.group(1)
                full_match = match.group(0)
                
                # 检查缓存中是否已有处理结果
                if quote_id in citation_cache:
                    preview_url = citation_cache[quote_id]
                    new_link = f"[📌]({preview_url})"
                    replacements.append((full_match, new_link))
                    logger.debug(f"使用缓存引用: {quote_id} -> {preview_url}")
                    continue
                
                # 检查是否正在处理中
                if quote_id in processing_citations:
                    logger.debug(f"引用正在处理中，暂时显示为空: {quote_id}")
                    # 如果引用正在处理中，暂时设置为普通文本
                    temp_link = f"📌"
                    replacements.append((full_match, temp_link))
                    continue
                
                # 新引用，需要获取数据并创建预览
                logger.info(f"发现新知识块引用，开始处理: {quote_id}")
                
                # 标记为处理中
                processing_citations.add(quote_id)
                
                try:
                    # 直接构建预览URL，包含必要的参数
                    preview_url = await self._create_quote_preview_url(quote_id, chat_id, chat_item_data_id)
                    if preview_url:
                        new_link = f"[📌]({preview_url})"
                        replacements.append((full_match, new_link))
                        # 缓存处理结果
                        citation_cache[quote_id] = preview_url
                        logger.info(f"新引用处理成功: {quote_id} -> {preview_url}")
                    else:
                        logger.warning(f"创建预览URL失败，使用普通文本: {quote_id}")
                        temp_link = f"📌"
                        replacements.append((full_match, temp_link))
                        
                finally:
                    # 无论成功失败，都要从处理中集合移除
                    processing_citations.discard(quote_id)
            
            # 执行替换
            processed_text = text
            for old_link, new_link in replacements:
                processed_text = processed_text.replace(old_link, new_link)
            
            return processed_text
            
        except Exception as e:
            logger.error(f"处理知识块引用异常: {str(e)}")
            return text  # 出错时返回原文本
    
    async def _create_quote_preview_url(self, quote_id: str, chat_id: str, chat_item_data_id: str) -> Optional[str]:
        """创建知识块预览URL（简化版，直接传递参数）
        
        Args:
            quote_id: 知识块ID
            chat_id: 聊天ID
            
        Returns:
            str: 预览链接，失败返回None
        """
        try:
            # 检查是否有图床配置用于构建完整URL
            if not self.app_config or not hasattr(self.app_config, 'image_bed_base_url'):
                logger.warning("image_bed_base_url配置不完整，无法创建预览链接")
                return None
            
            base_url = getattr(self.app_config, 'image_bed_base_url')
            
            # 使用aichat_app_id
            app_id_for_preview = getattr(self.app_config, 'aichat_app_id', '')
            
            # 直接构建预览URL，将参数传递给前端页面
            preview_url = f"{base_url.rstrip('/')}/api/v1/collection-viewer/view-quote/{quote_id}?app_id={app_id_for_preview}&chat_id={chat_id}&chat_item_data_id={chat_item_data_id}"
            
            logger.info(f"创建知识块预览URL: {preview_url}")
            return preview_url
            
        except Exception as e:
            logger.error(f"创建预览URL异常: {str(e)}")
            return None

    async def _download_and_process_file(self, message_id: str, file_key: str, file_name: str = "unknown") -> Dict[str, Any]:
        """下载文件并保存到本地图床目录
        
        Args:
            message_id: 消息ID
            file_key: 文件key
            file_name: 文件名
            
        Returns:
            Dict包含文件信息和访问URL
        """
        try:
            # 获取tenant_access_token
            token = await self.get_tenant_access_token()
            
            # 构建下载URL
            url = f"{self.base_url}/open-apis/im/v1/messages/{message_id}/resources/{file_key}?type=file"
            headers = {
                "Authorization": f"Bearer {token}"
            }
            
            logger.info(f"准备下载文件: {url}")
            
            # 下载文件
            async with aiohttp.ClientSession() as client:
                async with client.get(url, headers=headers) as response:
                    if response.status == 200:
                        content = await response.read()
                        logger.info(f"下载文件成功，大小: {len(content)} bytes")
                        
                        # 检测文件类型（基于文件扩展名）
                        file_ext = os.path.splitext(file_name.lower())[-1] if file_name else ""
                        
                        # 设置MIME类型
                        mime_type_map = {
                            '.pdf': 'application/pdf',
                            '.doc': 'application/msword',
                            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                            '.xls': 'application/vnd.ms-excel',
                            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                            '.ppt': 'application/vnd.ms-powerpoint',
                            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                            '.txt': 'text/plain',
                            '.json': 'application/json',
                            '.xml': 'application/xml',
                            '.csv': 'text/csv',
                            '.zip': 'application/zip',
                            '.rar': 'application/x-rar-compressed',
                            '.7z': 'application/x-7z-compressed'
                        }
                        
                        mime_type = mime_type_map.get(file_ext, 'application/octet-stream')
                        
                        # 生成安全的文件名（防止路径遍历攻击）
                        import uuid
                        import hashlib
                        import datetime
                        
                        # 使用时间戳和随机UUID生成唯一文件名，保持原扩展名
                        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        unique_id = str(uuid.uuid4())[:8]
                        safe_file_name = f"{timestamp}_{unique_id}{file_ext}"
                        
                        # 确保文件保存目录存在
                        files_dir = os.path.join(os.getcwd(), "static", "files")
                        os.makedirs(files_dir, exist_ok=True)
                        
                        # 构建完整的文件路径
                        file_path = os.path.join(files_dir, safe_file_name)
                        
                        # 保存文件到本地
                        with open(file_path, 'wb') as f:
                            f.write(content)
                        
                        # 保存原始文件名映射（用于下载时显示正确的文件名）
                        mapping_file = os.path.join(files_dir, f"{safe_file_name}.meta")
                        with open(mapping_file, 'w', encoding='utf-8') as f:
                            json.dump({
                                "original_name": file_name,
                                "safe_name": safe_file_name,
                                "upload_time": timestamp,
                                "file_size": len(content),
                                "mime_type": mime_type
                            }, f, ensure_ascii=False, indent=2)
                        
                        # 构建文件访问URL（使用API端点支持下载模式）
                        if self.app_config and hasattr(self.app_config, 'image_bed_base_url'):
                            base_url = getattr(self.app_config, 'image_bed_base_url')
                            file_url = f"{base_url.rstrip('/')}/api/v1/static/files/{safe_file_name}"
                        else:
                            # 如果没有配置base_url，使用相对路径
                            file_url = f"/api/v1/static/files/{safe_file_name}"
                        
                        logger.info(f"文件保存成功: {file_path}")
                        logger.info(f"文件访问URL: {file_url}")
                        logger.info(f"文件名映射保存: {mapping_file}")
                        
                        return {
                            "file_name": file_name,
                            "safe_file_name": safe_file_name,
                            "file_size": len(content),
                            "file_url": file_url,
                            "local_path": file_path,
                            "mime_type": mime_type,
                            "file_extension": file_ext,
                            "success": True
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"下载文件失败: {response.status}, 错误信息: {error_text}")
                        return {
                            "error": f"下载失败: HTTP {response.status}",
                            "success": False
                        }
                        
        except Exception as e:
            logger.error(f"下载和处理文件异常: {str(e)}")
            return {
                "error": f"文件处理异常: {str(e)}",
                "success": False
            }
    
    async def get_group_chat_context(self, app_id: str, chat_id: str, context_limit: int = 5) -> str:
        """获取群聊上下文"""
        try:
            context = await self.chat_message_service.get_context_for_reply(app_id, chat_id, context_limit)
            return context
        except Exception as e:
            logger.error(f"获取群聊上下文失败: {str(e)}")
            return ""
    