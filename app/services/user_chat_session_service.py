from datetime import datetime
from typing import Optional, Tuple
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.models.user_chat_session import UserChatSession
from app.core.logger import logger
import time

class UserChatSessionService:
    """用户聊天会话服务"""
    
    def __init__(self):
        # 创建同步数据库引擎
        self.engine = create_engine(
            settings.SQLALCHEMY_DATABASE_URI.replace("mysql+aiomysql://", "mysql+pymysql://")
        )
        self.Session = sessionmaker(bind=self.engine)
    
    def create_new_chat_session(self, app_id: str, user_id: str, open_id: str = None, app_name: str = None) -> str:
        """创建新的聊天会话
        
        Args:
            app_id: 应用ID
            user_id: 用户ID
            open_id: 用户Open ID
            app_name: 应用名称（用于生成chat_id）
        
        Returns:
            str: 新生成的chat_id
        """
        try:
            # 生成新的chat_id，格式：feishu_{app_name}_user_{user_id}_{timestamp}
            timestamp = int(time.time())  # 秒级时间戳
            if app_name:
                chat_id = f"feishu_{app_name}_user_{user_id}_{timestamp}"
            else:
                chat_id = f"feishu_{app_id}_user_{user_id}_{timestamp}"
            
            session_start_time = datetime.utcnow()
            
            with self.Session() as session:
                # 查询是否已存在该用户的会话记录
                query = select(UserChatSession).where(
                    UserChatSession.app_id == app_id,
                    UserChatSession.user_id == user_id
                )
                existing_session = session.execute(query).scalar_one_or_none()
                
                if existing_session:
                    # 更新现有记录
                    existing_session.current_chat_id = chat_id
                    existing_session.session_start_time = session_start_time
                    existing_session.open_id = open_id or existing_session.open_id
                    existing_session.updated_at = datetime.utcnow()
                    
                    logger.info(f"更新用户聊天会话: app_id={app_id}, user_id={user_id}, new_chat_id={chat_id}")
                else:
                    # 创建新记录
                    new_session = UserChatSession(
                        app_id=app_id,
                        user_id=user_id,
                        open_id=open_id,
                        current_chat_id=chat_id,
                        session_start_time=session_start_time
                    )
                    session.add(new_session)
                    
                    logger.info(f"创建新用户聊天会话: app_id={app_id}, user_id={user_id}, chat_id={chat_id}")
                
                session.commit()
                return chat_id
                
        except Exception as e:
            logger.error(f"创建聊天会话失败: {str(e)}")
            # 如果数据库操作失败，返回传统格式的chat_id作为fallback
            if app_name:
                return f"feishu_{app_name}_user_{user_id}"
            else:
                return f"feishu_{app_id}_user_{user_id}"
    
    def get_current_chat_id(self, app_id: str, user_id: str, app_name: str = None) -> str:
        """获取用户当前的活跃chat_id，如果跨天则自动重置
        
        Args:
            app_id: 应用ID
            user_id: 用户ID
            app_name: 应用名称（用于生成fallback chat_id）
        
        Returns:
            str: 当前活跃的chat_id
        """
        try:
            with self.Session() as session:
                # 查询用户的当前会话
                query = select(UserChatSession).where(
                    UserChatSession.app_id == app_id,
                    UserChatSession.user_id == user_id
                )
                user_session = session.execute(query).scalar_one_or_none()
                
                if user_session and user_session.current_chat_id:
                    # 检查是否跨天，如果跨天则自动重置chatId
                    current_date = datetime.utcnow().date()
                    session_date = user_session.session_start_time.date()
                    
                    if current_date != session_date:
                        # 跨天了，自动生成新的chatId
                        logger.info(f"检测到跨天，自动重置chatId: app_id={app_id}, user_id={user_id}, 原日期={session_date}, 当前日期={current_date}")
                        
                        # 生成新的chat_id
                        timestamp = int(time.time())
                        if app_name:
                            new_chat_id = f"feishu_{app_name}_user_{user_id}_{timestamp}"
                        else:
                            new_chat_id = f"feishu_{app_id}_user_{user_id}_{timestamp}"
                        
                        # 更新会话记录
                        user_session.current_chat_id = new_chat_id
                        user_session.session_start_time = datetime.utcnow()
                        user_session.updated_at = datetime.utcnow()
                        session.commit()
                        
                        logger.info(f"已自动重置chatId: {new_chat_id}")
                        return new_chat_id
                    else:
                        # 同一天，返回现有的chatId
                        logger.debug(f"找到用户会话: app_id={app_id}, user_id={user_id}, chat_id={user_session.current_chat_id}")
                        return user_session.current_chat_id
                else:
                    # 如果没有找到会话记录，返回传统格式的chat_id
                    if app_name:
                        fallback_chat_id = f"feishu_{app_name}_user_{user_id}"
                    else:
                        fallback_chat_id = f"feishu_{app_id}_user_{user_id}"
                    
                    logger.info(f"未找到用户会话记录，使用fallback chat_id: {fallback_chat_id}")
                    return fallback_chat_id
                    
        except Exception as e:
            logger.error(f"获取聊天会话失败: {str(e)}")
            # 如果数据库操作失败，返回传统格式的chat_id作为fallback
            if app_name:
                return f"feishu_{app_name}_user_{user_id}"
            else:
                return f"feishu_{app_id}_user_{user_id}"
    
    def get_session_info(self, app_id: str, user_id: str) -> Optional[Tuple[str, datetime]]:
        """获取用户会话的详细信息
        
        Args:
            app_id: 应用ID
            user_id: 用户ID
        
        Returns:
            Optional[Tuple[str, datetime]]: (chat_id, session_start_time) 或 None
        """
        try:
            with self.Session() as session:
                query = select(UserChatSession).where(
                    UserChatSession.app_id == app_id,
                    UserChatSession.user_id == user_id
                )
                user_session = session.execute(query).scalar_one_or_none()
                
                if user_session:
                    return user_session.current_chat_id, user_session.session_start_time
                else:
                    return None
                    
        except Exception as e:
            logger.error(f"获取会话信息失败: {str(e)}")
            return None 