import lark_oapi as lark
from typing import Dict, List, Optional, Any
import threading
import time
import sys
import os
import pymysql
from app.core.config import settings
from app.core.logger import setup_logger, setup_app_logger
from app.models.doc_subscription import DocSubscription
from sqlalchemy import select, create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
from sqlalchemy import update

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
        logger = setup_app_logger("feishu_callback", target_app.app_id, target_app.app_name)
    else:
        logger = setup_logger("feishu_callback")
else:
    # 多应用模式：使用全局logger
    logger = setup_logger("feishu_callback")

class FeishuCallbackService:
    """飞书回调服务 - 单应用模式"""
    
    _instance = None
    _lock = threading.Lock()
    _status = "stopped"  # 服务状态：stopped, running, error
    _app_info = None     # 当前应用信息
    _client = None       # 回调客户端
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(FeishuCallbackService, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
    def start_callback_service(self, app_id: str, app_secret: str, app_name: str = ""):
        """启动回调服务
        
        由于飞书SDK限制，一个进程只能有一个回调长连接。
        启动前会先检查是否已有服务运行，如有则停止旧服务。
        
        Args:
            app_id: 应用ID
            app_secret: 应用密钥
            app_name: 应用名称
        
        Returns:
            bool: 是否成功启动
        """
        # 如果已有服务正在运行，且是相同的应用，则不需要重新启动
        if self._status == "running" and self._app_info and self._app_info.get("app_id") == app_id:
            logger.info(f"应用 {app_name or app_id} 的回调服务已在运行中")
            return True
        
        # 如果有其他应用的服务在运行，先停止它
        if self._status == "running":
            self.stop_callback_service()
        
        # 设置应用信息
        self._app_info = {
            "app_id": app_id,
            "app_secret": app_secret,
            "app_name": app_name
        }
        
        try:
            # 创建并启动回调服务线程
            logger.info(f"开始启动应用 {app_name or app_id} 的回调服务")
            
            callback_thread = threading.Thread(
                target=self._run_callback_service,
                args=(app_id, app_secret, app_name),
                daemon=True
            )
            callback_thread.start()
            
            # 等待服务启动
            start_time = time.time()
            while time.time() - start_time < 5:  # 最多等待5秒
                if self._status == "running":
                    return True
                if self._status == "error":
                    return False
                time.sleep(0.1)
            
            # 如果超时仍未启动，认为启动失败
            logger.error(f"启动超时：应用 {app_name or app_id} 的回调服务启动超时")
            self._status = "error"
            return False
            
        except Exception as e:
            logger.error(f"启动失败：应用 {app_name or app_id} 的回调服务启动出错: {str(e)}")
            self._status = "error"
            return False
    
    def _run_callback_service(self, app_id: str, app_secret: str, app_name: str):
        """在独立线程中运行回调服务"""
        try:
            # 配置日志
            log_dir = os.path.join(os.getcwd(), "logs")
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, f"feishu_callback_{app_id}.log")
            
            # 创建事件处理函数
            def do_p2_drive_file_edit_v1(data: lark.drive.v1.P2DriveFileEditV1) -> None:
                """处理文件编辑事件"""
                logger.info(f"收到文件编辑事件: {lark.JSON.marshal(data)}")
                
                # 解析事件数据
                event = data.event
                file_token = event.file_token if hasattr(event, 'file_token') else None
                operator_id = event.operator.id if hasattr(event, 'operator') and hasattr(event.operator, 'id') else None
                file_type = event.file_type if hasattr(event, 'file_type') else None
                
                # 获取应用ID
                app_id = data.header.app_id if hasattr(data, 'header') and hasattr(data.header, 'app_id') else None
                
                # 查询文档订阅信息
                doc_info, subscription = self._get_doc_info(file_token, app_id)
                
                logger.info(f"文件 {file_token} ({file_type}) {doc_info} 被用户 {operator_id} 编辑")
                
                # 更新文档最后编辑时间
                try:
                    if app_id and file_token:
                        # 从回调消息中获取创建时间
                        create_time_ms = data.header.create_time if hasattr(data, 'header') and hasattr(data.header, 'create_time') else None
                        
                        if create_time_ms:
                            # 转换毫秒时间戳为datetime
                            create_time = datetime.fromtimestamp(int(create_time_ms) / 1000)
                            
                            # 更新数据库
                            engine = create_engine(settings.SQLALCHEMY_DATABASE_URI.replace("mysql+aiomysql://", "mysql+pymysql://"))
                            Session = sessionmaker(bind=engine)
                            with Session() as session:
                                # 更新数据库中的编辑时间
                                stmt = update(DocSubscription).where(
                                    DocSubscription.file_token == file_token,
                                    DocSubscription.app_id == app_id
                                ).values(obj_edit_time=create_time)
                                
                                session.execute(stmt)
                                session.commit()
                                logger.info(f"已更新文档 {file_token} 的最后编辑时间为 {create_time}")
                        else:
                            logger.warning(f"回调消息中没有create_time字段，无法更新文档编辑时间")
                except Exception as e:
                    logger.error(f"更新文档编辑时间失败: {str(e)}")
                
                # 必须返回None，表示成功接收
                return None

            def do_p2_drive_file_title_updated_v1(data: lark.drive.v1.P2DriveFileTitleUpdatedV1) -> None:
                """处理文件标题更新事件"""
                logger.info(f"收到文件标题更新事件: {lark.JSON.marshal(data)}")
                
                # 解析事件数据
                event = data.event
                file_token = event.file_token if hasattr(event, 'file_token') else None
                operator_id = event.operator.id if hasattr(event, 'operator') and hasattr(event.operator, 'id') else None
                file_type = event.file_type if hasattr(event, 'file_type') else None
                old_title = event.old_title if hasattr(event, 'old_title') else ''
                title = event.title if hasattr(event, 'title') else ''
                
                # 获取应用ID
                app_id = data.header.app_id if hasattr(data, 'header') and hasattr(data.header, 'app_id') else None
                
                # 查询文档订阅信息
                doc_info, subscription = self._get_doc_info(file_token, app_id)
                
                # 更新文档标题
                try:
                    if subscription:
                        engine = create_engine(settings.SQLALCHEMY_DATABASE_URI.replace("mysql+aiomysql://", "mysql+pymysql://"))
                        Session = sessionmaker(bind=engine)
                        with Session() as session:
                            # 查询订阅记录
                            query = select(DocSubscription).where(
                                DocSubscription.file_token == file_token,
                                DocSubscription.app_id == app_id
                            )
                            sub = session.execute(query).scalar_one_or_none()
                            if sub:
                                sub.title = title
                                session.commit()
                                logger.info(f"已更新文档标题: {title}")
                except Exception as e:
                    logger.error(f"更新文档标题失败: {str(e)}")
                
                logger.info(f"文件 {file_token} ({file_type}) {doc_info} 的标题被用户 {operator_id} 从 '{old_title}' 修改为 '{title}'")
                
                # 必须返回None，表示成功接收
                return None

            def do_p2_drive_file_created_in_folder_v1(data: lark.drive.v1.P2DriveFileCreatedInFolderV1) -> None:
                """处理文件夹下文件创建事件"""
                logger.info(f"收到文件夹下文件创建事件: {lark.JSON.marshal(data)}")
                
                # 解析事件数据
                event = data.event
                file_token = event.file_token if hasattr(event, 'file_token') else None
                operator_id = event.operator.id if hasattr(event, 'operator') and hasattr(event.operator, 'id') else None
                file_type = event.file_type if hasattr(event, 'file_type') else None
                parent_token = event.parent_token if hasattr(event, 'parent_token') else None
                
                # 获取应用ID
                app_id = data.header.app_id if hasattr(data, 'header') and hasattr(data.header, 'app_id') else None
                
                # 查询文档订阅信息
                doc_info, _ = self._get_doc_info(file_token, app_id)
                
                logger.info(f"用户 {operator_id} 在文件夹 {parent_token} 下创建了文件 {file_token} ({file_type}) {doc_info}")
                
                # 必须返回None，表示成功接收
                return None

            def do_p2_drive_file_trashed_v1(data: lark.drive.v1.P2DriveFileTrashedV1) -> None:
                """处理文件删除到回收站事件"""
                logger.info(f"收到文件删除到回收站事件: {lark.JSON.marshal(data)}")
                
                # 解析事件数据
                event = data.event
                file_token = event.file_token if hasattr(event, 'file_token') else None
                operator_id = event.operator.id if hasattr(event, 'operator') and hasattr(event.operator, 'id') else None
                file_type = event.file_type if hasattr(event, 'file_type') else None
                
                # 获取应用ID
                app_id = data.header.app_id if hasattr(data, 'header') and hasattr(data.header, 'app_id') else None
                
                # 查询文档订阅信息
                doc_info, _ = self._get_doc_info(file_token, app_id)
                
                logger.info(f"文件 {file_token} ({file_type}) {doc_info} 被用户 {operator_id} 删除到回收站")
                
                # 必须返回None，表示成功接收
                return None
            
            def do_p2_im_message_receive_v1(data: lark.im.v1.P2ImMessageReceiveV1) -> None:
                """处理机器人接收消息事件"""
                logger.info(f"收到机器人消息事件: {lark.JSON.marshal(data, indent=4)}")
                
                try:
                    # 解析消息数据
                    event = data.event
                    sender = event.sender
                    message = event.message
                    
                    # 获取发送者信息
                    sender_id = sender.sender_id.user_id if hasattr(sender, 'sender_id') and hasattr(sender.sender_id, 'user_id') else None
                    sender_type = sender.sender_type if hasattr(sender, 'sender_type') else None
                    
                    # 获取消息内容
                    message_id = message.message_id if hasattr(message, 'message_id') else None
                    message_type = message.message_type if hasattr(message, 'message_type') else None
                    content = message.content if hasattr(message, 'content') else None
                    chat_id = message.chat_id if hasattr(message, 'chat_id') else None
                    chat_type = message.chat_type if hasattr(message, 'chat_type') else None
                    
                    # 获取应用ID
                    app_id = data.header.app_id if hasattr(data, 'header') and hasattr(data.header, 'app_id') else None
                    
                    logger.info(f"机器人收到消息 - 发送者: {sender_id} ({sender_type}), 消息类型: {message_type}, 聊天ID: {chat_id} ({chat_type})")
                    
                    # 处理所有类型的消息（文本、音频、富文本等）
                    if message_type and content:
                        try:
                            import json
                            
                            # 根据消息类型记录不同的日志信息
                            if message_type == "text":
                                text_content = json.loads(content).get("text", "")
                                logger.info(f"文本消息内容: {text_content}")
                            elif message_type == "audio":
                                audio_content = json.loads(content)
                                file_key = audio_content.get("file_key")
                                duration = audio_content.get("duration", 0)
                                logger.info(f"音频消息内容: file_key={file_key}, duration={duration}ms")
                            elif message_type == "file":
                                file_content = json.loads(content)
                                file_key = file_content.get("file_key")
                                file_name = file_content.get("file_name", "未知文件")
                                file_size = file_content.get("file_size", 0)
                                logger.info(f"文件消息内容: file_key={file_key}, file_name={file_name}, file_size={file_size}")
                            elif message_type == "post":
                                post_content = json.loads(content)
                                logger.info(f"富文本消息内容结构: {json.dumps(post_content, ensure_ascii=False, indent=2)}")
                            else:
                                logger.info(f"其他类型消息: {message_type}")
                            
                            # 统一调用机器人服务处理消息
                            self._handle_bot_message_async(app_id, data)
                            
                        except Exception as e:
                            logger.error(f"解析{message_type}消息失败: {str(e)}")
                    else:
                        logger.warning(f"收到空消息或未知消息类型: type={message_type}")
                    
                except Exception as e:
                    logger.error(f"处理机器人消息事件失败: {str(e)}")
                
                # 必须返回None，表示成功接收
                return None

            def do_p2_application_bot_menu_v6(data: lark.application.v6.P2ApplicationBotMenuV6) -> None:
                """处理机器人菜单事件"""
                logger.info(f"收到机器人菜单事件: {lark.JSON.marshal(data, indent=4)}")
                
                try:
                    # 解析事件数据
                    event = data.event
                    header = data.header
                    
                    # 获取事件基本信息
                    event_key = event.event_key if hasattr(event, 'event_key') else None
                    timestamp = event.timestamp if hasattr(event, 'timestamp') else None
                    
                    # 获取操作用户信息
                    operator = event.operator if hasattr(event, 'operator') else None
                    operator_id = None
                    user_id = None
                    open_id = None
                    union_id = None
                    
                    if operator and hasattr(operator, 'operator_id'):
                        operator_info = operator.operator_id
                        user_id = operator_info.user_id if hasattr(operator_info, 'user_id') else None
                        open_id = operator_info.open_id if hasattr(operator_info, 'open_id') else None
                        union_id = operator_info.union_id if hasattr(operator_info, 'union_id') else None
                    
                    # 获取应用信息
                    app_id = header.app_id if hasattr(header, 'app_id') else None
                    tenant_key = header.tenant_key if hasattr(header, 'tenant_key') else None
                    event_id = header.event_id if hasattr(header, 'event_id') else None
                    create_time = header.create_time if hasattr(header, 'create_time') else None
                    
                    # 记录详细日志
                    logger.info(f"机器人菜单事件详情:")
                    logger.info(f"  事件类型: application.bot.menu_v6")
                    logger.info(f"  子事件: {event_key}")
                    logger.info(f"  事件ID: {event_id}")
                    logger.info(f"  应用ID: {app_id}")
                    logger.info(f"  租户Key: {tenant_key}")
                    logger.info(f"  创建时间: {create_time}")
                    logger.info(f"  时间戳: {timestamp}")
                    logger.info(f"  操作用户:")
                    logger.info(f"    User ID: {user_id}")
                    logger.info(f"    Open ID: {open_id}")
                    logger.info(f"    Union ID: {union_id}")
                    
                    # 针对不同子事件的处理
                    if event_key == "bot_new_chat":
                        logger.info(f"处理bot_new_chat事件:")
                        logger.info(f"  用户 {user_id} (Open ID: {open_id}) 触发了新建聊天菜单")
                        logger.info(f"  该事件表示用户通过机器人菜单发起了新的对话")
                        
                        # 转换时间戳为可读格式
                        if create_time:
                            try:
                                import datetime
                                create_time_int = int(create_time)
                                # 如果是毫秒级时间戳，转换为秒级
                                if create_time_int > 10**10:
                                    create_time_int = create_time_int // 1000
                                dt = datetime.datetime.fromtimestamp(create_time_int)
                                logger.info(f"  事件发生时间: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                            except Exception as e:
                                logger.warning(f"时间戳转换失败: {str(e)}")
                        
                        # 创建新的聊天会话
                        if app_id and user_id:
                            try:
                                from app.services.user_chat_session_service import UserChatSessionService
                                
                                # 获取应用名称和配置
                                app_name = None
                                app_secret = None
                                for app in settings.FEISHU_APPS:
                                    if app.app_id == app_id:
                                        app_name = app.app_name
                                        app_secret = app.app_secret
                                        break
                                
                                # 创建聊天会话服务并生成新的chat_id
                                session_service = UserChatSessionService()
                                new_chat_id = session_service.create_new_chat_session(
                                    app_id=app_id,
                                    user_id=user_id,
                                    open_id=open_id,
                                    app_name=app_name
                                )
                                
                                logger.info(f"  已为用户创建新的聊天会话:")
                                logger.info(f"    应用: {app_name or app_id}")
                                logger.info(f"    用户ID: {user_id}")
                                logger.info(f"    新Chat ID: {new_chat_id}")
                                
                                # 发送新会话分隔消息（异步执行）
                                if app_secret:
                                    try:
                                        self._send_new_session_message_async(app_id, app_secret, user_id, app_name)
                                    except Exception as msg_error:
                                        logger.error(f"启动发送新会话消息失败: {str(msg_error)}")
                                else:
                                    logger.warning("缺少app_secret，无法发送新会话消息")
                                
                            except Exception as e:
                                logger.error(f"创建聊天会话失败: {str(e)}")
                                import traceback
                                logger.error(f"错误详情: {traceback.format_exc()}")
                        else:
                            logger.warning(f"缺少必要参数，无法创建聊天会话: app_id={app_id}, user_id={user_id}")
                    
                    elif event_key in ["bot_search_dataset", "bot_search_web", "bot_search_all"]:
                        logger.info(f"处理搜索模式选择事件: {event_key}")
                        logger.info(f"  用户 {user_id} (Open ID: {open_id}) 选择了搜索模式")
                        
                        # 转换时间戳为可读格式
                        if create_time:
                            try:
                                import datetime
                                create_time_int = int(create_time)
                                if create_time_int > 10**10:
                                    create_time_int = create_time_int // 1000
                                dt = datetime.datetime.fromtimestamp(create_time_int)
                                logger.info(f"  事件发生时间: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                            except Exception as e:
                                logger.warning(f"时间戳转换失败: {str(e)}")
                        
                        # 设置搜索偏好
                        if app_id and user_id:
                            try:
                                from app.services.user_chat_session_service import UserChatSessionService
                                from app.services.user_search_preference_service import UserSearchPreferenceService
                                
                                # 获取应用名称和配置
                                app_name = None
                                app_secret = None
                                for app in settings.FEISHU_APPS:
                                    if app.app_id == app_id:
                                        app_name = app.app_name
                                        app_secret = app.app_secret
                                        break
                                
                                # 确定搜索模式
                                search_mode_map = {
                                    "bot_search_dataset": "dataset",
                                    "bot_search_web": "web",
                                    "bot_search_all": "all"
                                }
                                search_mode = search_mode_map.get(event_key)
                                
                                # 设置搜索偏好
                                preference_service = UserSearchPreferenceService()
                                success = preference_service.set_search_preference(
                                    app_id=app_id,
                                    user_id=user_id,
                                    search_mode=search_mode
                                )
                                
                                if success:
                                    mode_name = preference_service.get_search_mode_display_name(search_mode)
                                    logger.info(f"  已设置搜索偏好:")
                                    logger.info(f"    应用: {app_name or app_id}")
                                    logger.info(f"    用户ID: {user_id}")
                                    logger.info(f"    搜索模式: {mode_name}")
                                    logger.info(f"    该偏好将应用于用户在此应用的所有会话")
                                    
                                    # 发送搜索模式设置确认消息
                                    if app_secret:
                                        try:
                                            self._send_search_mode_confirmation_async(
                                                app_id, app_secret, user_id, search_mode, app_name
                                            )
                                        except Exception as msg_error:
                                            logger.error(f"启动发送搜索模式确认消息失败: {str(msg_error)}")
                                else:
                                    logger.error(f"设置搜索偏好失败")
                                
                            except Exception as e:
                                logger.error(f"处理搜索模式选择失败: {str(e)}")
                                import traceback
                                logger.error(f"错误详情: {traceback.format_exc()}")
                        else:
                            logger.warning(f"缺少必要参数，无法设置搜索偏好: app_id={app_id}, user_id={user_id}")
                    
                    else:
                        logger.info(f"处理其他机器人菜单事件: {event_key}")
                    
                except Exception as e:
                    logger.error(f"处理机器人菜单事件失败: {str(e)}")
                    import traceback
                    logger.error(f"错误详情: {traceback.format_exc()}")
                
                # 必须返回None，表示成功接收
                return None

            def do_p2_card_action_trigger(data: 'lark.im.v2.P2CardActionTrigger') -> None:
                """处理卡片交互事件（停止回答按钮）"""
                logger.info(f"收到卡片交互事件: {lark.JSON.marshal(data, indent=4)}")
                
                try:
                    # 解析事件数据 - 新版本结构在data.event中
                    event = data.event
                    action = event.action if hasattr(event, 'action') else None
                    context = event.context if hasattr(event, 'context') else None
                    operator = event.operator if hasattr(event, 'operator') else None
                    
                    # 获取操作相关信息
                    action_value = action.value if action and hasattr(action, 'value') else {}
                    action_tag = action.tag if action and hasattr(action, 'tag') else None
                    action_name = action.name if action and hasattr(action, 'name') else None
                    
                    # 获取用户信息
                    open_id = operator.open_id if operator and hasattr(operator, 'open_id') else None
                    user_id = operator.user_id if operator and hasattr(operator, 'user_id') else None
                    
                    # 获取消息上下文
                    open_message_id = context.open_message_id if context and hasattr(context, 'open_message_id') else None
                    open_chat_id = context.open_chat_id if context and hasattr(context, 'open_chat_id') else None
                    
                    # 获取应用信息
                    app_id = data.header.app_id if hasattr(data, 'header') and hasattr(data.header, 'app_id') else None
                    event_id = data.header.event_id if hasattr(data, 'header') and hasattr(data.header, 'event_id') else None
                    
                    logger.info(f"卡片交互事件详情:")
                    logger.info(f"  事件类型: card.action.trigger")
                    logger.info(f"  事件ID: {event_id}")
                    logger.info(f"  应用ID: {app_id}")
                    logger.info(f"  操作类型: {action_tag}")
                    logger.info(f"  操作名称: {action_name}")
                    logger.info(f"  回调数据: {action_value}")
                    logger.info(f"  操作用户: {user_id} (Open ID: {open_id})")
                    logger.info(f"  消息ID: {open_message_id}")
                    logger.info(f"  会话ID: {open_chat_id}")
                    
                    # 处理停止回答操作
                    if isinstance(action_value, dict) and action_value.get("action") == "stop_streaming":
                        card_id = action_value.get("card_id")
                        
                        logger.info(f"处理停止回答请求:")
                        logger.info(f"  卡片ID: {card_id}")
                        logger.info(f"  用户 {user_id} 请求停止流式回答")
                        
                        if app_id and card_id:
                            try:
                                # 获取应用配置
                                app_secret = None
                                for app in settings.FEISHU_APPS:
                                    if app.app_id == app_id:
                                        app_secret = app.app_secret
                                        break
                                
                                if app_secret:
                                    # 创建飞书机器人服务实例并调用停止方法
                                    from app.services.feishu_bot import FeishuBotService
                                    
                                    bot_service = FeishuBotService(app_id, app_secret)
                                    success = bot_service.stop_streaming_reply(card_id)
                                    
                                    if success:
                                        logger.info(f"成功设置停止标志，卡片ID: {card_id}")
                                    else:
                                        logger.warning(f"设置停止标志失败，卡片ID: {card_id}")
                                        
                                else:
                                    logger.error(f"未找到应用 {app_id} 的配置信息")
                                    
                            except Exception as e:
                                logger.error(f"处理停止回答请求失败: {str(e)}")
                                import traceback
                                logger.error(f"错误详情: {traceback.format_exc()}")
                        else:
                            logger.warning(f"缺少必要参数: app_id={app_id}, card_id={card_id}")
                    
                    else:
                        logger.info(f"未识别的卡片交互操作: {action_value}")
                    
                except Exception as e:
                    logger.error(f"处理卡片交互事件失败: {str(e)}")
                    import traceback
                    logger.error(f"错误详情: {traceback.format_exc()}")
                
                # 必须返回None，表示成功接收
                return None
            
            # 创建事件处理器
            logger.info("开始注册事件处理器...")
            
            # 检查应用是否启用了AI Chat功能
            aichat_enabled = False
            for app in settings.FEISHU_APPS:
                if app.app_id == app_id:
                    aichat_enabled = getattr(app, 'aichat_enable', False)
                    break
            
            # 创建事件处理器构建器
            handler_builder = lark.EventDispatcherHandler.builder("", "") \
                .register_p2_drive_file_edit_v1(do_p2_drive_file_edit_v1) \
                .register_p2_drive_file_title_updated_v1(do_p2_drive_file_title_updated_v1) \
                .register_p2_drive_file_created_in_folder_v1(do_p2_drive_file_created_in_folder_v1) \
                .register_p2_drive_file_trashed_v1(do_p2_drive_file_trashed_v1) \
                .register_p2_application_bot_menu_v6(do_p2_application_bot_menu_v6) \
                .register_p2_card_action_trigger(do_p2_card_action_trigger)
            
            # 只有在启用AI Chat时才注册机器人消息事件
            if aichat_enabled:
                handler_builder = handler_builder.register_p2_im_message_receive_v1(do_p2_im_message_receive_v1)
                logger.info("AI Chat已启用，将注册机器人消息接收事件")
            else:
                logger.info("AI Chat未启用，跳过机器人消息接收事件注册")
            
            # 构建事件处理器
            event_handler = handler_builder.build()
            
            logger.info("事件处理器注册完成，已注册以下事件:")
            logger.info("- 文件编辑事件 (file.edit_v1)")
            logger.info("- 标题更新事件 (file.title_update_v1)")
            logger.info("- 文件创建事件 (file.created_in_folder_v1)")
            logger.info("- 文件删除事件 (file.trashed_v1)")
            logger.info("- 机器人菜单事件 (application.bot.menu_v6)")
            logger.info("- 卡片交互事件 (card.action.trigger)")
            if aichat_enabled:
                logger.info("- 机器人消息事件 (im.message.receive_v1)")
            else:
                logger.info("- 机器人消息事件: 未注册 (AI Chat功能未启用)")
            
            # 创建客户端
            self._client = lark.ws.Client(
                app_id, 
                app_secret,
                event_handler=event_handler, 
                log_level=lark.LogLevel.DEBUG
            )
            
            # 更新状态为运行中
            self._status = "running"
            logger.info(f"飞书回调服务启动成功，应用: {app_name or app_id}")
            
            # 启动客户端
            try:
                self._client.start()
            except Exception as e:
                logger.error(f"飞书回调服务运行错误: {str(e)}")
                self._status = "error"
        except Exception as e:
            logger.error(f"飞书回调服务初始化错误: {str(e)}")
            self._status = "error"
    
    def stop_callback_service(self):
        """停止回调服务"""
        if self._status != "running" or not self._client:
            logger.warning("没有正在运行的回调服务")
            return
        
        app_info = self._app_info or {}
        app_id = app_info.get("app_id", "未知")
        app_name = app_info.get("app_name", "")
        
        try:
            logger.info(f"正在停止应用 {app_name or app_id} 的回调服务")
            
            # 停止客户端
            if self._client:
                self._client.stop()
                self._client = None
            
            self._status = "stopped"
            logger.info(f"应用 {app_name or app_id} 的回调服务已停止")
            
        except Exception as e:
            logger.error(f"停止应用 {app_name or app_id} 的回调服务失败: {str(e)}")
            self._status = "error"
    
    def get_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        status = {
            "status": self._status,
            "running": self._status == "running"
        }
        
        if self._app_info:
            status.update({
                "app_id": self._app_info.get("app_id"),
                "app_name": self._app_info.get("app_name", ""),
            })
            
        return status
    
    def start_callback_services(self):
        """兼容旧接口，仅启动配置中的第一个应用"""
        if not settings.FEISHU_APPS:
            logger.warning("没有配置飞书应用，无法启动回调服务")
            return
        
        # 仅启动第一个应用
        app = settings.FEISHU_APPS[0]
        self.start_callback_service(app.app_id, app.app_secret, app.app_name)
        
    def stop_all_callback_services(self):
        """兼容旧接口，停止当前运行的应用"""
        self.stop_callback_service()
        
    def get_client_status(self, app_id: str = None) -> Dict:
        """兼容旧接口，获取客户端状态"""
        status = self.get_status()
        
        if app_id and status.get("app_id") != app_id:
            return {"status": "not_started"}
            
        return status
    
    def _get_doc_info(self, file_token: str, app_id: str) -> tuple:
        """获取文档订阅信息
        
        Args:
            file_token: 文档Token
            app_id: 应用ID
            
        Returns:
            tuple: (doc_info_str, subscription对象)
        """
        doc_info = ""
        subscription = None
        
        try:
            # 创建同步数据库会话
            engine = create_engine(settings.SQLALCHEMY_DATABASE_URI.replace("mysql+aiomysql://", "mysql+pymysql://"))
            Session = sessionmaker(bind=engine)
            with Session() as session:
                # 查询订阅记录
                query = select(DocSubscription).where(
                    DocSubscription.file_token == file_token,
                    DocSubscription.app_id == app_id
                )
                subscription = session.execute(query).scalar_one_or_none()
                
                if subscription:
                    doc_info = f"[应用ID:{subscription.app_id}]"
                    if subscription.title:
                        doc_info += f" [文档:{subscription.title}]"
                    if subscription.space_id:
                        doc_info += f" [知识空间ID:{subscription.space_id}]"
        except Exception as e:
            logger.error(f"查询文档订阅信息失败: {str(e)}")
        
        return doc_info, subscription
    
    def _handle_bot_message_async(self, app_id: str, data: 'lark.im.v1.P2ImMessageReceiveV1') -> None:
        """异步处理机器人消息
        
        Args:
            app_id: 应用ID
            data: 消息事件数据
        """
        try:
            import asyncio
            import threading
            from concurrent.futures import ThreadPoolExecutor
            
            # 使用线程池执行器避免事件循环冲突
            def run_message_processing():
                try:
                    # 创建独立的事件循环
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    try:
                        # 运行异步处理
                        loop.run_until_complete(self._process_bot_message(app_id, data))
                    finally:
                        # 确保循环正确关闭
                        pending = asyncio.all_tasks(loop)
                        if pending:
                            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                        loop.close()
                        
                except Exception as e:
                    logger.error(f"线程中处理机器人消息失败: {str(e)}")
            
            # 在独立线程中运行，避免事件循环冲突
            thread = threading.Thread(target=run_message_processing, daemon=True)
            thread.start()
            
        except Exception as e:
            logger.error(f"启动机器人消息处理失败: {str(e)}")
    
    async def _process_bot_message(self, app_id: str, data: 'lark.im.v1.P2ImMessageReceiveV1') -> None:
        """处理机器人消息的具体逻辑
        
        Args:
            app_id: 应用ID  
            data: 消息事件数据
        """
        try:
            # 从配置中获取应用信息
            app_config = None
            for app in settings.FEISHU_APPS:
                if app.app_id == app_id:
                    app_config = {
                        "app_id": app.app_id,
                        "app_secret": app.app_secret,
                        "app_name": app.app_name
                    }
                    break
            
            if not app_config:
                logger.error(f"未找到应用配置: {app_id}")
                return
            
            # 导入机器人服务
            from app.services.feishu_bot import FeishuBotService
            
            # 创建机器人服务实例
            bot_service = FeishuBotService(app_config["app_id"], app_config["app_secret"])
            
            # 转换数据格式为兼容格式
            event_data = {
                "header": {
                    "app_id": app_id,
                    "event_type": "im.message.receive_v1"
                },
                "event": {
                    "sender": {
                        "sender_id": {
                            "user_id": data.event.sender.sender_id.user_id if hasattr(data.event.sender, 'sender_id') and hasattr(data.event.sender.sender_id, 'user_id') else None
                        },
                        "sender_type": data.event.sender.sender_type if hasattr(data.event.sender, 'sender_type') else None
                    },
                    "message": {
                        "message_id": data.event.message.message_id if hasattr(data.event.message, 'message_id') else None,
                        "message_type": data.event.message.message_type if hasattr(data.event.message, 'message_type') else None,
                        "content": data.event.message.content if hasattr(data.event.message, 'content') else None,
                        "chat_id": data.event.message.chat_id if hasattr(data.event.message, 'chat_id') else None,
                        "chat_type": data.event.message.chat_type if hasattr(data.event.message, 'chat_type') else None,
                        "mentions": [
                            {
                                "key": mention.key if hasattr(mention, 'key') else None,
                                "name": mention.name if hasattr(mention, 'name') else None,
                                "id": {
                                    "user_id": mention.id.user_id if hasattr(mention, 'id') and hasattr(mention.id, 'user_id') else None,
                                    "open_id": mention.id.open_id if hasattr(mention, 'id') and hasattr(mention.id, 'open_id') else None,
                                    "union_id": mention.id.union_id if hasattr(mention, 'id') and hasattr(mention.id, 'union_id') else None
                                } if hasattr(mention, 'id') else {},
                                "tenant_key": mention.tenant_key if hasattr(mention, 'tenant_key') else None
                            }
                            for mention in (data.event.message.mentions if hasattr(data.event.message, 'mentions') and data.event.message.mentions is not None else [])
                        ]
                    }
                }
            }
            
            # 调用机器人服务处理消息
            success = await bot_service.handle_message(event_data)
            
            if success:
                logger.info(f"机器人成功处理消息")
            else:
                logger.warning(f"机器人处理消息失败")
                
        except Exception as e:
            logger.error(f"处理机器人消息失败: {str(e)}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")

    def _send_new_session_message_async(self, app_id: str, app_secret: str, user_id: str, app_name: str = None) -> None:
        """异步发送新会话分隔消息
        
        Args:
            app_id: 应用ID
            app_secret: 应用密钥
            user_id: 用户ID
            app_name: 应用名称
        """
        try:
            import asyncio
            import threading
            
            # 使用线程池执行器避免事件循环冲突
            def run_message_sending():
                try:
                    # 创建独立的事件循环
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    try:
                        # 运行异步发送
                        loop.run_until_complete(self._send_new_session_message(app_id, app_secret, user_id, app_name))
                    finally:
                        # 确保循环正确关闭
                        pending = asyncio.all_tasks(loop)
                        if pending:
                            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                        loop.close()
                        
                except Exception as e:
                    logger.error(f"线程中发送新会话消息失败: {str(e)}")
            
            # 在独立线程中运行，避免事件循环冲突
            thread = threading.Thread(target=run_message_sending, daemon=True)
            thread.start()
            
        except Exception as e:
            logger.error(f"启动发送新会话消息失败: {str(e)}")

    async def _send_new_session_message(self, app_id: str, app_secret: str, user_id: str, app_name: str = None) -> None:
        """发送新会话分隔消息的具体逻辑
        
        Args:
            app_id: 应用ID
            app_secret: 应用密钥
            user_id: 用户ID
            app_name: 应用名称
        """
        try:
            # 导入机器人服务
            from app.services.feishu_bot import FeishuBotService
            
            # 创建机器人服务实例
            bot_service = FeishuBotService(app_id, app_secret)
            
            # 构建新会话分隔卡片
            card_content = self._build_new_session_card(app_name)
            
            # 发送卡片消息给用户
            success = await bot_service.send_card_message(
                receive_id=user_id,
                card_content=card_content,
                receive_id_type="user_id"
            )
            
            if success:
                logger.info(f"新会话分隔卡片发送成功: user_id={user_id}")
            else:
                logger.warning(f"新会话分隔卡片发送失败: user_id={user_id}")
                
        except Exception as e:
            logger.error(f"发送新会话分隔消息失败: {str(e)}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")

    def _build_new_session_card(self, app_name: str = None) -> dict:
        """构建新会话分隔卡片
        
        Args:
            app_name: 应用名称
            
        Returns:
            dict: 飞书卡片内容
        """
        # 获取当前时间
        from datetime import datetime
        current_time = datetime.now().strftime("%H:%M")
        
        # 构建应用显示名称
        if app_name:
            app_display = app_name
        else:
            app_display = "AI助手"
        
        # 构建Markdown内容，使用---分隔线
        markdown_content = f"""---

**✨ 新对话开始** `{current_time}`

🤖 **{app_display}** 为您服务

---

开始全新的对话吧！我会为您提供最佳的帮助。"""
        
        # 构建卡片结构
        card_content = {
            "schema": "2.0",
            "header": {
                "title": {
                    "content": f"🔄 新会话",
                    "tag": "plain_text"
                },
                "template": "blue"
            },
            "config": {
                "enable_forward": True,
                "width_mode": "fill"
            },
            "body": {
                "elements": [
                    {
                        "tag": "markdown",
                        "content": markdown_content
                    }
                ]
            }
        }
        
        return card_content

    def _send_search_mode_confirmation_async(self, app_id: str, app_secret: str, user_id: str, search_mode: str, app_name: str = None) -> None:
        """异步发送搜索模式设置确认消息
        
        Args:
            app_id: 应用ID
            app_secret: 应用密钥
            user_id: 用户ID
            search_mode: 搜索模式
            app_name: 应用名称
        """
        try:
            import asyncio
            import threading
            
            # 使用线程池执行器避免事件循环冲突
            def run_message_sending():
                try:
                    # 创建独立的事件循环
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    try:
                        # 运行异步发送
                        loop.run_until_complete(self._send_search_mode_confirmation(app_id, app_secret, user_id, search_mode, app_name))
                    finally:
                        # 确保循环正确关闭
                        pending = asyncio.all_tasks(loop)
                        if pending:
                            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                        loop.close()
                        
                except Exception as e:
                    logger.error(f"线程中发送搜索模式确认消息失败: {str(e)}")
            
            # 在独立线程中运行，避免事件循环冲突
            thread = threading.Thread(target=run_message_sending, daemon=True)
            thread.start()
            
        except Exception as e:
            logger.error(f"启动发送搜索模式确认消息失败: {str(e)}")

    async def _send_search_mode_confirmation(self, app_id: str, app_secret: str, user_id: str, search_mode: str, app_name: str = None) -> None:
        """发送搜索模式设置确认消息的具体逻辑
        
        Args:
            app_id: 应用ID
            app_secret: 应用密钥
            user_id: 用户ID
            search_mode: 搜索模式
            app_name: 应用名称
        """
        try:
            # 导入机器人服务
            from app.services.feishu_bot import FeishuBotService
            from app.services.user_search_preference_service import UserSearchPreferenceService
            
            # 创建机器人服务实例
            bot_service = FeishuBotService(app_id, app_secret)
            
            # 构建搜索模式确认卡片
            card_content = self._build_search_mode_confirmation_card(search_mode, app_name)
            
            # 发送卡片消息给用户
            success = await bot_service.send_card_message(
                receive_id=user_id,
                card_content=card_content,
                receive_id_type="user_id"
            )
            
            if success:
                logger.info(f"搜索模式确认卡片发送成功: user_id={user_id}, mode={search_mode}")
            else:
                logger.warning(f"搜索模式确认卡片发送失败: user_id={user_id}, mode={search_mode}")
                
        except Exception as e:
            logger.error(f"发送搜索模式确认消息失败: {str(e)}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")

    def _build_search_mode_confirmation_card(self, search_mode: str, app_name: str = None) -> dict:
        """构建搜索模式确认卡片
        
        Args:
            search_mode: 搜索模式
            app_name: 应用名称
            
        Returns:
            dict: 飞书卡片内容
        """
        # 获取当前时间
        from datetime import datetime
        current_time = datetime.now().strftime("%H:%M")
        
        # 构建应用显示名称
        if app_name:
            app_display = app_name
        else:
            app_display = "AI助手"
        
        # 搜索模式映射
        mode_info = {
            "dataset": {
                "name": "📚 知识库搜索",
                "desc": "仅在已有知识库中搜索相关信息",
                "color": "blue"
            },
            "web": {
                "name": "🌐 联网搜索", 
                "desc": "实时联网获取最新信息",
                "color": "green"
            },
            "all": {
                "name": "♾️ 知识库+联网搜索",
                "desc": "结合知识库和联网搜索，提供全面的信息",
                "color": "purple"
            }
        }
        
        mode_data = mode_info.get(search_mode, mode_info["dataset"])
        
        # 构建Markdown内容
        markdown_content = f"""---

**✅ 搜索模式已设置** `{current_time}`

**{mode_data['name']}**

{mode_data['desc']}

---

现在您可以开始提问，我将使用此搜索模式为您提供答案！"""
        
        # 构建卡片结构
        card_content = {
            "schema": "2.0",
            "header": {
                "title": {
                    "content": f"⚙️ 搜索设置",
                    "tag": "plain_text"
                },
                "template": mode_data["color"]
            },
            "config": {
                "enable_forward": True,
                "width_mode": "fill"
            },
            "body": {
                "elements": [
                    {
                        "tag": "markdown",
                        "content": markdown_content
                    }
                ]
            }
        }
        
        return card_content