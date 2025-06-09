from sqlalchemy import Column, Integer, String, DateTime, SmallInteger, func, UniqueConstraint
from app.db.base import Base

class SpaceSubscription(Base):
    """知识空间订阅模型
    
    用于记录已订阅的知识空间信息，包括空间基本信息、订阅状态和同步时间等。
    每个记录代表一个应用订阅了一个特定的飞书知识空间。
    
    Attributes:
        id: 自增主键
        app_id: 应用ID，关联到飞书应用
        space_id: 知识空间ID，飞书知识空间的唯一标识
        space_name: 知识空间名称
        space_type: 空间类型，如"知识库"、"项目空间"等
        status: 订阅状态，1表示已订阅，0表示已取消
        doc_count: 空间内已订阅的文档数量
        last_sync_time: 最后同步时间
        created_at: 记录创建时间
        updated_at: 记录更新时间
    """
    __tablename__ = "space_subscription"
    
    id = Column(Integer, primary_key=True, index=True, comment="自增主键ID")
    app_id = Column(String(50), nullable=False, comment="应用ID")
    space_id = Column(String(100), nullable=False, comment="知识空间ID，空间唯一标识")
    space_name = Column(String(255), comment="知识空间名称")
    space_type = Column(String(50), comment="空间类型，如'知识库'、'项目空间'等")
    status = Column(SmallInteger, default=1, comment="订阅状态，1: 已订阅, 0: 已取消")
    doc_count = Column(Integer, default=0, comment="空间内已订阅的文档数量")
    last_sync_time = Column(DateTime, comment="最后同步时间")
    created_at = Column(DateTime, default=func.now(), comment="记录创建时间")
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), comment="记录更新时间")
    
    __table_args__ = (
        UniqueConstraint('app_id', 'space_id', name='uix_space_subscription_app_space'),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci", "comment": "知识空间订阅表"},
    ) 