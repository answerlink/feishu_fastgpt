from sqlalchemy import Column, String, Text, DateTime, Integer, Boolean, JSON
from datetime import datetime
from app.db.base import Base

class GroupChatMessage(Base):
    """群聊消息记录表"""
    __tablename__ = "group_chat_messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True, comment="自增ID")
    app_id = Column(String(100), nullable=False, index=True, comment="飞书应用ID")
    message_id = Column(String(100), nullable=False, comment="飞书消息ID")
    chat_id = Column(String(100), nullable=False, index=True, comment="群聊ID")
    chat_name = Column(String(200), nullable=False, comment="群聊名称")
    sender_id = Column(String(100), nullable=False, comment="发送者ID")
    sender_name = Column(String(200), nullable=False, comment="发送者姓名")
    raw_content = Column(Text, nullable=False, comment="原始消息内容（替换@后）")
    pure_content = Column(Text, nullable=False, comment="纯净消息内容（去除@）")
    message_type = Column(String(50), default="text", comment="消息类型")
    mention_users = Column(JSON, nullable=True, comment="@的用户列表")
    mentioned_bot = Column(Boolean, default=False, comment="是否@了机器人")
    feishu_create_time = Column(String(50), nullable=True, comment="飞书消息创建时间")
    created_at = Column(DateTime, default=datetime.utcnow, comment="记录创建时间")
    
    def to_dict(self):
        """转换为字典格式"""
        return {
            "id": self.id,
            "app_id": self.app_id,
            "message_id": self.message_id,
            "chat_id": self.chat_id,
            "chat_name": self.chat_name,
            "sender_id": self.sender_id,
            "sender_name": self.sender_name,
            "raw_content": self.raw_content,
            "pure_content": self.pure_content,
            "message_type": self.message_type,
            "mention_users": self.mention_users or [],
            "mentioned_bot": self.mentioned_bot,
            "feishu_create_time": self.feishu_create_time,
            "created_at": self.created_at.isoformat() if self.created_at else None
        } 