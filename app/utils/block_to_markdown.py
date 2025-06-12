from typing import List, Dict, Any, Tuple, Optional
import logging
from pathlib import Path
from app.utils.doc_block_filter import DocBlockFilter
from app.core.logger import setup_logger
from app.core.config import settings

logger = setup_logger("block_to_markdown")

class BlockToMarkdown:
    """飞书文档块转Markdown工具类
    
    将过滤后的飞书文档块转换为Markdown格式文本
    """
    
    # 块类型到Markdown格式的映射
    HEADING_LEVELS = {
        3: "#",        # 一级标题
        4: "##",       # 二级标题
        5: "###",      # 三级标题
        6: "####",     # 四级标题
        7: "#####",    # 五级标题
        8: "######",   # 六级标题
        9: "######",  # 七级标题
        10: "######", # 八级标题
        11: "######" # 九级标题
    }
    
    @classmethod
    async def convert(cls, blocks: List[Dict[str, Any]], doc_title: str = "", app_id: str = None) -> str:
        """将文档块转换为Markdown
        
        Args:
            blocks: 过滤后的文档块列表
            doc_title: 文档标题，可选
            app_id: 应用ID，用于获取VLM配置
            
        Returns:
            str: 生成的Markdown内容
        """
        if not blocks:
            return ""
        
        # 获取应用配置
        app_config = None
        if app_id:
            app_config = next((app for app in settings.FEISHU_APPS if app.app_id == app_id), None)
        
        # 构建块ID到块的映射
        block_map = {block.get("block_id"): block for block in blocks}
        
        # 找出顶级块（没有父块或父块不在blocks中的块）
        top_level_blocks = []
        for block in blocks:
            parent_id = block.get("parent_id")
            if not parent_id or parent_id not in block_map:
                top_level_blocks.append(block)
        
        # 按照块在文档中的顺序排序
        # 这里简单处理，假设块的顺序就是它们在blocks列表中的顺序
        
        # 初始化Markdown内容
        markdown = ""
        
        # 如果提供了文档标题，添加为一级标题
        if doc_title:
            markdown += f"# {doc_title}\n\n"
        
        # 初始化有序列表计数器字典
        ordered_list_counters = {}
        
        # 创建一个集合来记录已处理过的块的ID
        processed_block_ids = set()
        
        # 初始化VLM服务
        vlm_service = None
        if app_id and app_config:
            # 检查VLM相关配置是否完整
            vlm_config_complete = all([
                getattr(app_config, 'image_bed_vlm_api_url', None),
                getattr(app_config, 'image_bed_vlm_api_key', None),
                getattr(app_config, 'image_bed_vlm_model', None),
                getattr(app_config, 'image_bed_vlm_model_prompt', None)
            ])
            
            if vlm_config_complete:
                try:
                    from app.utils.vlm_service import VLMService
                    vlm_service = VLMService(app_id)
                    logger.info(f"VLM服务已启用: {app_id}")
                except Exception as e:
                    logger.error(f"初始化VLM服务失败: {str(e)}")
            else:
                logger.debug(f"VLM配置不完整，跳过VLM服务初始化: {app_id}")
        
        try:
            # 循环处理每个块
            for block in blocks:
                # 获取块的类型和内容
                block_type = block.get("block_type")
                block_id = block.get("block_id")
                
                # 如果块已经处理过，则跳过
                if block_id in processed_block_ids:
                    continue
                    
                # 根据块类型生成对应的Markdown内容
                block_md, append_newline = await cls._convert_block(
                    block, block_map, ordered_list_counters, processed_block_ids, app_config, vlm_service
                )
                markdown += block_md
                
                # 根据需要添加换行
                if append_newline:
                    markdown += "\n\n"
        
        finally:
            # 关闭VLM服务
            if vlm_service:
                await vlm_service.close()
        
        return markdown
    
    @classmethod
    async def _convert_block(cls, block: Dict[str, Any], block_map: Dict[str, Dict[str, Any]], 
                       ordered_list_counters: Dict[str, int] = None, 
                       processed_block_ids: set = None,
                       app_config = None,
                       vlm_service = None) -> Tuple[str, bool]:
        """转换单个块为Markdown
        
        Args:
            block: 文档块
            block_map: 块ID到块的映射
            ordered_list_counters: 有序列表计数器字典
            processed_block_ids: 已处理的块ID集合
            app_config: 应用配置
            vlm_service: VLM服务
            
        Returns:
            Tuple[str, bool]: (Markdown内容, 是否需要添加换行)
        """
        block_type = block.get("block_type")
        block_id = block.get("block_id")
        indent_level = cls._get_indent_level(block, block_map)
        indent = "    " * indent_level  # 缩进使用4个空格
        
        # 将当前块标记为已处理
        if processed_block_ids is not None and block_id:
            processed_block_ids.add(block_id)
        
        # 根据块类型生成对应的Markdown内容
        if block_type == 2:  # 文本块
            text_content = cls._extract_text_content(block.get("text", {}).get("elements", []))
            return f"{indent}{text_content}", True
            
        elif block_type in cls.HEADING_LEVELS:  # 标题块
            type_name = DocBlockFilter.get_type_name(block_type)
            text_content = cls._extract_text_content(block.get(type_name, {}).get("elements", []))
            heading_marker = cls.HEADING_LEVELS[block_type]
            return f"{indent}{heading_marker} {text_content}", True
            
        elif block_type == 12:  # 无序列表
            text_content = cls._extract_text_content(block.get("bullet", {}).get("elements", []))
            return f"{indent}- {text_content}", True
            
        elif block_type == 13:  # 有序列表
            text_content = cls._extract_text_content(block.get("ordered", {}).get("elements", []))
            
            # 获取父块ID
            parent_id = block.get("parent_id") or "root"
            
            # 初始化计数器字典
            if ordered_list_counters is None:
                ordered_list_counters = {}
            
            # 生成用于计数的键
            counter_key = f"{parent_id}_{indent_level}"
            
            # 检查父列表项是否已经有计数器值
            if counter_key not in ordered_list_counters:
                ordered_list_counters[counter_key] = 1
            
            # 获取当前序号并递增
            current_number = ordered_list_counters[counter_key]
            ordered_list_counters[counter_key] += 1
            
            return f"{indent}{current_number}. {text_content}", True
            
        elif block_type == 14:  # 代码块
            text_content = cls._extract_text_content(block.get("code", {}).get("elements", []))
            lang = block.get("code", {}).get("style", {}).get("language", "")
            return f"{indent}```\n{indent}{text_content}\n{indent}```", True
            
        elif block_type == 15:  # 引用块
            # 注意：飞书文档API中引用块应该是block_type == 15，但实际上有时候会以block_type == 2（文本块）的形式返回
            # 这会导致引用块无法被正确识别和转换，需要特殊处理那些实际是引用但被标记为文本块的内容
            text_content = cls._extract_text_content(block.get("quote", {}).get("elements", []))
            # 处理多行引用，确保每行都有 > 前缀
            lines = text_content.split('\n')
            quote_lines = [f"{indent}> {line}" for line in lines]
            quote_content = '\n'.join(quote_lines)
            return quote_content, True
            
        elif block_type == 16:  # 待办事项
            text_content = cls._extract_text_content(block.get("todo", {}).get("elements", []))
            done = block.get("todo", {}).get("style", {}).get("done", False)
            # 使用星号而不是短横线，已完成的任务添加删除线
            checkbox = "[x]" if done else "[ ]"
            formatted_text = f"~~{text_content}~~" if done else text_content
            return f"{indent}* {checkbox} {formatted_text}", True
            
        elif block_type == 22:  # 分割线
            return f"{indent}---", True
            
        elif block_type == 27:  # 图片块
            image_token = block.get("image", {}).get("token", "")
            
            # 检查是否有本地URL（已下载的图片）
            local_url = block.get("image", {}).get("local_url")
            if local_url:
                # 使用本地静态文件URL
                image_url = local_url
                logger.info(f"图片块使用本地URL: {image_token} -> {image_url}")
            else:
                # 如果没有本地URL，使用静态文件访问格式
                # 假设图片已经下载到static/images目录，使用token作为文件名
                image_url = f"/static/images/{image_token}.png"
                logger.info(f"图片块使用静态URL: {image_token} -> {image_url}")
            
            # 添加image_bed_base_url前缀
            if app_config and hasattr(app_config, 'image_bed_base_url') and app_config.image_bed_base_url:
                base_url = app_config.image_bed_base_url.rstrip('/')
                full_image_url = f"{base_url}{image_url}"
                logger.debug(f"添加base_url前缀: {image_url} -> {full_image_url}")
            else:
                full_image_url = image_url
            
            # 获取图片描述
            alt_text = ""
            if vlm_service and vlm_service.is_enabled():
                try:
                    # 构建本地图片文件路径
                    if local_url:
                        # 从local_url中提取文件名
                        local_path = local_url.replace("/static/images/", "")
                        image_file_path = Path("static/images") / local_path
                    else:
                        # 使用token构建路径
                        image_file_path = Path("static/images") / f"{image_token}.png"
                    
                    if image_file_path.exists():
                        description = await vlm_service.get_image_description(str(image_file_path))
                        if description:
                            alt_text = description
                            logger.info(f"获取到图片描述: {image_token} -> {alt_text}")
                        else:
                            logger.debug(f"未获取到图片描述: {image_token}")
                    else:
                        logger.warning(f"图片文件不存在，无法获取描述: {image_file_path}")
                except Exception as e:
                    logger.error(f"获取图片描述异常: {image_token}, 错误: {str(e)}")
            
            return f"{indent}![{alt_text}]({full_image_url})", True
            
        elif block_type == 31:  # 表格
            # 获取表格行列信息
            rows = block.get("table", {}).get("property", {}).get("row_size", 0)
            columns = block.get("table", {}).get("property", {}).get("column_size", 0)
            
            # 获取表格所有子块（单元格）和子块内的内容块
            children_ids = block.get("children", [])
            cell_blocks = []
            for child_id in children_ids:
                if child_id in block_map:
                    cell_block = block_map[child_id]
                    cell_blocks.append(cell_block)
                    
                    # 将单元格标记为已处理
                    if processed_block_ids is not None:
                        processed_block_ids.add(child_id)
                        
                        # 标记单元格内所有子块为已处理
                        for grandchild_id in cell_block.get("children", []):
                            if grandchild_id in block_map:
                                processed_block_ids.add(grandchild_id)
            
            # 构建HTML表格
            table_html = f"{indent}<table><tbody>\n"
            
            # 根据行列数和单元格顺序组织表格
            if rows > 0 and columns > 0:
                # 遍历每一行
                for row_index in range(rows):
                    table_html += f"{indent}<tr>\n"
                    # 遍历该行的每一列
                    for col_index in range(columns):
                        # 计算单元格在列表中的索引
                        cell_index = row_index * columns + col_index
                        
                        if cell_index < len(cell_blocks):
                            cell = cell_blocks[cell_index]
                            
                            # 获取单元格内容
                            cell_content = ""
                            for child_id in cell.get("children", []):
                                if child_id in block_map:
                                    child_block = block_map[child_id]
                                    child_md, _ = await cls._convert_block(child_block, block_map, ordered_list_counters, processed_block_ids, app_config, vlm_service)
                                    cell_content += child_md.strip() + "\n\n"
                            
                            # 添加单元格
                            table_html += f"{indent}<td>\n\n{cell_content}</td>\n"
                    
                    table_html += f"{indent}</tr>\n"
            
            table_html += f"{indent}</tbody></table>"
            
            return table_html, True
            
        elif block_type == 41:  # 链接预览
            url = block.get("link_preview", {}).get("url", "")
            title = block.get("link_preview", {}).get("title", url)
            return f"{indent}[{title}]({url})", True
            
        else:
            # 未知块类型，返回空字符串
            return "", True
    
    @classmethod
    def _extract_text_content(cls, elements: List[Dict[str, Any]]) -> str:
        """从文本元素中提取文本内容
        
        Args:
            elements: 文本元素列表
            
        Returns:
            str: 提取的文本内容
        """
        if not elements:
            return ""
        
        text = ""
        for element in elements:
            # 处理文本运行
            if "text_run" in element:
                content = element["text_run"].get("content", "")
                style = element["text_run"].get("text_element_style", {})
                
                # 处理链接
                if style.get("link") and style.get("link").get("url"):
                    url = style.get("link").get("url", "")
                    # URL解码
                    try:
                        import urllib.parse
                        url = urllib.parse.unquote(url)
                    except Exception as e:
                        logger.warning(f"URL解码失败: {url}, 错误: {str(e)}")
                    
                    # 构建Markdown链接格式
                    content = f"[{content}]({url})"
                # 应用其他样式
                else:
                    if style.get("bold"):
                        content = f"**{content}**"
                    if style.get("italic"):
                        content = f"*{content}*"
                    if style.get("strikethrough"):
                        content = f"~~{content}~~"
                    if style.get("underline"):
                        content = f"<u>{content}</u>"
                    if style.get("inline_code"):
                        content = f"`{content}`"
                
                text += content
            # 处理其他可能的元素类型，如链接等
            # 省略其他可能的处理...
        
        return text
    
    @classmethod
    def _get_indent_level(cls, block: Dict[str, Any], block_map: Dict[str, Dict[str, Any]]) -> int:
        """计算块的缩进级别
        
        Args:
            block: 文档块
            block_map: 块ID到块的映射
            
        Returns:
            int: 缩进级别
        """
        # 只有列表类型需要考虑缩进
        if block.get("block_type") not in [12, 13]:  # 无序列表和有序列表
            return 0
        
        # 获取父块ID
        parent_id = block.get("parent_id")
        if not parent_id or parent_id not in block_map:
            return 0
        
        # 获取父块
        parent_block = block_map[parent_id]
        parent_type = parent_block.get("block_type")
        
        # 如果父块也是列表，则在父块的缩进基础上增加一级
        if parent_type in [12, 13]:
            # 递归计算父块的缩进
            return cls._get_indent_level(parent_block, block_map) + 1
        
        return 0 