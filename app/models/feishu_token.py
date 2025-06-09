from datetime import datetime
from sqlalchemy import String, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class FeishuToken(Base):
    """飞书Token模型
    
    用于存储和管理飞书应用的访问令牌(tenant_access_token)。
    系统使用这些令牌访问飞书开放平台API。每个应用有一个对应的记录。
    
    Attributes:
        id: 自增主键
        app_id: 应用ID，关联到飞书应用
        tenant_access_token: 租户访问令牌，用于API调用
        expire_time: 令牌过期时间
        created_at: 记录创建时间
        updated_at: 记录更新时间
    """
    __tablename__ = "feishu_token"
    __table_args__ = {"comment": "飞书应用访问令牌表"}
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True, comment="自增主键ID")
    app_id: Mapped[str] = mapped_column(String(50), index=True, nullable=False, comment="应用ID")
    tenant_access_token: Mapped[str] = mapped_column(String(100), nullable=False, comment="租户访问令牌")
    expire_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="令牌过期时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="记录创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="记录更新时间") 