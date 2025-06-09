import asyncio
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, func, update, or_, and_, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import AsyncSessionLocal
from app.models.space_subscription import SpaceSubscription
from app.models.doc_subscription import DocSubscription
from app.services.feishu_service import FeishuService
from app.core.config import settings
from app.core.logger import setup_logger
from app.services.fastgpt_service import FastGPTService
from app.api.v1.endpoints.document import SyncDocToAIChatRequest, sync_document_to_aichat

logger = setup_logger("subscription_scheduler")

class SubscriptionScheduler:
    """订阅定时任务调度器
    
    定期扫描数据库中的订阅空间，执行文档同步和订阅更新操作
    """
    
    _instance = None
    _scheduler = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SubscriptionScheduler, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self._scheduler = AsyncIOScheduler()
        self._running = False
    
    def start(self):
        """启动调度器"""
        if self._running:
            logger.info("调度器已经在运行中")
            return
            
        # 添加定时任务
        self._scheduler.add_job(
            self._scan_subscriptions,
            trigger=IntervalTrigger(minutes=3),  # 每3分钟执行一次
            id='scan_subscriptions',
            replace_existing=True
        )
        
        # 添加AI知识库更新定时任务
        self._scheduler.add_job(
            self._update_aichat_knowledge_base,
            trigger=IntervalTrigger(minutes=1),  # 每1分钟执行一次
            id='update_aichat_knowledge_base',
            replace_existing=True
        )
        
        # 添加FastGPT文件状态检查定时任务（二次校验）
        self._scheduler.add_job(
            self._check_fastgpt_file_status,
            trigger=IntervalTrigger(minutes=30),  # 每30分钟执行一次
            id='check_fastgpt_file_status',
            replace_existing=True
        )
        
        # 启动调度器
        self._scheduler.start()
        self._running = True
        logger.info("订阅定时任务调度器已启动，将扫描订阅状态，检查AI知识库更新，检查FastGPT文件状态")
    
    def shutdown(self):
        """关闭调度器"""
        if not self._running:
            return
            
        self._scheduler.shutdown()
        self._running = False
        logger.info("订阅定时任务调度器已关闭")
    
    async def _scan_subscriptions(self):
        """扫描所有订阅的知识空间，更新文档订阅状态"""
        logger.info(f"开始扫描订阅空间和文档 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        async with AsyncSessionLocal() as db:
            try:
                # 查询所有已订阅的空间
                query = await db.execute(
                    select(SpaceSubscription)
                    .where(SpaceSubscription.status == 1)
                    .order_by(SpaceSubscription.last_sync_time)  # 优先处理最久未同步的空间
                )
                
                spaces = query.scalars().all()
                
                if not spaces:
                    logger.info("没有找到已订阅的知识空间")
                    return
                
                logger.info(f"找到 {len(spaces)} 个已订阅的知识空间")
                
                # 创建服务实例
                feishu_service = FeishuService(db)
                
                # 遍历每个空间
                for space in spaces:
                    await self._process_space(db, feishu_service, space)
                    
                logger.info(f"订阅空间扫描完成 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
            except Exception as e:
                logger.error(f"扫描订阅空间时发生错误: {str(e)}")
    
    async def _update_aichat_knowledge_base(self):
        """检查并更新AI知识库
        
        扫描已订阅的文档，查找符合以下条件的文档：
        1. AI知识库更新时间 < 文档最后编辑时间
        2. 当前时间 - 文档最后编辑时间 > 60秒
        
        对符合条件的文档执行AI知识库更新
        """
        logger.info(f"开始检查AI知识库更新 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        async with AsyncSessionLocal() as db:
            try:
                current_time = datetime.now()
                edit_time_threshold = current_time - timedelta(seconds=60)
                
                # 查询需要更新的文档
                query = await db.execute(
                    select(DocSubscription)
                    .where(
                        DocSubscription.status == 1,  # 已订阅的文档
                        DocSubscription.obj_edit_time < edit_time_threshold,  # 编辑时间早于阈值（确保文档已稳定）
                        # aichat_update_time IS NULL OR obj_edit_time > aichat_update_time
                        or_(
                            DocSubscription.aichat_update_time == None,
                            DocSubscription.obj_edit_time > DocSubscription.aichat_update_time
                        ),
                        # file_type='docx' OR title REGEXP "\\.(docx|pdf|xlsx)$"
                        # 使用MySQL的REGEXP函数进行正则匹配
                        or_(
                            DocSubscription.file_type == 'docx',
                            text("title REGEXP '\\\\.(docx|pdf|xlsx)$'")
                        )
                    )
                    .order_by(DocSubscription.obj_edit_time.desc())  # 按文档编辑时间降序排列
                    # .limit(10)  # 每次最多处理10个文档，如果需要可以取消注释
                )
                
                docs = query.scalars().all()
                
                if not docs:
                    logger.info("没有找到需要更新AI知识库的文档")
                    return
                
                logger.info(f"找到 {len(docs)} 个需要更新AI知识库的文档")
                
                # 创建服务实例
                feishu_service = FeishuService(db)
                
                # 遍历每个文档进行更新
                for doc in docs:
                    try:
                        # 记录文档信息
                        doc_info = f"文档：{doc.title or '未命名'} (token: {doc.file_token})"
                        edit_time = doc.obj_edit_time.strftime('%Y-%m-%d %H:%M:%S') if doc.obj_edit_time else "未知"
                        aichat_time = doc.aichat_update_time.strftime('%Y-%m-%d %H:%M:%S') if doc.aichat_update_time else "未更新"
                        
                        logger.info(f"正在更新AI知识库 - {doc_info}")
                        logger.info(f"文档编辑时间: {edit_time}, AI知识库更新时间: {aichat_time}")
                        
                        # 使用新的同步接口
                        # 创建同步请求
                        sync_request = SyncDocToAIChatRequest(
                            app_id=doc.app_id,
                            file_token=doc.file_token,
                            file_type=doc.file_type
                        )
                        
                        # 调用同步接口
                        try:
                            # 直接调用同步方法，而不是通过API路由
                            result = await sync_document_to_aichat(sync_request, feishu_service)
                            
                            if result.get("code") == 0:
                                logger.info(f"成功更新AI知识库 - {doc_info}")
                            else:
                                error_msg = result.get('msg', '未知错误')
                                
                                # 检查是否是文件不存在错误（404）
                                if "文件不存在或已被删除" in error_msg or "404" in error_msg:
                                    logger.warning(f"文件不存在，标记文档为不可用 - {doc_info}: {error_msg}")
                                    
                                    # 对于404错误，更新aichat_update_time以避免重复尝试
                                    # 但不标记为成功同步，collection_id保持为空
                                    await db.execute(
                                        update(DocSubscription)
                                        .where(
                                            DocSubscription.app_id == doc.app_id,
                                            DocSubscription.file_token == doc.file_token
                                        )
                                        .values(aichat_update_time=datetime.now())
                                    )
                                    await db.commit()
                                    logger.info(f"已更新时间戳，避免重复尝试同步不存在的文件 - {doc_info}")
                                elif "无权限访问" in error_msg or "403" in error_msg:
                                    logger.warning(f"无权限访问文件，跳过此次同步 - {doc_info}: {error_msg}")
                                    # 对于权限问题，不更新时间戳，稍后可能会重新获得权限
                                elif "认证失败" in error_msg or "401" in error_msg:
                                    logger.warning(f"认证失败，稍后重试 - {doc_info}: {error_msg}")
                                    # 对于认证问题，不更新时间戳，可能是临时的token问题
                                else:
                                    logger.error(f"更新AI知识库失败 - {doc_info}: {error_msg}")
                        except Exception as e:
                            logger.error(f"调用同步接口异常 - {doc_info}: {str(e)}")
                        
                    except Exception as e:
                        logger.error(f"更新文档AI知识库失败: {doc.file_token}, 错误: {str(e)}")
                
                logger.info(f"AI知识库更新检查完成 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
            except Exception as e:
                logger.error(f"AI知识库更新过程中发生错误: {str(e)}")
    
    async def _check_fastgpt_file_status(self):
        """检查FastGPT平台上的文件状态
        
        主动扫描doc_subscription表，查询FastGPT接口，看是否对应目录真有对应的文件，
        这样即使同步到FastGPT平台失败了，后面也能自动修复。
        """
        logger.info(f"开始检查FastGPT文件状态 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        async with AsyncSessionLocal() as db:
            try:
                # 查询所有已订阅的文档（包括collection_id为空的，表示之前同步失败）
                query = await db.execute(
                    select(DocSubscription)
                    .where(
                        DocSubscription.status == 1  # 已订阅的文档
                    )
                )
                
                docs = query.scalars().all()
                
                if not docs:
                    logger.info("没有找到需要检查FastGPT状态的文档")
                    return
                
                logger.info(f"找到 {len(docs)} 个需要检查FastGPT状态的文档")
                
                # 按应用ID分组处理，避免重复创建FastGPT服务实例
                app_docs = {}
                for doc in docs:
                    if doc.app_id not in app_docs:
                        app_docs[doc.app_id] = []
                    app_docs[doc.app_id].append(doc)
                
                # 创建飞书服务实例
                feishu_service = FeishuService(db)
                
                # 按应用处理文档
                for app_id, app_doc_list in app_docs.items():
                    fastgpt_service = None
                    try:
                        # 创建FastGPT服务实例
                        fastgpt_service = FastGPTService(app_id)
                        
                        for doc in app_doc_list:
                            try:
                                # 记录文档信息
                                doc_info = f"文档：{doc.title or '未命名'} (token: {doc.file_token}, collection_id: {doc.collection_id})"
                                
                                logger.info(f"正在检查FastGPT文件状态 - {doc_info}")
                                
                                # 判断是否需要重新同步：
                                # 1. collection_id为空或None（之前同步失败）
                                # 2. 检查成功但文档不存在 (exists=False)
                                # 3. 检查失败且错误信息包含collection_not_exist
                                should_resync = False
                                
                                # 如果collection_id为空，直接标记为需要重新同步
                                if not doc.collection_id or doc.collection_id.strip() == "":
                                    should_resync = True
                                    logger.warning(f"FastGPT文件collection_id为空，准备重新同步 - {doc_info}")
                                else:
                                    # 检查文档在FastGPT中是否存在
                                    check_result = await fastgpt_service.check_collection_exists(doc.collection_id)
                                    
                                    if check_result.get("code") == 0:
                                        if check_result.get("exists"):
                                            # 获取datasetId信息并记录
                                            dataset_info = check_result.get("data", {})
                                            dataset_id = dataset_info.get("datasetId", {}).get("_id") if isinstance(dataset_info.get("datasetId"), dict) else dataset_info.get("datasetId")
                                            logger.info(f"FastGPT文件状态正常 - {doc_info}, datasetId: {dataset_id}")
                                        else:
                                            # 文档在FastGPT中不存在，需要重新同步
                                            should_resync = True
                                            logger.warning(f"FastGPT文件不存在，准备重新同步 - {doc_info}")
                                    else:
                                        # 检查失败，判断是否是collection不存在的错误
                                        error_msg = check_result.get("msg", "")
                                        if "collection_not_exist" in error_msg.lower() or "not found" in error_msg.lower():
                                            should_resync = True
                                            logger.warning(f"FastGPT文件检查失败（文档可能不存在），准备重新同步 - {doc_info}: {error_msg}")
                                        else:
                                            logger.error(f"检查FastGPT文件状态失败 - {doc_info}: {error_msg}")
                                
                                # 执行重新同步
                                if should_resync:
                                    # 清空collection_id，标记为需要重新同步
                                    await db.execute(
                                        update(DocSubscription)
                                        .where(DocSubscription.id == doc.id)
                                        .values(
                                            collection_id=None,
                                            aichat_update_time=None
                                        )
                                    )
                                    await db.commit()
                                    
                                    # 创建同步请求并重新同步
                                    sync_request = SyncDocToAIChatRequest(
                                        app_id=doc.app_id,
                                        file_token=doc.file_token,
                                        file_type=doc.file_type
                                    )
                                    
                                    # 调用同步方法
                                    sync_result = await sync_document_to_aichat(sync_request, feishu_service)
                                    
                                    if sync_result.get("code") == 0:
                                        logger.info(f"成功重新同步文档到FastGPT - {doc_info}")
                                    else:
                                        error_msg = sync_result.get('msg', '未知错误')
                                        
                                        # 检查是否是文件不存在等不可恢复的错误
                                        if "文件不存在或已被删除" in error_msg or "404" in error_msg:
                                            logger.warning(f"重新同步失败：文件不存在，标记文档为不可用 - {doc_info}: {error_msg}")
                                            
                                            # 对于404错误，更新aichat_update_time避免重复尝试
                                            await db.execute(
                                                update(DocSubscription)
                                                .where(DocSubscription.id == doc.id)
                                                .values(aichat_update_time=datetime.now())
                                            )
                                            await db.commit()
                                            logger.info(f"已标记不存在的文件，避免重复尝试 - {doc_info}")
                                        elif "无权限访问" in error_msg or "403" in error_msg:
                                            logger.warning(f"重新同步失败：无权限访问文件 - {doc_info}: {error_msg}")
                                        elif "认证失败" in error_msg or "401" in error_msg:
                                            logger.warning(f"重新同步失败：认证失败，稍后重试 - {doc_info}: {error_msg}")
                                        else:
                                            logger.error(f"重新同步文档到FastGPT失败 - {doc_info}: {error_msg}")
                            except Exception as e:
                                logger.error(f"检查单个文档FastGPT状态失败: {doc.file_token}, 错误: {str(e)}")
                        
                    except Exception as e:
                        logger.error(f"处理应用 {app_id} 的文档时发生错误: {str(e)}")
                    finally:
                        # 确保关闭FastGPT服务实例
                        if fastgpt_service:
                            await fastgpt_service.close()
                
                logger.info(f"FastGPT文件状态检查完成 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
            except Exception as e:
                logger.error(f"检查FastGPT文件状态过程中发生错误: {str(e)}")
    
    async def _process_space(self, db: AsyncSession, feishu_service: FeishuService, space: SpaceSubscription):
        """处理单个知识空间的订阅"""
        try:
            logger.info(f"处理知识空间: {space.space_name} (ID: {space.space_id})")
            
            # 更新空间的最后同步时间
            space.last_sync_time = datetime.now()
            await db.commit()
            
            # 批量订阅空间下的文档
            result = await feishu_service.subscribe_space_documents(
                space.app_id,
                space.space_id
            )
            
            if result.get("code") == 0:
                data = result.get("data", {})
                logger.info(f"空间 {space.space_name} 同步结果: 共{data.get('total', 0)}个节点, "
                           f"{data.get('success', 0)}个新订阅, {data.get('already_subscribed', 0)}个已订阅")
                
                # 更新空间的文档计数
                await feishu_service.update_space_doc_count(space.app_id, space.space_id)
            else:
                logger.error(f"同步空间 {space.space_name} 失败: {result.get('msg', '未知错误')}")
                
        except Exception as e:
            logger.error(f"处理知识空间 {space.space_name} (ID: {space.space_id}) 时发生错误: {str(e)}")
            
            # 发生错误时，不影响其他空间的处理，继续执行

# 全局实例
scheduler = SubscriptionScheduler() 