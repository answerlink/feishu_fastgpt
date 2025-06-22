"""
聊天消息服务 - 统一管理私聊和群聊消息存储
"""

import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, and_, desc, func
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_config
from app.core.logger import setup_logger
from app.models.user_memory import ChatMessage

logger = setup_logger("chat_message_service")


class ChatMessageService:
    """聊天消息服务"""
    
    def __init__(self):
        """初始化服务"""
        try:
            config = get_config()
            # 使用同步数据库连接
            database_url = config.SQLALCHEMY_DATABASE_URI.replace("mysql+aiomysql://", "mysql+pymysql://")
            
            # 创建同步数据库引擎，优化连接池配置
            self.engine = create_engine(
                database_url,
                pool_size=config.SQLALCHEMY_POOL_SIZE,
                pool_timeout=config.SQLALCHEMY_POOL_TIMEOUT,
                pool_recycle=config.SQLALCHEMY_POOL_RECYCLE,
                pool_pre_ping=True,  # 启用连接预检查
                echo=config.SQLALCHEMY_ECHO,
                connect_args={
                    "charset": "utf8mb4",
                    "connect_timeout": 30,
                    "read_timeout": 30,
                    "write_timeout": 30,
                }
            )
            
            self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
            logger.info("聊天消息服务初始化成功")
            
        except Exception as e:
            logger.error(f"聊天消息服务初始化失败: {e}")
            self.SessionLocal = None
    
    async def save_message(self, message_data: Dict[str, Any]) -> bool:
        """保存聊天消息"""
        try:
            if not self.SessionLocal:
                logger.error("数据库连接不可用")
                return False
            
            # 在后台线程中执行数据库操作，带重试机制
            def _save_message():
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        with self.SessionLocal() as db:
                            # 检查消息是否已存在
                            existing = db.query(ChatMessage).filter(
                                ChatMessage.app_id == message_data["app_id"],
                                ChatMessage.message_id == message_data["message_id"]
                            ).first()
                            
                            if existing:
                                logger.debug(f"消息已存在，跳过保存: {message_data['message_id']}")
                                return True
                            
                            # 创建新消息记录
                            message = ChatMessage(
                                app_id=message_data["app_id"],
                                message_id=message_data["message_id"],
                                chat_type=message_data.get("chat_type", "group"),
                                chat_id=message_data["chat_id"],
                                chat_name=message_data.get("chat_name", ""),
                                sender_id=message_data["sender_id"],
                                sender_name=message_data.get("sender_name", ""),
                                raw_content=message_data.get("raw_content", ""),
                                pure_content=message_data.get("pure_content", ""),
                                message_type=message_data.get("message_type", "text"),
                                mention_users=message_data.get("mention_users", []),
                                mentioned_bot=message_data.get("mentioned_bot", False)
                            )
                            
                            db.add(message)
                            db.commit()
                            
                            logger.debug(f"消息保存成功: {message_data['message_id']}")
                            return True
                            
                    except Exception as e:
                        logger.error(f"保存消息失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                        if attempt < max_retries - 1:
                            import time
                            time.sleep(1)  # 等待1秒后重试
                        else:
                            return False
                
                return False
            
            # 在线程池中执行
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _save_message)
            
        except Exception as e:
            logger.error(f"保存消息异常: {e}")
            return False
    
    async def get_recent_messages(
        self, 
        app_id: str, 
        chat_id: str, 
        limit: int = 50,
        chat_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取最近的聊天消息"""
        try:
            if not self.SessionLocal:
                return []
            
            def _get_messages():
                try:
                    with self.SessionLocal() as db:
                        query = db.query(ChatMessage).filter(
                            ChatMessage.app_id == app_id,
                            ChatMessage.chat_id == chat_id
                        )
                        
                        if chat_type:
                            query = query.filter(ChatMessage.chat_type == chat_type)
                        
                        messages = query.order_by(
                            desc(ChatMessage.created_at)
                        ).limit(limit).all()
                        
                        return [msg.to_dict() for msg in messages]
                        
                except Exception as e:
                    logger.error(f"获取消息失败: {e}")
                    return []
            
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _get_messages)
            
        except Exception as e:
            logger.error(f"获取消息异常: {e}")
            return []
    
    async def get_chat_statistics(
        self, 
        app_id: str, 
        chat_id: str, 
        days: int = 7
    ) -> Dict[str, Any]:
        """获取聊天统计信息"""
        try:
            if not self.SessionLocal:
                return {}
            
            def _get_stats():
                try:
                    with self.SessionLocal() as db:
                        # 计算时间范围
                        end_time = datetime.now()
                        start_time = end_time - timedelta(days=days)
                        
                        # 基础查询条件
                        base_query = db.query(ChatMessage).filter(
                            ChatMessage.app_id == app_id,
                            ChatMessage.chat_id == chat_id,
                            ChatMessage.created_at >= start_time
                        )
                        
                        # 总消息数
                        total_messages = base_query.count()
                        
                        # 按用户统计
                        user_stats = db.query(
                            ChatMessage.sender_id,
                            ChatMessage.sender_name,
                            func.count(ChatMessage.id).label('message_count')
                        ).filter(
                            ChatMessage.app_id == app_id,
                            ChatMessage.chat_id == chat_id,
                            ChatMessage.created_at >= start_time
                        ).group_by(
                            ChatMessage.sender_id, ChatMessage.sender_name
                        ).order_by(
                            desc('message_count')
                        ).limit(10).all()
                        
                        # 按消息类型统计
                        type_stats = db.query(
                            ChatMessage.message_type,
                            func.count(ChatMessage.id).label('count')
                        ).filter(
                            ChatMessage.app_id == app_id,
                            ChatMessage.chat_id == chat_id,
                            ChatMessage.created_at >= start_time
                        ).group_by(ChatMessage.message_type).all()
                        
                        # @机器人的消息数
                        bot_mentions = base_query.filter(
                            ChatMessage.mentioned_bot == True
                        ).count()
                        
                        # 获取聊天基本信息
                        latest_message = base_query.order_by(
                            desc(ChatMessage.created_at)
                        ).first()
                        
                        chat_name = latest_message.chat_name if latest_message else "未知聊天"
                        chat_type = latest_message.chat_type if latest_message else "group"
                        
                        return {
                            "app_id": app_id,
                            "chat_id": chat_id,
                            "chat_name": chat_name,
                            "chat_type": chat_type,
                            "days": days,
                            "total_messages": total_messages,
                            "bot_mentions": bot_mentions,
                            "user_stats": [
                                {
                                    "sender_id": stat.sender_id,
                                    "sender_name": stat.sender_name,
                                    "message_count": stat.message_count
                                } for stat in user_stats
                            ],
                            "message_type_stats": {
                                stat.message_type or "text": stat.count 
                                for stat in type_stats
                            },
                            "start_time": start_time.isoformat(),
                            "end_time": end_time.isoformat()
                        }
                        
                except Exception as e:
                    logger.error(f"获取统计失败: {e}")
                    return {}
            
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _get_stats)
            
        except Exception as e:
            logger.error(f"获取统计异常: {e}")
            return {}
    
    async def get_context_for_reply(
        self, 
        app_id: str, 
        chat_id: str, 
        context_limit: int = 5
    ) -> str:
        """获取用于回复的上下文（排除最新消息避免重复）"""
        try:
            # 取limit+1条消息，然后去掉最后一条（当前消息）
            messages = await self.get_recent_messages(app_id, chat_id, context_limit + 1)
            
            if not messages:
                return ""
            
            # 去掉最后一条消息（当前用户刚发送的消息）
            if len(messages) > 1:
                messages = messages[1:]  # 去掉第一条（最新的）
            else:
                # 如果只有一条消息，说明没有历史上下文
                return ""
            
            # 按时间正序排列（最早的在前）
            messages.reverse()
            
            context_parts = []
            for msg in messages:
                sender_name = msg.get("sender_name", "用户")
                content = msg.get("pure_content", "")
                
                if content.strip():
                    context_parts.append(f"{sender_name}: {content}")
            
            context = "\n".join(context_parts)
            logger.debug(f"生成聊天上下文，排除当前消息后长度: {len(context)}")
            
            return context
            
        except Exception as e:
            logger.error(f"获取上下文异常: {e}")
            return ""
    
    async def get_user_message_history(
        self, 
        app_id: str, 
        user_id: str, 
        limit: int = 20,
        chat_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取用户的消息历史"""
        try:
            if not self.SessionLocal:
                return []
            
            def _get_history():
                try:
                    with self.SessionLocal() as db:
                        query = db.query(ChatMessage).filter(
                            ChatMessage.app_id == app_id,
                            ChatMessage.sender_id == user_id
                        )
                        
                        if chat_type:
                            query = query.filter(ChatMessage.chat_type == chat_type)
                        
                        messages = query.order_by(
                            desc(ChatMessage.created_at)
                        ).limit(limit).all()
                        
                        return [msg.to_dict() for msg in messages]
                        
                except Exception as e:
                    logger.error(f"获取用户历史失败: {e}")
                    return []
            
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _get_history)
            
        except Exception as e:
            logger.error(f"获取用户历史异常: {e}")
            return []
    
    async def search_messages(
        self, 
        app_id: str, 
        keyword: str, 
        chat_id: Optional[str] = None,
        chat_type: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """搜索消息"""
        try:
            if not self.SessionLocal:
                return []
            
            def _search():
                try:
                    with self.SessionLocal() as db:
                        query = db.query(ChatMessage).filter(
                            ChatMessage.app_id == app_id,
                            func.concat(
                                ChatMessage.raw_content, ' ', 
                                ChatMessage.pure_content
                            ).contains(keyword)
                        )
                        
                        if chat_id:
                            query = query.filter(ChatMessage.chat_id == chat_id)
                        
                        if chat_type:
                            query = query.filter(ChatMessage.chat_type == chat_type)
                        
                        messages = query.order_by(
                            desc(ChatMessage.created_at)
                        ).limit(limit).all()
                        
                        return [msg.to_dict() for msg in messages]
                        
                except Exception as e:
                    logger.error(f"搜索消息失败: {e}")
                    return []
            
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _search)
            
        except Exception as e:
            logger.error(f"搜索消息异常: {e}")
            return []


# 创建全局实例
chat_message_service = ChatMessageService() 