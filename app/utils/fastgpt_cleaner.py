import asyncio
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from datetime import datetime
from app.core.logger import setup_logger
from app.services.fastgpt_service import FastGPTService

logger = setup_logger("fastgpt_cleaner")

class FastGPTCleaner:
    """FastGPT知识库清理工具
    
    用于清理FastGPT中重复的collection（知识文件），规则为：
    1. 递归遍历所有可访问的文件夹、知识库（dataset）、文件（collection）
    2. 在一个知识库内发现collection有重名时，保留最新时间的，删除其他的
    """
    
    def __init__(self, app_id: str, dry_run: bool = False):
        """初始化清理工具
        
        Args:
            app_id: 应用ID，用于获取对应的FastGPT配置
            dry_run: 是否为预览模式，True表示只分析不删除
        """
        self.app_id = app_id
        self.dry_run = dry_run
        self.fastgpt_service = FastGPTService(app_id)
        self.cleanup_stats = {
            "scanned_folders": 0,
            "scanned_datasets": 0,
            "scanned_collections": 0,
            "found_duplicates": 0,
            "deleted_collections": 0,
            "would_delete_collections": 0,  # dry_run模式下预计删除的数量
            "errors": []
        }
    
    async def close(self):
        """关闭FastGPT服务连接"""
        if self.fastgpt_service:
            await self.fastgpt_service.close()
    
    async def clean_duplicate_collections(self) -> Dict:
        """清理重复的collections
        
        Returns:
            Dict: 清理结果统计
        """
        try:
            mode_text = "预览模式" if self.dry_run else "清理模式"
            logger.info(f"开始{mode_text}FastGPT重复collections - app_id: {self.app_id}")
            
            # 从根目录开始递归遍历
            await self._process_directory(parent_id=None)
            
            # 打印清理统计
            self._log_cleanup_summary()
            
            message = "预览完成" if self.dry_run else "清理完成"
            return {
                "code": 200,
                "message": message,
                "data": self.cleanup_stats
            }
            
        except Exception as e:
            error_msg = f"清理过程中发生异常: {str(e)}"
            logger.error(error_msg)
            self.cleanup_stats["errors"].append(error_msg)
            return {
                "code": 500,
                "message": error_msg,
                "data": self.cleanup_stats
            }
        finally:
            await self.close()
    
    async def _process_directory(self, parent_id: Optional[str], level: int = 0) -> None:
        """递归处理目录
        
        Args:
            parent_id: 父目录ID，None表示根目录
            level: 递归层级，用于日志缩进
        """
        indent = "  " * level
        logger.info(f"{indent}开始处理目录 - parent_id: {parent_id or 'ROOT'}")
        
        try:
            # 获取当前目录下的所有项目
            result = await self.fastgpt_service.get_dataset_list(parent_id)
            
            if result.get("code") != 200:
                error_msg = f"{indent}获取目录列表失败: {result.get('message')}"
                logger.error(error_msg)
                self.cleanup_stats["errors"].append(error_msg)
                return
            
            items = result.get("data", [])
            if not items:
                logger.info(f"{indent}目录为空")
                return
            
            logger.info(f"{indent}找到 {len(items)} 个项目")
            
            # 分类项目
            folders = []
            datasets = []
            
            for item in items:
                item_type = item.get("type", "")
                item_name = item.get("name", "")
                item_id = item.get("_id", "")
                
                if item_type == "folder":
                    folders.append(item)
                    logger.info(f"{indent}发现文件夹: {item_name} (ID: {item_id})")
                elif item_type == "dataset":
                    datasets.append(item)
                    logger.info(f"{indent}发现知识库: {item_name} (ID: {item_id})")
                else:
                    logger.warning(f"{indent}发现未知类型项目: {item_name} (类型: {item_type})")
            
            # 更新统计
            self.cleanup_stats["scanned_folders"] += len(folders)
            self.cleanup_stats["scanned_datasets"] += len(datasets)
            
            # 处理所有知识库中的collections
            for dataset in datasets:
                await self._process_dataset(dataset, level + 1)
            
            # 递归处理子文件夹
            for folder in folders:
                await self._process_directory(folder.get("_id"), level + 1)
                
        except Exception as e:
            error_msg = f"{indent}处理目录异常: {str(e)}"
            logger.error(error_msg)
            self.cleanup_stats["errors"].append(error_msg)
    
    async def _process_dataset(self, dataset: Dict, level: int) -> None:
        """处理单个知识库
        
        Args:
            dataset: 知识库信息
            level: 递归层级，用于日志缩进
        """
        indent = "  " * level
        dataset_id = dataset.get("_id", "")
        dataset_name = dataset.get("name", "")
        
        logger.info(f"{indent}开始处理知识库: {dataset_name} (ID: {dataset_id})")
        
        try:
            # 获取知识库中的所有collections，分页获取所有数据
            all_collections = await self._get_all_collections(dataset_id)
            
            if not all_collections:
                logger.info(f"{indent}知识库中没有collections")
                return
            
            self.cleanup_stats["scanned_collections"] += len(all_collections)
            logger.info(f"{indent}知识库中共有 {len(all_collections)} 个collections")
            
            # 按名称分组
            collections_by_name = defaultdict(list)
            for collection in all_collections:
                collection_name = collection.get("name", "")
                if collection_name:
                    collections_by_name[collection_name].append(collection)
            
            # 查找重复项
            duplicates_found = 0
            for name, collections in collections_by_name.items():
                if len(collections) > 1:
                    duplicates_found += 1
                    await self._handle_duplicate_collections(name, collections, level + 1)
            
            if duplicates_found > 0:
                self.cleanup_stats["found_duplicates"] += duplicates_found
                logger.info(f"{indent}知识库处理完成，发现 {duplicates_found} 组重复collections")
            else:
                logger.info(f"{indent}知识库处理完成，未发现重复collections")
                
        except Exception as e:
            error_msg = f"{indent}处理知识库异常: {dataset_name}, 错误: {str(e)}"
            logger.error(error_msg)
            self.cleanup_stats["errors"].append(error_msg)
    
    async def _get_all_collections(self, dataset_id: str) -> List[Dict]:
        """获取知识库中的所有collections（分页获取）
        
        Args:
            dataset_id: 知识库ID
            
        Returns:
            List[Dict]: 所有collections列表
        """
        all_collections = []
        offset = 0
        page_size = 30  # FastGPT默认最大30
        
        while True:
            # 修改请求数据结构以支持分页
            data = {
                "offset": offset,
                "pageSize": page_size,
                "datasetId": dataset_id,
                "parentId": "",
                "searchText": ""
            }
            
            result = await self.fastgpt_service._request("POST", "/api/core/dataset/collection/listV2", data)
            
            if result.get("code") != 200:
                logger.error(f"获取collections列表失败: {result.get('message')}")
                break
            
            collections_data = result.get("data", {})
            collections = collections_data.get("list", [])
            total = collections_data.get("total", 0)
            
            if not collections:
                break
            
            all_collections.extend(collections)
            offset += len(collections)
            
            logger.info(f"已获取 {len(all_collections)}/{total} 个collections")
            
            # 如果获取的数量少于页面大小，说明已经获取完毕
            if len(collections) < page_size:
                break
        
        return all_collections
    
    async def _handle_duplicate_collections(self, name: str, collections: List[Dict], level: int) -> None:
        """处理重复的collections
        
        Args:
            name: collection名称
            collections: 重复的collections列表
            level: 递归层级，用于日志缩进
        """
        indent = "  " * level
        logger.warning(f"{indent}发现重复collections: '{name}' (共 {len(collections)} 个)")
        
        # 按创建时间排序，保留最新的
        sorted_collections = sorted(
            collections,
            key=lambda x: self._parse_time(x.get("createTime", "")),
            reverse=True
        )
        
        # 保留最新的
        keep_collection = sorted_collections[0]
        delete_collections = sorted_collections[1:]
        
        keep_time = keep_collection.get("createTime", "")
        keep_id = keep_collection.get("_id", "")
        
        logger.info(f"{indent}保留最新的collection: '{name}' (ID: {keep_id}, 创建时间: {keep_time})")
        
        # 删除其他的
        for collection in delete_collections:
            await self._delete_collection_safe(collection, level)
    
    def _parse_time(self, time_str: str) -> datetime:
        """解析时间字符串
        
        Args:
            time_str: 时间字符串
            
        Returns:
            datetime: 解析后的时间对象
        """
        try:
            # 尝试解析ISO格式时间
            if time_str:
                # 移除时区信息后解析
                if 'T' in time_str:
                    time_part = time_str.split('+')[0].split('Z')[0]
                    return datetime.fromisoformat(time_part)
                else:
                    return datetime.fromisoformat(time_str)
        except Exception as e:
            logger.warning(f"解析时间失败: {time_str}, 错误: {str(e)}")
        
        # 如果解析失败，返回最小时间
        return datetime.min
    
    async def _delete_collection_safe(self, collection: Dict, level: int) -> None:
        """安全删除collection
        
        Args:
            collection: 要删除的collection信息
            level: 递归层级，用于日志缩进
        """
        indent = "  " * level
        collection_id = collection.get("_id", "")
        collection_name = collection.get("name", "")
        create_time = collection.get("createTime", "")
        
        if self.dry_run:
            # 预览模式，只记录不删除
            self.cleanup_stats["would_delete_collections"] += 1
            logger.info(f"{indent}🔍 [预览] 将删除重复collection: '{collection_name}' (ID: {collection_id}, 创建时间: {create_time})")
            return
        
        logger.info(f"{indent}准备删除重复collection: '{collection_name}' (ID: {collection_id}, 创建时间: {create_time})")
        
        try:
            result = await self.fastgpt_service.delete_collection(collection_id)
            
            if result.get("code") == 200:
                self.cleanup_stats["deleted_collections"] += 1
                logger.info(f"{indent}✓ 成功删除重复collection: '{collection_name}' (ID: {collection_id})")
            else:
                error_msg = f"{indent}✗ 删除collection失败: '{collection_name}', 错误: {result.get('msg')}"
                logger.error(error_msg)
                self.cleanup_stats["errors"].append(error_msg)
                
        except Exception as e:
            error_msg = f"{indent}✗ 删除collection异常: '{collection_name}', 错误: {str(e)}"
            logger.error(error_msg)
            self.cleanup_stats["errors"].append(error_msg)
    
    def _log_cleanup_summary(self) -> None:
        """打印清理统计摘要"""
        stats = self.cleanup_stats
        mode_text = "预览" if self.dry_run else "清理"
        
        logger.info("=" * 60)
        logger.info(f"FastGPT {mode_text}统计摘要")
        logger.info("=" * 60)
        logger.info(f"扫描的文件夹数量: {stats['scanned_folders']}")
        logger.info(f"扫描的知识库数量: {stats['scanned_datasets']}")
        logger.info(f"扫描的collection数量: {stats['scanned_collections']}")
        logger.info(f"发现重复组数: {stats['found_duplicates']}")
        
        if self.dry_run:
            logger.info(f"预计删除的collection数量: {stats['would_delete_collections']}")
        else:
            logger.info(f"实际删除的collection数量: {stats['deleted_collections']}")
        
        logger.info(f"错误数量: {len(stats['errors'])}")
        
        if stats['errors']:
            logger.warning("错误详情:")
            for i, error in enumerate(stats['errors'], 1):
                logger.warning(f"  {i}. {error}")
        
        logger.info("=" * 60) 