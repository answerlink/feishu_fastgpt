"""
飞书电子表格转换工具

将飞书电子表格的单元格数据转换为Markdown表格格式
"""

from typing import List, Any, Optional
import re
import html


class SheetConverter:
    """飞书电子表格转换器"""
    
    def __init__(self):
        """初始化转换器"""
        pass
    
    def convert_to_markdown(self, values: List[List[Any]], sheet_title: str = "工作表") -> str:
        """将工作表数据转换为Markdown表格
        
        Args:
            values: 工作表的单元格数据，二维数组
            sheet_title: 工作表标题
            
        Returns:
            str: Markdown格式的表格内容
        """
        if not values or len(values) == 0:
            return f"## {sheet_title}\n\n此工作表暂无数据。"
        
        # 清理和处理数据
        cleaned_values = self._clean_values(values)
        
        if not cleaned_values:
            return f"## {sheet_title}\n\n此工作表暂无有效数据。"
        
        # 自动检测有效列数，去除末尾的空列
        effective_cols = self._detect_effective_columns(cleaned_values)
        
        if effective_cols == 0:
            return f"## {sheet_title}\n\n此工作表暂无有效数据。"
        
        # 截取有效列的数据
        trimmed_values = []
        for row in cleaned_values:
            # 只保留有效列数的数据，如果行数据不够，用空字符串补齐
            trimmed_row = []
            for i in range(effective_cols):
                if i < len(row):
                    trimmed_row.append(row[i])
                else:
                    trimmed_row.append("")
            trimmed_values.append(trimmed_row)
        
        # 生成Markdown表格
        markdown = f"## {sheet_title}\n\n"
        
        if len(trimmed_values) == 1:
            # 只有一行数据，作为普通内容显示
            row_content = " | ".join(str(cell) for cell in trimmed_values[0])
            markdown += f"{row_content}\n"
        else:
            # 多行数据，生成表格
            markdown += self._generate_markdown_table(trimmed_values)
        
        return markdown
    
    def _clean_values(self, values: List[List[Any]]) -> List[List[str]]:
        """清理和标准化单元格数据
        
        Args:
            values: 原始单元格数据
            
        Returns:
            List[List[str]]: 清理后的数据
        """
        cleaned = []
        
        for row in values:
            cleaned_row = []
            for cell in row:
                # 处理不同类型的单元格数据
                if cell is None:
                    cleaned_cell = ""
                elif isinstance(cell, list):
                    # 处理列表类型的单元格数据（通常包含链接信息）
                    cleaned_cell = self._extract_text_from_cell_list(cell)
                elif isinstance(cell, dict):
                    # 如果是字典，尝试提取文本内容
                    cleaned_cell = self._extract_text_from_cell_dict(cell)
                elif isinstance(cell, (int, float)):
                    cleaned_cell = str(cell)
                else:
                    cleaned_cell = str(cell).strip()
                
                # 清理HTML标签和特殊字符
                cleaned_cell = self._clean_text(cleaned_cell)
                cleaned_row.append(cleaned_cell)
            
            # 跳过完全空白的行
            if any(cell.strip() for cell in cleaned_row):
                cleaned.append(cleaned_row)
        
        return cleaned
    
    def _extract_text_from_cell_dict(self, cell_dict: dict) -> str:
        """从单元格字典中提取文本内容
        
        Args:
            cell_dict: 单元格字典数据
            
        Returns:
            str: 提取的文本内容
        """
        # 飞书API可能返回的单元格格式：
        # {"text": "内容"} 或 {"formattedValue": "内容"} 等
        
        if "text" in cell_dict:
            return str(cell_dict["text"])
        elif "formattedValue" in cell_dict:
            return str(cell_dict["formattedValue"])
        elif "value" in cell_dict:
            return str(cell_dict["value"])
        else:
            # 如果都没有，返回整个字典的字符串表示
            return str(cell_dict)
    
    def _extract_text_from_cell_list(self, cell_list: list) -> str:
        """从单元格列表中提取文本内容（处理飞书电子表格中的链接格式）
        
        Args:
            cell_list: 单元格列表数据，包含文本和链接信息
            
        Returns:
            str: 转换后的Markdown格式文本
        """
        if not cell_list:
            return ""
        
        result_parts = []
        
        for element in cell_list:
            if isinstance(element, dict):
                element_type = element.get("type", "")
                
                if element_type == "url":
                    # 处理普通URL链接: {"type": "url", "text": "这是百度链接", "link": "http://www.baidu.com"}
                    text = element.get("text", "")
                    link = element.get("link", "")
                    if text and link:
                        # URL解码
                        import urllib.parse
                        try:
                            decoded_link = urllib.parse.unquote(link)
                        except:
                            decoded_link = link
                        result_parts.append(f"[{text}]({decoded_link})")
                    elif text:
                        result_parts.append(text)
                    elif link:
                        result_parts.append(link)
                        
                elif element_type == "mention":
                    # 处理飞书文档提及链接: {"type": "mention", "text": "调研分析", "link": "https://..."}
                    text = element.get("text", "")
                    link = element.get("link", "")
                    if text and link:
                        result_parts.append(f"[{text}]({link})")
                    elif text:
                        result_parts.append(text)
                    elif link:
                        result_parts.append(link)
                        
                elif element_type == "text":
                    # 处理纯文本: {"type": "text", "text": " "}
                    text = element.get("text", "")
                    if text:
                        result_parts.append(text)
                        
                else:
                    # 未知类型，尝试提取text字段
                    text = element.get("text", "")
                    if text:
                        result_parts.append(text)
                    else:
                        # 如果没有text字段，返回字典的字符串表示
                        result_parts.append(str(element))
                        
            else:
                # 非字典类型，直接转换为字符串
                result_parts.append(str(element))
        
        return "".join(result_parts)
    
    def _clean_text(self, text: str) -> str:
        """清理文本内容
        
        Args:
            text: 原始文本
            
        Returns:
            str: 清理后的文本
        """
        if not text:
            return ""
        
        # 解码HTML实体
        text = html.unescape(text)
        
        # 移除HTML标签
        text = re.sub(r'<[^>]+>', '', text)
        
        # 清理多余的空白字符
        text = re.sub(r'\s+', ' ', text).strip()
        
        # 转义Markdown特殊字符
        text = self._escape_markdown(text)
        
        return text
    
    def _escape_markdown(self, text: str) -> str:
        """转义Markdown特殊字符
        
        Args:
            text: 原始文本
            
        Returns:
            str: 转义后的文本
        """
        # 转义Markdown表格中的管道符
        text = text.replace("|", "\\|")
        
        # 转义其他可能影响表格的字符
        text = text.replace("\n", " ")  # 将换行符替换为空格
        text = text.replace("\r", " ")
        
        return text
    
    def _generate_markdown_table(self, values: List[List[str]]) -> str:
        """生成Markdown表格
        
        Args:
            values: 规范化的单元格数据
            
        Returns:
            str: Markdown表格字符串
        """
        if not values:
            return ""
        
        lines = []
        
        # 添加表头（第一行）
        header = "| " + " | ".join(values[0]) + " |"
        lines.append(header)
        
        # 添加分隔行
        separator = "| " + " | ".join(["---"] * len(values[0])) + " |"
        lines.append(separator)
        
        # 添加数据行（从第二行开始）
        for row in values[1:]:
            data_row = "| " + " | ".join(row) + " |"
            lines.append(data_row)
        
        return "\n".join(lines) + "\n"
    
    def convert_multiple_sheets(self, sheets_data: List[dict]) -> str:
        """转换多个工作表
        
        Args:
            sheets_data: 工作表数据列表，每个元素包含title和values
            
        Returns:
            str: 所有工作表的Markdown内容
        """
        if not sheets_data:
            return "# 电子表格\n\n此表格暂无数据。"
        
        markdown_parts = ["# 电子表格内容\n"]
        
        for sheet_data in sheets_data:
            title = sheet_data.get("title", "未知工作表")
            values = sheet_data.get("values", [])
            
            sheet_markdown = self.convert_to_markdown(values, title)
            markdown_parts.append(sheet_markdown)
        
        return "\n\n".join(markdown_parts)
    
    def _detect_effective_columns(self, values: List[List[str]]) -> int:
        """检测有效的列数，去除末尾的空列
        
        Args:
            values: 清理后的数据
            
        Returns:
            int: 有效列数
        """
        if not values:
            return 0
        
        max_effective_cols = 0
        
        for row in values:
            # 从右往左找到第一个非空单元格
            effective_cols = 0
            for i in range(len(row) - 1, -1, -1):
                if row[i] and str(row[i]).strip():
                    effective_cols = i + 1
                    break
            
            max_effective_cols = max(max_effective_cols, effective_cols)
        
        return max_effective_cols 