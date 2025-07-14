import json
import aiohttp
import asyncio
from typing import Dict, Any, List
from app.core.logger import setup_logger
import time

logger = setup_logger("aichat_service")

class AIChatService:
    """AI Chat服务，用于调用FastGPT等AI接口"""
    
    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url
        self.api_key = api_key
        self._client = None
    
    @property
    def client(self):
        """懒加载客户端会话"""
        if self._client is None or self._client.closed:
            self._client = aiohttp.ClientSession()
        return self._client
    
    async def chat_completion_streaming(self, message: List[Dict[str, Any]], variables: Dict[str, Any] = None, chat_id: str = None,
                                               on_status_callback=None, on_think_callback=None, on_answer_callback=None,
                                               on_references_callback=None, should_stop_callback=None, retain_dataset_cite: bool = False) -> str:
        """调用AI Chat接口获取回复（支持状态、思考和答案的分离回调，支持多模态）
        
        Args:
            message: 用户消息（多模态内容）
            variables: 额外变量，默认包含token
            on_status_callback: 状态更新回调函数，接收(status_text)参数
            on_think_callback: 思考过程回调函数，接收(think_text)参数
            on_answer_callback: 答案回调函数，接收(answer_text)参数
            on_references_callback: 引用数据回调函数，接收(references_data)参数
            should_stop_callback: 停止检查回调函数，返回True表示应该停止处理
            retain_dataset_cite: 是否保留数据集引用，默认为False
            
        Returns:
            str: AI回复内容
        """
        try:
            data = {
                "chatId": chat_id,
                "responseChatItemId": chat_id,
                "messages": [
                    {
                        "role": "user",
                        "content": message
                    }
                ],
                "variables": variables,
                "stream": True,
                "detail": True
            }
            
            # 只有在 retain_dataset_cite 为 True 时才添加这个字段 流式输出答案时会带引用 格式：[quote_id](CITE)
            if retain_dataset_cite:
                data["retainDatasetCite"] = True
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # 发送请求并处理流式响应
            think_content = ""
            answer_content = ""
            flow_node_statuses = []  # 存储流程节点状态
            pending_tasks = []  # 收集所有异步任务
            
            # 回调频率控制
            last_status_update = 0
            last_think_update = 0
            last_answer_update = 0
            callback_interval = 0.5  # 500ms间隔控制
            
            # 跟踪待发送的最新内容
            pending_status = None
            pending_think = None  
            pending_answer = None  
            
            # 使用临时的客户端会话避免事件循环冲突
            async with aiohttp.ClientSession(
                read_bufsize=1024*1024,  # 1MB缓冲区，解决Chunk too big错误
                max_line_size=1024*1024,  # 1MB最大行大小
                max_field_size=1024*1024  # 1MB最大字段大小
            ) as client:
                async with client.post(self.api_url, json=data, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"AI Chat接口返回错误: status={response.status}, error={error_text}")
                        return f"抱歉，AI服务暂时不可用，请稍后再试。"
                    
                    # 处理流式响应
                    current_event = None
                    async for line in response.content:
                        # 检查是否需要停止
                        if should_stop_callback and should_stop_callback():
                            logger.info("检测到停止信号，终止AI流式处理")
                            break
                        
                        line_text = line.decode('utf-8').strip()
                        
                        if not line_text:
                            continue
                        
                        # logger.debug(f"AI Chat流式响应: {line_text}")
                        
                        # 检查是否是结束标志
                        if line_text == "data: [DONE]":
                            logger.info(f"AI Chat响应结束，总内容长度: {len(answer_content)}")
                            # 调用回调函数标记完成
                            if on_status_callback and flow_node_statuses:
                                await on_status_callback("✅ **处理完成**")
                            continue
                        
                        # 处理SSE事件类型行
                        if line_text.startswith("event: "):
                            current_event = line_text[7:]  # 去掉"event: "前缀
                            continue
                        
                        # 解析SSE格式数据
                        if line_text.startswith("data: "):
                            try:
                                data_str = line_text[6:]  # 去掉"data: "前缀
                                data_obj = json.loads(data_str)
                                
                                # 根据事件类型处理数据
                                if current_event == "flowNodeStatus":
                                    # 处理流程节点状态
                                    status = data_obj.get("status")
                                    name = data_obj.get("name")
                                    
                                    if status == "running" and name:
                                        # 检查是否有未完成的答案更新
                                        if pending_answer and on_answer_callback:
                                            task = asyncio.create_task(on_answer_callback(pending_answer))
                                            pending_tasks.append(task)
                                            pending_answer = None  # 清除待发送
                                        
                                        # 添加到流程状态列表
                                        flow_node_statuses.append(name)
                                        # logger.debug(f"流程节点状态: {name} - {status}")
                                        
                                        # 构建状态内容
                                        status_content = f"🔄 **当前执行**: {name}"
                                        
                                        # 频率控制：立即发送或保存待发送
                                        current_time = time.time()
                                        if on_status_callback:
                                            if (current_time - last_status_update) >= callback_interval:
                                                # 立即发送
                                                last_status_update = current_time
                                                task = asyncio.create_task(on_status_callback(status_content))
                                                pending_tasks.append(task)
                                                pending_status = None  # 清除待发送
                                            else:
                                                # 保存为待发送（覆盖之前的）
                                                pending_status = status_content
                                
                                elif current_event == "toolCall":
                                    # 处理工具调用事件
                                    tool_info = data_obj.get("tool", {})
                                    tool_name = tool_info.get("toolName", "")
                                    function_name = tool_info.get("functionName", "")
                                    tool_id = tool_info.get("id", "")
                                    
                                    if tool_name:
                                        # 检查是否有未完成的答案更新
                                        if pending_answer and on_answer_callback:
                                            task = asyncio.create_task(on_answer_callback(pending_answer))
                                            pending_tasks.append(task)
                                            pending_answer = None  # 清除待发送
                                        
                                        logger.info(f"工具调用: {tool_name} (ID: {tool_id})")
                                        
                                        # 构建工具调用状态内容
                                        status_content = f"🔧 **工具调用**: {tool_name}..."
                                        
                                        # 频率控制：立即发送或保存待发送
                                        current_time = time.time()
                                        if on_status_callback:
                                            if (current_time - last_status_update) >= callback_interval:
                                                # 立即发送
                                                last_status_update = current_time
                                                task = asyncio.create_task(on_status_callback(status_content))
                                                pending_tasks.append(task)
                                                pending_status = None  # 清除待发送
                                            else:
                                                # 保存为待发送（覆盖之前的）
                                                pending_status = status_content
                                
                                elif current_event == "toolParams":
                                    # 处理工具参数事件（不显示给用户，只做日志记录）
                                    tool_info = data_obj.get("tool", {})
                                    tool_id = tool_info.get("id", "")
                                    params = tool_info.get("params", "")
                                    
                                    # 参数详情(流式响应 日志较多)
                                    # logger.debug(f"工具参数更新 (ID: {tool_id}): {params[:100]}{'...' if len(params) > 100 else ''}")
                                
                                elif current_event == "toolResponse":
                                    # 处理工具响应事件（不显示给用户，只做日志记录）
                                    tool_info = data_obj.get("tool", {})
                                    tool_id = tool_info.get("id", "")
                                    response = tool_info.get("response", "")
                                    
                                    # 只在debug级别记录响应概要
                                    # response_preview = response[:200] + "..." if len(response) > 200 else response
                                    # logger.debug(f"工具响应完成 (ID: {tool_id}): {response_preview}")
                                
                                # 处理思考过程和实际答案内容
                                elif current_event == "answer" or "choices" in data_obj:
                                    # 处理答案内容
                                    if "choices" in data_obj:
                                        choices = data_obj.get("choices", [])
                                        if choices and len(choices) > 0:
                                            delta = choices[0].get("delta", {})
                                            
                                            # 处理思考内容 (reasoning_content)
                                            reasoning_content = delta.get("reasoning_content")
                                            if reasoning_content:
                                                # 检查是否有未完成的状态更新
                                                if pending_status and on_status_callback:
                                                    task = asyncio.create_task(on_status_callback(pending_status))
                                                    pending_tasks.append(task)
                                                    pending_status = None  # 清除待发送

                                                think_content += reasoning_content
                                                
                                                # 频率控制：立即发送或保存待发送
                                                current_time = time.time()
                                                if on_think_callback:
                                                    if (current_time - last_think_update) >= callback_interval:
                                                        # 立即发送
                                                        last_think_update = current_time
                                                        task = asyncio.create_task(on_think_callback(think_content))
                                                        pending_tasks.append(task)
                                                        pending_think = None  # 清除待发送
                                                    else:
                                                        # 保存为待发送（覆盖之前的）
                                                        pending_think = think_content
                                            
                                            # 处理答案内容 (content)
                                            content = delta.get("content")
                                            if content:
                                                # 检查是否有未完成的思考更新
                                                if pending_think and on_think_callback:
                                                    task = asyncio.create_task(on_think_callback(pending_think))
                                                    pending_tasks.append(task)
                                                    pending_think = None
                                                
                                                answer_content += content
                                                
                                                # 频率控制：立即发送或保存待发送
                                                current_time = time.time()
                                                if on_answer_callback:
                                                    if (current_time - last_answer_update) >= callback_interval:
                                                        # 立即发送
                                                        last_answer_update = current_time
                                                        task = asyncio.create_task(on_answer_callback(answer_content))
                                                        pending_tasks.append(task)
                                                        pending_answer = None  # 清除待发送
                                                    else:
                                                        # 保存为待发送（覆盖之前的）
                                                        pending_answer = answer_content
                                    else:
                                        # 其他格式忽略
                                        pass
                                
                                elif current_event == "flowResponses" and isinstance(data_obj, list):
                                    # 处理流程响应数据 （代表本次长连接完全结束）
                                    
                                    # 检查是否有未完成的答案更新
                                    if pending_answer and on_answer_callback:
                                        task = asyncio.create_task(on_answer_callback(pending_answer))
                                        pending_tasks.append(task)
                                        pending_answer = None  # 清除待发送

                                    all_references = []  # 收集所有引用数据
                                    
                                    for flow_response in data_obj:
                                        # 过滤出知识库节点
                                        if flow_response.get("moduleType") == "datasetSearchNode":
                                            # logger.info(f"知识库节点响应: {json.dumps(flow_response, ensure_ascii=False, indent=2)}")
                                            
                                            # 提取关键信息
                                            module_name = flow_response.get("moduleName", "未知知识库")
                                            query = flow_response.get("query", "")
                                            quote_list = flow_response.get("quoteList", [])
                                            
                                            logger.info(f"知识库查询 - 模块: {module_name}, 查询: {query}, 引用数量: {len(quote_list)}")
                                            
                                            # 处理引用列表
                                            if quote_list:
                                                for i, quote in enumerate(quote_list):
                                                    source_name = quote.get("sourceName", "未知来源")
                                                    content = quote.get("q", "")
                                                    collection_id = quote.get("collectionId", "")
                                                    content_preview = content[:100] + "..." if len(content) > 100 else content
                                                    # logger.info(f"引用 {i+1}: 来源={source_name}, 内容预览={content_preview}")
                                                    
                                                    # 收集引用数据
                                                    all_references.append({
                                                        "source_name": source_name,
                                                        "content": content,
                                                        "module_name": module_name,
                                                        "query": query,
                                                        "collection_id": collection_id
                                                    })
                                    
                                    # 如果有引用数据，通过回调传递
                                    if all_references and on_references_callback:
                                        task = asyncio.create_task(on_references_callback(all_references))
                                        pending_tasks.append(task)

                                # 重置当前事件
                                current_event = None

                            except json.JSONDecodeError:
                                # 忽略非JSON格式的行
                                continue
                            except Exception as e:
                                logger.warning(f"解析SSE数据异常: {str(e)}, line: {line_text[:100]}")
                                continue
            
            # 等待所有异步任务完成
            if pending_tasks:
                logger.info(f"等待 {len(pending_tasks)} 个异步任务完成...")
                await asyncio.gather(*pending_tasks, return_exceptions=True)
                logger.info("所有异步任务已完成")
            
            logger.info(f"AI流式回复完成，最终内容长度: {len(answer_content)}")
            return answer_content

        except asyncio.TimeoutError:
            logger.error("AI Chat接口调用超时")
            return "抱歉，处理时间过长，请稍后再试。"
        except Exception as e:
            logger.error(f"AI聊天异常: {str(e)}")
            # 出现异常时也需要等待已创建的任务
            if 'pending_tasks' in locals() and pending_tasks:
                await asyncio.gather(*pending_tasks, return_exceptions=True)
            raise
    
    async def close(self):
        """关闭客户端会话"""
        if self._client and not self._client.closed:
            await self._client.close()
            self._client = None
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()
    
    def __del__(self):
        """析构函数"""
        if hasattr(self, '_client') and self._client and not self._client.closed:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.close())
                else:
                    loop.run_until_complete(self.close())
            except Exception as e:
                logger.error(f"关闭AI Chat客户端会话异常: {str(e)}") 