from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class UserSearchPreference(Base):
    """用户搜索偏好模型
    
    用于存储和管理用户在各个飞书应用中的搜索模式偏好。
    每个用户在每个应用中有一个全局的搜索偏好配置。
    
    Attributes:
        id: 自增主键
        app_id: 应用ID，关联到飞书应用
        user_id: 用户ID（飞书user_id）
        dataset_search: 是否启用知识库搜索
        web_search: 是否启用联网搜索
        search_mode: 搜索模式描述（dataset/web/all）
        created_at: 记录创建时间
        updated_at: 记录更新时间
    """
    __tablename__ = "user_search_preference"
    __table_args__ = (
        UniqueConstraint('app_id', 'user_id', name='uk_app_user'),
        {"comment": "用户搜索偏好表"}
    )
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True, comment="自增主键ID")
    app_id: Mapped[str] = mapped_column(String(50), index=True, nullable=False, comment="应用ID")
    user_id: Mapped[str] = mapped_column(String(50), index=True, nullable=False, comment="用户ID")
    dataset_search: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, comment="是否启用知识库搜索")
    web_search: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="是否启用联网搜索")
    search_mode: Mapped[str] = mapped_column(String(20), nullable=False, comment="搜索模式(dataset/web/all)")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="记录创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="记录更新时间") 