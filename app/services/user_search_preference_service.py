from datetime import datetime
from typing import Optional, Tuple
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.models.user_search_preference import UserSearchPreference
from app.core.logger import logger

class UserSearchPreferenceService:
    """用户搜索偏好服务"""
    
    def __init__(self):
        # 创建同步数据库引擎
        self.engine = create_engine(
            settings.SQLALCHEMY_DATABASE_URI.replace("mysql+aiomysql://", "mysql+pymysql://")
        )
        self.Session = sessionmaker(bind=self.engine)
    
    def set_search_preference(self, app_id: str, user_id: str, search_mode: str) -> bool:
        """设置用户的搜索偏好
        
        Args:
            app_id: 应用ID
            user_id: 用户ID
            search_mode: 搜索模式 (dataset/web/all)
        
        Returns:
            bool: 是否设置成功
        """
        try:
            # 根据搜索模式确定搜索选项
            dataset_search = False
            web_search = False
            
            if search_mode == "dataset":
                dataset_search = True
                web_search = False
            elif search_mode == "web":
                dataset_search = False
                web_search = True
            elif search_mode == "all":
                dataset_search = True
                web_search = True
            else:
                logger.error(f"未知的搜索模式: {search_mode}")
                return False
            
            with self.Session() as session:
                # 查询是否已存在该记录
                query = select(UserSearchPreference).where(
                    UserSearchPreference.app_id == app_id,
                    UserSearchPreference.user_id == user_id
                )
                existing_preference = session.execute(query).scalar_one_or_none()
                
                if existing_preference:
                    # 更新现有记录
                    existing_preference.dataset_search = dataset_search
                    existing_preference.web_search = web_search
                    existing_preference.search_mode = search_mode
                    existing_preference.updated_at = datetime.utcnow()
                    
                    logger.info(f"更新搜索偏好: app_id={app_id}, user_id={user_id}, mode={search_mode}")
                else:
                    # 创建新记录
                    new_preference = UserSearchPreference(
                        app_id=app_id,
                        user_id=user_id,
                        dataset_search=dataset_search,
                        web_search=web_search,
                        search_mode=search_mode
                    )
                    session.add(new_preference)
                    
                    logger.info(f"创建搜索偏好: app_id={app_id}, user_id={user_id}, mode={search_mode}")
                
                session.commit()
                return True
                
        except Exception as e:
            logger.error(f"设置搜索偏好失败: {str(e)}")
            return False
    
    def set_model_preference(self, app_id: str, user_id: str, model_id: str) -> bool:
        """设置用户的模型偏好
        
        Args:
            app_id: 应用ID
            user_id: 用户ID
            model_id: 模型ID
        
        Returns:
            bool: 是否设置成功
        """
        try:
            with self.Session() as session:
                # 查询是否已存在该记录
                query = select(UserSearchPreference).where(
                    UserSearchPreference.app_id == app_id,
                    UserSearchPreference.user_id == user_id
                )
                existing_preference = session.execute(query).scalar_one_or_none()
                
                if existing_preference:
                    # 更新现有记录
                    existing_preference.model_id = model_id
                    existing_preference.updated_at = datetime.utcnow()
                    
                    logger.info(f"更新模型偏好: app_id={app_id}, user_id={user_id}, model_id={model_id}")
                else:
                    # 创建新记录，使用默认搜索偏好
                    new_preference = UserSearchPreference(
                        app_id=app_id,
                        user_id=user_id,
                        dataset_search=True,  # 默认启用知识库搜索
                        web_search=False,    # 默认不启用联网搜索
                        search_mode="dataset",  # 默认搜索模式
                        model_id=model_id
                    )
                    session.add(new_preference)
                    
                    logger.info(f"创建用户偏好记录，包含模型偏好: app_id={app_id}, user_id={user_id}, model_id={model_id}")
                
                session.commit()
                return True
                
        except Exception as e:
            logger.error(f"设置模型偏好失败: {str(e)}")
            return False
    
    def get_search_preference(self, app_id: str, user_id: str) -> Tuple[bool, bool, Optional[str]]:
        """获取用户的搜索偏好和模型偏好
        
        Args:
            app_id: 应用ID
            user_id: 用户ID
        
        Returns:
            Tuple[bool, bool, Optional[str]]: (dataset_search, web_search, model_id)
        """
        try:
            with self.Session() as session:
                # 查询用户的偏好设置
                query = select(UserSearchPreference).where(
                    UserSearchPreference.app_id == app_id,
                    UserSearchPreference.user_id == user_id
                )
                preference = session.execute(query).scalar_one_or_none()
                
                if preference:
                    logger.debug(f"找到用户偏好: app_id={app_id}, user_id={user_id}, "
                               f"dataset={preference.dataset_search}, web={preference.web_search}, model_id={preference.model_id}")
                    return preference.dataset_search, preference.web_search, preference.model_id
                else:
                    # 如果没有找到偏好记录，返回默认值
                    logger.info(f"未找到用户偏好记录，使用默认值: dataset=True, web=False, model_id=None")
                    return True, False, None
                    
        except Exception as e:
            logger.error(f"获取用户偏好失败: {str(e)}")
            # 如果数据库操作失败，返回默认值
            return True, False, None

    def clear_model_preference(self, app_id: str, user_id: str) -> bool:
        """清除用户的模型偏好（将 model_id 置为空）
        
        Args:
            app_id: 应用ID
            user_id: 用户ID
        
        Returns:
            bool: 是否清除成功（无记录也视为成功）
        """
        try:
            with self.Session() as session:
                query = select(UserSearchPreference).where(
                    UserSearchPreference.app_id == app_id,
                    UserSearchPreference.user_id == user_id
                )
                preference = session.execute(query).scalar_one_or_none()
                if preference:
                    preference.model_id = None
                    preference.updated_at = datetime.utcnow()
                    session.commit()
                    logger.info(f"清除模型偏好: app_id={app_id}, user_id={user_id}")
                else:
                    # 若不存在记录，不视为错误
                    logger.info(f"未找到用户偏好记录，无需清除模型偏好: app_id={app_id}, user_id={user_id}")
            return True
        except Exception as e:
            logger.error(f"清除模型偏好失败: {str(e)}")
            return False
    
    def get_search_mode_info(self, app_id: str, user_id: str) -> Optional[dict]:
        """获取搜索模式的详细信息
        
        Args:
            app_id: 应用ID
            user_id: 用户ID
        
        Returns:
            Optional[dict]: 搜索偏好详细信息
        """
        try:
            with self.Session() as session:
                query = select(UserSearchPreference).where(
                    UserSearchPreference.app_id == app_id,
                    UserSearchPreference.user_id == user_id
                )
                preference = session.execute(query).scalar_one_or_none()
                
                if preference:
                    return {
                        "search_mode": preference.search_mode,
                        "dataset_search": preference.dataset_search,
                        "web_search": preference.web_search,
                        "model_id": preference.model_id,
                        "created_at": preference.created_at,
                        "updated_at": preference.updated_at
                    }
                else:
                    return None
                    
        except Exception as e:
            logger.error(f"获取搜索模式信息失败: {str(e)}")
            return None
    
    def get_search_mode_display_name(self, search_mode: str) -> str:
        """获取搜索模式的显示名称
        
        Args:
            search_mode: 搜索模式代码
            
        Returns:
            str: 搜索模式显示名称
        """
        mode_names = {
            "dataset": "📚 知识库搜索",
            "web": "🌐 联网搜索", 
            "all": "♾️ 知识库+联网搜索"
        }
        return mode_names.get(search_mode, "🔍 默认搜索")
    
    def get_model_display_name(self, model_id: str) -> str:
        """获取模型的显示名称
        
        Args:
            model_id: 模型ID
            
        Returns:
            str: 模型显示名称
        """
        if not model_id:
            return "🤖 默认模型"
        
        # 这里可以根据实际的模型ID映射显示名称
        # 目前先简单处理，显示模型ID
        return f"🤖 {model_id}" 