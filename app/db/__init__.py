# 只导入Base基类，避免循环导入
from app.db.base import Base

__all__ = ["Base"] 