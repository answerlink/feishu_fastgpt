#!/usr/bin/env python3
"""
Markdown转换工具

用于优化从飞书获取的Markdown内容，特别是将HTML表格转换为标准的Markdown表格格式
"""

import re
from bs4 import BeautifulSoup
from typing import List, Dict

def convert_html_tables_to_markdown(markdown_content: str) -> str:
    """
    将Markdown中的HTML表格转换为标准的Markdown表格格式
    
    Args:
        markdown_content: 包含HTML表格的Markdown内容
        
    Returns:
        str: 转换后的Markdown内容
    """
    # 查找所有HTML表格
    table_pattern = r'<table>.*?</table>'
    tables = re.findall(table_pattern, markdown_content, re.DOTALL)
    
    for html_table in tables:
        try:
            # 使用BeautifulSoup解析HTML表格
            soup = BeautifulSoup(html_table, 'html.parser')
            table = soup.find('table')
            
            if table:
                markdown_table = convert_table_to_markdown(table)
                # 替换原始HTML表格
                markdown_content = markdown_content.replace(html_table, markdown_table)
        except Exception as e:
            print(f"转换表格时出错: {e}")
            # 如果转换失败，保留原始HTML
            continue
    
    return markdown_content

def convert_table_to_markdown(table) -> str:
    """
    将BeautifulSoup解析的表格转换为Markdown格式
    
    Args:
        table: BeautifulSoup表格对象
        
    Returns:
        str: Markdown格式的表格
    """
    rows = []
    
    # 获取所有行
    for tr in table.find_all('tr'):
        cells = []
        for td in tr.find_all(['td', 'th']):
            # 获取单元格文本，去除多余空白
            cell_text = td.get_text(strip=True)
            # 处理空单元格
            if not cell_text:
                cell_text = ""
            # 转义Markdown特殊字符
            cell_text = escape_markdown_chars(cell_text)
            cells.append(cell_text)
        
        if cells:  # 只添加非空行
            rows.append(cells)
    
    if not rows:
        return ""
    
    # 确定列数
    max_cols = max(len(row) for row in rows) if rows else 0
    
    # 标准化所有行的列数
    for row in rows:
        while len(row) < max_cols:
            row.append("")
    
    # 构建Markdown表格
    markdown_lines = []
    
    # 添加表头（第一行）
    if rows:
        header = "| " + " | ".join(rows[0]) + " |"
        markdown_lines.append(header)
        
        # 添加分隔线
        separator = "|" + "|".join(["-" * (len(cell) + 2) if cell else "---" for cell in rows[0]]) + "|"
        markdown_lines.append(separator)
        
        # 添加数据行
        for row in rows[1:]:
            data_row = "| " + " | ".join(row) + " |"
            markdown_lines.append(data_row)
    
    return "\n".join(markdown_lines)

def escape_markdown_chars(text: str) -> str:
    """
    转义Markdown特殊字符
    
    Args:
        text: 原始文本
        
    Returns:
        str: 转义后的文本
    """
    # 转义管道符，因为它在表格中有特殊含义
    text = text.replace("|", "\\|")
    return text

def optimize_markdown_content(markdown_content: str) -> str:
    """
    优化Markdown内容，提高LLM处理效果
    
    Args:
        markdown_content: 原始Markdown内容
        
    Returns:
        str: 优化后的Markdown内容
    """
    # 1. 转换HTML表格为Markdown表格
    content = convert_html_tables_to_markdown(markdown_content)
    
    # 2. 清理多余的空行
    content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
    
    # 3. 标准化标题格式
    content = standardize_headers(content)
    
    # 4. 清理HTML标签残留
    content = clean_html_tags(content)
    
    return content.strip()

def standardize_headers(content: str) -> str:
    """
    标准化标题格式
    
    Args:
        content: Markdown内容
        
    Returns:
        str: 标准化后的内容
    """
    # 确保标题前后有适当的空行
    content = re.sub(r'([^\n])\n(#{1,6}\s)', r'\1\n\n\2', content)
    content = re.sub(r'(#{1,6}\s[^\n]+)\n([^#\n])', r'\1\n\n\2', content)
    
    return content

def clean_html_tags(content: str) -> str:
    """
    清理残留的HTML标签
    
    Args:
        content: Markdown内容
        
    Returns:
        str: 清理后的内容
    """
    # 移除常见的HTML标签
    html_tags = ['<br>', '<br/>', '<br />', '<p>', '</p>', '<div>', '</div>', 
                 '<span>', '</span>', '<strong>', '</strong>', '<b>', '</b>',
                 '<em>', '</em>', '<i>', '</i>']
    
    for tag in html_tags:
        content = content.replace(tag, '')
    
    # 移除其他HTML标签（保守处理）
    content = re.sub(r'<[^>]+>', '', content)
    
    return content

