from typing import List, Dict, Any
import logging

logger = logging.getLogger("doc_block_filter")

class DocBlockFilter:
    """飞书文档块过滤工具类
    
    用于过滤飞书文档块，只保留可转换为Markdown的通用块结构
    """
    
    # 可保留的块类型（可与Markdown互相转换的通用块）
    ALLOWED_BLOCK_TYPES = {
        2: "text",           # 普通文本（超链接也是块类型2）
        3: "heading1",       # 一级标题
        4: "heading2",       # 二级标题
        5: "heading3",       # 三级标题
        6: "heading4",       # 四级标题
        7: "heading5",       # 五级标题
        8: "heading6",       # 六级标题
        9: "heading7",       # 七级标题
        10: "heading8",      # 八级标题
        11: "heading9",      # 九级标题
        12: "bullet",        # 无序列表
        13: "ordered",       # 有序列表
        14: "code",          # 代码块
        15: "quote",         # 引用块（目前仍然是块类型2）
        16: "todo",          # 待办事项（读块直接就获取不到）
        22: "divider",       # 分割线
        27: "image",         # 图片
        31: "table",         # 表格
        32: "table_cell",    # 表格单元格
    }
    
    @classmethod
    def filter_blocks(cls, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """过滤文档块，只保留可转换为Markdown的通用块
        
        Args:
            blocks: 原始文档块列表
            
        Returns:
            List[Dict[str, Any]]: 过滤后的文档块列表
        """
        if not blocks:
            return []
        
        filtered_blocks = []
        filtered_count = 0
        
        for block in blocks:
            block_type = block.get("block_type")
            
            if block_type in cls.ALLOWED_BLOCK_TYPES:
                # 保留允许的块类型
                filtered_blocks.append(block)
            else:
                # 记录被过滤掉的块数量和类型
                filtered_count += 1
                logger.debug(f"过滤掉块类型: {block_type}, block_id: {block.get('block_id')}")
        
        logger.info(f"文档块过滤结果: 总块数={len(blocks)}, 保留块数={len(filtered_blocks)}, 过滤块数={filtered_count}")
        return filtered_blocks
    
    @classmethod
    def get_type_name(cls, block_type: int) -> str:
        """获取块类型名称
        
        Args:
            block_type: 块类型ID
            
        Returns:
            str: 块类型名称
        """
        return cls.ALLOWED_BLOCK_TYPES.get(block_type, f"未知类型({block_type})")
    
    @classmethod
    def organize_blocks(cls, blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """组织文档块，按照层级关系重构为树状结构
        
        Args:
            blocks: 过滤后的文档块列表
            
        Returns:
            Dict[str, Any]: 重构后的文档树
        """
        if not blocks:
            return {"blocks": [], "tree": {}}
        
        # 先过滤块
        filtered_blocks = cls.filter_blocks(blocks)
        
        # 创建一个映射，用于快速查找块
        block_map = {block.get("block_id"): block for block in filtered_blocks}
        
        # 查找根块（page类型）
        root_block = None
        for block in filtered_blocks:
            if block.get("block_type") == 1:  # page类型
                root_block = block
                break
        
        # 如果没有找到根块，则取第一个块作为根
        if not root_block and filtered_blocks:
            root_block = filtered_blocks[0]
        
        # 构建文档树
        tree = cls._build_tree(root_block, block_map) if root_block else {}
        
        return {
            "blocks": filtered_blocks,
            "tree": tree
        }
    
    @classmethod
    def _build_tree(cls, block: Dict[str, Any], block_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """递归构建块树
        
        Args:
            block: 当前块
            block_map: 块ID到块的映射
            
        Returns:
            Dict[str, Any]: 构建的树
        """
        if not block:
            return {}
        
        # 创建当前节点
        node = {
            "block_id": block.get("block_id"),
            "block_type": block.get("block_type"),
            "type_name": cls.get_type_name(block.get("block_type")),
            "content": cls._extract_block_content(block),
            "children": []
        }
        
        # 处理子节点
        children_ids = block.get("children", [])
        for child_id in children_ids:
            child_block = block_map.get(child_id)
            if child_block:
                child_tree = cls._build_tree(child_block, block_map)
                if child_tree:
                    node["children"].append(child_tree)
        
        return node
    
    @classmethod
    def _extract_block_content(cls, block: Dict[str, Any]) -> Any:
        """提取块内容
        
        根据块类型提取相应的内容
        
        Args:
            block: 块数据
            
        Returns:
            Any: 提取的内容
        """
        block_type = block.get("block_type")
        
        # 文本相关块（包括标题、列表等）
        if block_type in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]:
            # 提取文本内容
            type_name = cls.get_type_name(block_type)
            return block.get(type_name, {}).get("elements", [])
        
        # 图片块
        elif block_type == 27:
            return {
                "token": block.get("image", {}).get("token"),
                "width": block.get("image", {}).get("width"),
                "height": block.get("image", {}).get("height")
            }
        
        # 表格块
        elif block_type == 31:
            return {
                "rows": block.get("table", {}).get("rows", 0),
                "columns": block.get("table", {}).get("columns", 0)
            }
        
        # 表格单元格块
        elif block_type == 32:
            return {
                "row_index": block.get("table_cell", {}).get("row_index", 0),
                "col_index": block.get("table_cell", {}).get("col_index", 0)
            }
        
        # 分割线块
        elif block_type == 22:
            return {"divider": True}
        
        # 链接预览块
        elif block_type == 41:
            return {
                "url": block.get("link_preview", {}).get("url"),
                "title": block.get("link_preview", {}).get("title")
            }
        
        # 其他类型
        return {} 