"""
向量数据库工具函数模块
功能: 处理元数据和向量相关的辅助函数

主要功能:
- 元数据过滤: 移除大型/冗余字段
- 元数据处理: 转换不可序列化的类型，处理特殊字符
"""

from datetime import datetime

from open_webui.utils.misc import sanitize_text_for_db

# 需要从元数据中排除的字段
# 这些字段可能包含大量数据或导致序列化问题
KEYS_TO_EXCLUDE = ['content', 'pages', 'tables', 'paragraphs', 'sections', 'figures']


def filter_metadata(metadata: dict[str, any]) -> dict[str, any]:
    """
    过滤元数据字典

    移除大型/冗余字段以减小存储空间和提高查询效率

    Args:
        metadata: 原始元数据字典

    Returns:
        过滤后的元数据字典
    """
    metadata = {key: value for key, value in metadata.items() if key not in KEYS_TO_EXCLUDE}
    return metadata


def process_metadata(
    metadata: dict[str, any],
) -> dict[str, any]:
    """
    处理元数据以适应数据库存储

    执行以下转换:
    1. 移除大型字段（使用 KEYS_TO_EXCLUDE）
    2. 将不可序列化的类型（datetime, list, dict）转换为字符串
    3. 清理字符串中的无效字符（null bytes, surrogates）

    Args:
        metadata: 原始元数据字典

    Returns:
        处理后的元数据字典
    """
    result = {}
    for key, value in metadata.items():
        # Skip large fields
        if key in KEYS_TO_EXCLUDE:
            continue
        # Convert non-serializable fields to strings
        if isinstance(value, (datetime, list, dict)):
            result[key] = sanitize_text_for_db(str(value))
        else:
            result[key] = sanitize_text_for_db(value)
    return result
