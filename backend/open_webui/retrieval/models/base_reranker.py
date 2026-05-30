"""
Reranker 基类模块
功能: 定义重排序模型的抽象接口

概述:
Reranker（重排序器）是 RAG 系统中的关键组件。
在初步检索后，重排序模型对结果进行再排序，提高相关性。

工作流程:
1. 检索阶段：向量数据库返回初步结果（可能几十条）
2. 重排序阶段：使用更精确的模型对结果进行排序
3. 选择阶段：选取排名最高的几个结果（通常 3-5 条）

应用场景:
- 当初步检索结果过多时，使用重排序精选
- 需要更精确的相关性判断时
- 多模态或多语言检索场景

使用示例:
    >>> reranker = SomeReranker(...)
    >>> scores = reranker.predict([("查询", "文档1"), ("查询", "文档2")])
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Tuple


class BaseReranker(ABC):
    """
    重排序模型抽象基类

    所有重排序模型必须继承此类并实现 predict 方法
    """

    @abstractmethod
    def predict(self, sentences: List[Tuple[str, str]]) -> Optional[List[float]]:
        """
        预测查询-文档对的相关性分数

        Args:
            sentences: (查询, 文档) 元组列表

        Returns:
            浮点数分数列表，按输入顺序对应，较高的分数表示较高的相关性
        """
        pass