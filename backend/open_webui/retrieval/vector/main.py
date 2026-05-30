"""
向量数据库抽象基类模块
功能: 定义所有向量数据库实现的统一接口

核心概念:
- 向量相似度搜索: 通过比较向量间的距离找到相似的文档
- 余弦相似度: 常用的向量相似度度量方式
- 集合(Collection): 向量数据的逻辑分组
- 元数据过滤: 支持按元数据属性筛选向量

RAG 中的角色:
- 存储: 将文档的向量表示存储到向量数据库
- 检索: 根据查询向量找到最相似的文档块

接口方法:
- has_collection: 检查集合是否存在
- insert/upsert: 插入或更新向量
- search: 向量相似度搜索
- query: 按元数据过滤查询
- get: 获取集合中的所有向量
- delete: 删除向量
- reset: 重置数据库
"""

from pydantic import BaseModel
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union


class VectorItem(BaseModel):
    """
    向量条目数据模型

    Attributes:
        id: 向量的唯一标识符
        text: 原始文本内容
        vector: 向量表示（浮点数列表）
        metadata: 元数据字典
    """


class GetResult(BaseModel):
    """
    向量查询结果模型

    Attributes:
        ids: 向量 ID 列表的列表
        documents: 文档文本列表的列表
        metadatas: 元数据列表的列表
    """


class SearchResult(GetResult):
    """
    向量搜索结果模型

    继承自 GetResult，额外包含:
    Attributes:
        distances: 距离/相似度分数列表的列表
    """


class VectorDBBase(ABC):
    """
    向量数据库抽象基类

    所有支持的向量数据库（Chroma, pgvector, Qdrant, Milvus 等）
    都必须继承自此类并实现所有抽象方法

    设计模式:
    - 工厂模式: 通过 VectorDBFactory 根据配置创建实例
    - 策略模式: 不同的向量数据库可以互换使用
    """

    @abstractmethod
    def has_collection(self, collection_name: str) -> bool:
        """
        检查集合是否存在

        Args:
            collection_name: 集合名称

        Returns:
            集合是否存在
        """
        pass

    @abstractmethod
    def delete_collection(self, collection_name: str) -> None:
        """
        删除整个集合

        Args:
            collection_name: 集合名称
        """
        pass

    @abstractmethod
    def insert(self, collection_name: str, items: List[VectorItem]) -> None:
        """
        插入向量条目

        Args:
            collection_name: 集合名称
            items: 向量条目列表
        """
        pass

    @abstractmethod
    def upsert(self, collection_name: str, items: List[VectorItem]) -> None:
        """
        插入或更新向量条目

        如果条目已存在则更新，不存在则插入

        Args:
            collection_name: 集合名称
            items: 向量条目列表
        """
        pass

    @abstractmethod
    def search(
        self,
        collection_name: str,
        vectors: List[List[Union[float, int]]],
        filter: Optional[Dict] = None,
        limit: int = 10,
    ) -> Optional[SearchResult]:
        """
        向量相似度搜索

        根据查询向量在集合中找到最相似的向量

        Args:
            collection_name: 集合名称
            vectors: 查询向量列表
            filter: 可选的元数据过滤条件
            limit: 返回结果数量限制

        Returns:
            搜索结果，包含 ID、文档、元数据和距离
        """
        pass

    @abstractmethod
    def query(self, collection_name: str, filter: Dict, limit: Optional[int] = None) -> Optional[GetResult]:
        """
        按元数据过滤查询向量

        Args:
            collection_name: 集合名称
            filter: 元数据过滤条件
            limit: 可选的结果数量限制

        Returns:
            查询结果
        """
        pass

    @abstractmethod
    def get(self, collection_name: str) -> Optional[GetResult]:
        """
        获取集合中的所有向量

        Args:
            collection_name: 集合名称

        Returns:
            所有向量的结果
        """
        pass

    @abstractmethod
    def delete(
        self,
        collection_name: str,
        ids: Optional[List[str]] = None,
        filter: Optional[Dict] = None,
    ) -> None:
        """
        删除向量

        可以通过 ID 列表或元数据过滤条件删除向量

        Args:
            collection_name: 集合名称
            ids: 要删除的向量 ID 列表
            filter: 元数据过滤条件
        """
        pass

    @abstractmethod
    def reset(self) -> None:
        """
        重置向量数据库

        删除所有集合和数据
        """
        pass
