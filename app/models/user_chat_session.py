from datetime import datetime
from sqlalchemy import String, DateTime, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class UserChatSession(Base):
    """用户聊天会话模型
    
    用于存储和管理用户在各个飞书应用中的活跃聊天会话ID。
    当用户触发bot_new_chat事件时，会创建或更新对应的会话记录。
    
    Attributes:
        id: 自增主键
        app_id: 应用ID，关联到飞书应用
        user_id: 用户ID（飞书user_id）
        open_id: 用户Open ID（飞书open_id）
        current_chat_id: 当前活跃的聊天会话ID
        session_start_time: 会话开始时间（触发bot_new_chat的时间）
        created_at: 记录创建时间
        updated_at: 记录更新时间
    """
    __tablename__ = "user_chat_session"
    __table_args__ = (
        UniqueConstraint('app_id', 'user_id', name='uk_app_user'),
        {"comment": "用户聊天会话表"}
    )
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True, comment="自增主键ID")
    app_id: Mapped[str] = mapped_column(String(50), index=True, nullable=False, comment="应用ID")
    user_id: Mapped[str] = mapped_column(String(50), index=True, nullable=False, comment="用户ID")
    open_id: Mapped[str] = mapped_column(String(100), nullable=True, comment="用户Open ID")
    current_chat_id: Mapped[str] = mapped_column(String(200), nullable=False, comment="当前活跃的聊天会话ID")
    session_start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="会话开始时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="记录创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="记录更新时间") 