# 使用示例
if __name__ == "__main__":
    # 测试HTML表格转换

    # 飞书-获取云文档内容（合并单元格的处理有bug）
    test_content = """
<table><tbody>\n<tr>\n<td>\n\n**一级品类**\n\n</td>\n<td>\n\n**二级品类**\n\n</td>\n<td>\n\n**三级品类**\n\n</td>\n</tr>\n<tr>\n<td rowspan=\"4\">\n\n项目采购\n\n</td>\n<td>\n\n咨询服务\n\n</td>\n<td>\n\n代理咨询服务\n\n</td>\n</tr>\n<tr>\n<td>\n\n项目硬件\n\n</td>\n<td>\n\n项目用硬件设备\n\n</td>\n</tr>\n<tr>\n<td>\n\n技术分包\n\n</td>\n<td>\n\n技术分包\n\n</td>\n</tr>\n<tr>\n<td>\n\n商务分包\n\n</td>\n<td>\n\n商务分包\n\n</td>\n</tr>\n<tr>\n<td rowspan=\"8\">\n\n非项目采购\n\n</td>\n<td rowspan=\"3\">\n\n公司自用产品\n\n</td>\n<td>\n\n大宗办公用品\n\n</td>\n</tr>\n<tr>\n<td>\n\n办公信息化工具\n\n</td>\n</tr>\n<tr>\n<td>\n\n公司自用硬件设备\n\n</td>\n</tr>\n<tr>\n<td rowspan=\"3\">\n\n房屋租赁装修\n\n</td>\n<td>\n\n办公家具\n\n</td>\n</tr>\n<tr>\n<td>\n\n装修\n\n</td>\n</tr>\n<tr>\n<td>\n\n物业管理\n\n</td>\n</tr>\n<tr>\n<td>\n\n交际礼品采购\n\n</td>\n<td>\n\n大宗商务礼品\n\n</td>\n</tr>\n<tr>\n<td>\n\n产品宣发材料\n\n</td>\n<td>\n\n大宗宣传物料\n\n</td>\n</tr>\n</tbody></table>
"""
    # 飞书-获取所有块-自己实现解析（合并单元格的处理正确）
    test_content = """
<table><tbody>\n<tr>\n<td>\n\n**一级品类**\n\n</td>\n<td>\n\n**二级品类**\n\n</td>\n<td>\n\n**三级品类**\n\n</td>\n</tr>\n<tr>\n<td>\n\n项目采购\n\n</td>\n<td>\n\n咨询服务\n\n</td>\n<td>\n\n代理咨询服务\n\n</td>\n</tr>\n<tr>\n<td>\n\n\n\n</td>\n<td>\n\n项目硬件\n\n</td>\n<td>\n\n项目用硬件设备\n\n</td>\n</tr>\n<tr>\n<td>\n\n\n\n</td>\n<td>\n\n技术分包\n\n</td>\n<td>\n\n技术分包\n\n</td>\n</tr>\n<tr>\n<td>\n\n\n\n</td>\n<td>\n\n商务分包\n\n</td>\n<td>\n\n商务分包\n\n</td>\n</tr>\n<tr>\n<td>\n\n非项目采购\n\n</td>\n<td>\n\n公司自用产品\n\n</td>\n<td>\n\n大宗办公用品\n\n</td>\n</tr>\n<tr>\n<td>\n\n\n\n</td>\n<td>\n\n\n\n</td>\n<td>\n\n办公信息化工具\n\n</td>\n</tr>\n<tr>\n<td>\n\n\n\n</td>\n<td>\n\n\n\n</td>\n<td>\n\n公司自用硬件设备\n\n</td>\n</tr>\n<tr>\n<td>\n\n\n\n</td>\n<td>\n\n房屋租赁装修\n\n</td>\n<td>\n\n办公家具\n\n</td>\n</tr>\n<tr>\n<td>\n\n\n\n</td>\n<td>\n\n\n\n</td>\n<td>\n\n装修\n\n</td>\n</tr>\n<tr>\n<td>\n\n\n\n</td>\n<td>\n\n\n\n</td>\n<td>\n\n物业管理\n\n</td>\n</tr>\n<tr>\n<td>\n\n\n\n</td>\n<td>\n\n交际礼品采购\n\n</td>\n<td>\n\n大宗商务礼品\n\n</td>\n</tr>\n<tr>\n<td>\n\n\n\n</td>\n<td>\n\n产品宣发材料\n\n</td>\n<td>\n\n大宗宣传物料\n\n</td>\n</tr>\n</tbody></table>
"""
    
    result = optimize_markdown_content(test_content)
    print("转换结果:")
    print(result) 