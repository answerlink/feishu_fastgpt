import asyncio
from typing import Dict, List, Optional
from collections import defaultdict
from datetime import datetime
from app.core.logger import setup_logger
from app.services.fastgpt_service import FastGPTService

logger = setup_logger("fastgpt_dataset_updater")

class FastGPTDatasetUpdater:
    """FastGPT知识库描述更新工具
    
    用于扫描FastGPT中的所有知识库（dataset），并为它们生成和更新描述，规则为：
    1. 递归遍历所有可访问的文件夹、知识库（dataset）
    2. 根据模式参数决定是否跳过已有描述的知识库或全量覆盖更新
    3. 使用LLM根据知识库中的文件列表生成描述
    """
    
    def __init__(self, app_id: str, skip_existing: bool = True, dry_run: bool = False):
        """初始化描述更新工具
        
        Args:
            app_id: 应用ID，用于获取对应的FastGPT配置
            skip_existing: 如果已有描述就跳过，False表示全量覆盖更新
            dry_run: 是否为预览模式，True表示只分析不更新
        """
        self.app_id = app_id
        self.skip_existing = skip_existing
        self.dry_run = dry_run
        self.fastgpt_service = FastGPTService(app_id)
        self.update_stats = {
            "scanned_folders": 0,
            "scanned_datasets": 0,
            "existing_descriptions": 0,
            "skipped_datasets": 0,
            "updated_datasets": 0,
            "would_update_datasets": 0,  # dry_run模式下预计更新的数量
            "failed_updates": 0,
            "errors": []
        }
    
    async def close(self):
        """关闭FastGPT服务连接"""
        if self.fastgpt_service:
            await self.fastgpt_service.close()
    
    async def update_dataset_descriptions(self) -> Dict:
        """更新知识库描述
        
        Returns:
            Dict: 更新结果统计
        """
        try:
            mode_text = "预览模式" if self.dry_run else "更新模式"
            skip_text = "跳过已有描述" if self.skip_existing else "全量覆盖更新"
            logger.info(f"开始{mode_text}FastGPT知识库描述 - app_id: {self.app_id}, 策略: {skip_text}")
            
            # 检查摘要LLM配置
            app_config = self.fastgpt_service.app_config
            if not all([
                app_config.summary_llm_api_url,
                app_config.summary_llm_api_key,
                app_config.summary_llm_model
            ]):
                error_msg = "摘要LLM配置不完整，无法生成知识库描述"
                logger.error(error_msg)
                return {
                    "code": 400,
                    "message": error_msg,
                    "data": self.update_stats
                }
            
            # 从根目录开始递归遍历
            await self._process_directory(parent_id=None)
            
            # 打印更新统计
            self._log_update_summary()
            
            message = "预览完成" if self.dry_run else "更新完成"
            return {
                "code": 200,
                "message": message,
                "data": self.update_stats
            }
            
        except Exception as e:
            error_msg = f"更新过程中发生异常: {str(e)}"
            logger.error(error_msg)
            self.update_stats["errors"].append(error_msg)
            return {
                "code": 500,
                "message": error_msg,
                "data": self.update_stats
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
                self.update_stats["errors"].append(error_msg)
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
            self.update_stats["scanned_folders"] += len(folders)
            self.update_stats["scanned_datasets"] += len(datasets)
            
            # 处理所有知识库的描述
            for dataset in datasets:
                await self._process_dataset(dataset, level + 1)
            
            # 递归处理子文件夹
            for folder in folders:
                await self._process_directory(folder.get("_id"), level + 1)
                
        except Exception as e:
            error_msg = f"{indent}处理目录异常: {str(e)}"
            logger.error(error_msg)
            self.update_stats["errors"].append(error_msg)
    
    async def _process_dataset(self, dataset: Dict, level: int) -> None:
        """处理单个知识库
        
        Args:
            dataset: 知识库信息
            level: 递归层级，用于日志缩进
        """
        indent = "  " * level
        dataset_id = dataset.get("_id", "")
        dataset_name = dataset.get("name", "")
        current_intro = dataset.get("intro", "")
        
        logger.info(f"{indent}开始处理知识库: {dataset_name} (ID: {dataset_id})")
        
        # 检查是否已有描述
        has_description = bool(current_intro and current_intro.strip())
        if has_description:
            self.update_stats["existing_descriptions"] += 1
            logger.info(f"{indent}当前描述: {current_intro}")
        
        # 根据跳过策略决定是否处理
        if has_description and self.skip_existing:
            self.update_stats["skipped_datasets"] += 1
            logger.info(f"{indent}已有描述且配置为跳过，跳过知识库: {dataset_name}")
            return
        
        try:
            # 获取知识库中的collections
            collections_result = await self.fastgpt_service.get_collection_list(dataset_id)
            
            if collections_result.get("code") != 200:
                error_msg = f"{indent}获取知识库collections失败: {collections_result.get('message')}"
                logger.error(error_msg)
                self.update_stats["errors"].append(error_msg)
                return
            
            collections = collections_result.get("data", {}).get("list", [])
            
            if not collections:
                logger.info(f"{indent}知识库中没有文件，跳过描述生成")
                return
            
            logger.info(f"{indent}知识库中共有 {len(collections)} 个文件")
            
            # 提取文件名
            filenames = [collection.get("name", "") for collection in collections if collection.get("name")]
            
            if not filenames:
                logger.info(f"{indent}没有有效的文件名，跳过描述生成")
                return
            
            # 生成新描述
            await self._generate_and_update_description(dataset_id, dataset_name, filenames, level)
                
        except Exception as e:
            error_msg = f"{indent}处理知识库异常: {dataset_name}, 错误: {str(e)}"
            logger.error(error_msg)
            self.update_stats["errors"].append(error_msg)
    
    async def _generate_and_update_description(self, dataset_id: str, dataset_name: str, filenames: List[str], level: int) -> None:
        """生成并更新知识库描述
        
        Args:
            dataset_id: 知识库ID
            dataset_name: 知识库名称
            filenames: 文件名列表
            level: 递归层级，用于日志缩进
        """
        indent = "  " * level
        
        if self.dry_run:
            # 预览模式，只记录不更新
            self.update_stats["would_update_datasets"] += 1
            file_list = ", ".join(filenames[:5])  # 只显示前5个文件名
            if len(filenames) > 5:
                file_list += f"... 等{len(filenames)}个文件"
            logger.info(f"{indent}🔍 [预览] 将为知识库生成描述: '{dataset_name}' (ID: {dataset_id}, 文件: {file_list})")
            return
        
        logger.info(f"{indent}开始为知识库生成描述: {dataset_name} (文件数量: {len(filenames)})")
        
        try:
            # 调用摘要LLM生成描述
            app_config = self.fastgpt_service.app_config
            description = await self.fastgpt_service.call_summary_llm(
                "请直接给这个文件夹添加一段简洁易懂的描述，让用户可以快速了解这个文件夹的内容。不要做额外解释说明。",
                filenames
            )
            
            if not description:
                logger.warning(f"{indent}LLM未生成有效描述: {dataset_name}")
                self.update_stats["failed_updates"] += 1
                return
            
            # 更新知识库描述
            result = await self.fastgpt_service.update_dataset_description(dataset_id, description)
            
            if result.get("code") == 200:
                self.update_stats["updated_datasets"] += 1
                logger.info(f"{indent}✓ 成功更新知识库描述: '{dataset_name}' -> '{description}'")
            else:
                self.update_stats["failed_updates"] += 1
                error_msg = f"{indent}✗ 更新知识库描述失败: '{dataset_name}', 错误: {result.get('message')}"
                logger.error(error_msg)
                self.update_stats["errors"].append(error_msg)
                
        except Exception as e:
            self.update_stats["failed_updates"] += 1
            error_msg = f"{indent}✗ 生成描述异常: '{dataset_name}', 错误: {str(e)}"
            logger.error(error_msg)
            self.update_stats["errors"].append(error_msg)
    
    def _log_update_summary(self) -> None:
        """打印更新统计摘要"""
        stats = self.update_stats
        mode_text = "预览" if self.dry_run else "更新"
        skip_text = "跳过已有描述" if self.skip_existing else "全量覆盖更新"
        
        logger.info("=" * 60)
        logger.info(f"FastGPT知识库描述{mode_text}统计摘要 ({skip_text})")
        logger.info("=" * 60)
        logger.info(f"扫描的文件夹数量: {stats['scanned_folders']}")
        logger.info(f"扫描的知识库数量: {stats['scanned_datasets']}")
        logger.info(f"已有描述的知识库数量: {stats['existing_descriptions']}")
        logger.info(f"跳过的知识库数量: {stats['skipped_datasets']}")
        
        if self.dry_run:
            logger.info(f"预计更新的知识库数量: {stats['would_update_datasets']}")
        else:
            logger.info(f"成功更新的知识库数量: {stats['updated_datasets']}")
            logger.info(f"更新失败的知识库数量: {stats['failed_updates']}")
        
        logger.info(f"错误数量: {len(stats['errors'])}")
        
        if stats['errors']:
            logger.warning("错误详情:")
            for i, error in enumerate(stats['errors'], 1):
                logger.warning(f"  {i}. {error}")
        
        logger.info("=" * 60) 