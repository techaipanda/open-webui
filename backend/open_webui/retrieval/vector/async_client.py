"""
向量数据库异步客户端模块
功能: 将同步向量数据库操作包装为异步操作

问题背景:
Open WebUI 捆绑的向量数据库后端（Chroma, pgvector, Qdrant, Milvus, OpenSearch, Pinecone, Weaviate 等）
都暴露统一的同步 API。每个方法执行阻塞的网络或磁盘 I/O。
某些操作（如 insert/upsert）可能需要数秒。

当从异步路由处理器中等待同步方法时，它会阻塞整个事件循环，
导致所有其他进行中的 HTTP 请求、WebSocket 消息和后台任务冻结。

解决方案:
本模块将同步客户端包装在 AsyncVectorDBClient 中，
通过 asyncio.to_thread 透明地将每个调用分派到工作线程。
异步调用者可以 await ASYNC_VECTOR_DB_CLIENT.x(...) 代替 VECTOR_DB_CLIENT.x(...)

设计原则:
- VECTOR_DB_CLIENT 保持不变，已使用 run_in_threadpool 的调用者（如 save_docs_to_vector_db）不受影响
- 线程安全由底层驱动保证（这是已有的要求）
- 不添加全局序列化锁（否则失去异步响应性优势）
- 方法签名与 VectorDBBase 完全一致，静态分析可以在调用站点捕获错误的 kwargs

使用示例:
    # 异步调用
    results = await ASYNC_VECTOR_DB_CLIENT.search(collection_name, vectors, limit=10)

    # 需要后端特定参数时，使用 .sync 逃生舱口
    await asyncio.to_thread(
        ASYNC_VECTOR_DB_CLIENT.sync.some_backend_specific_op,
        collection_name, special_kwarg=value,
    )
"""

from __future__ import annotations

import asyncio
from typing import Dict, List, Optional, Union

from open_webui.retrieval.vector.factory import VECTOR_DB_CLIENT
from open_webui.retrieval.vector.main import (
    GetResult,
    SearchResult,
    VectorDBBase,
    VectorItem,
)


class AsyncVectorDBClient:
    """
    VectorDBBase 的可等待镜像，将每个调用分派到线程

    方法签名与 VectorDBBase 完全一致，
    因此静态分析可以在调用站点捕获错误的 kwargs，
    而不是让它们在 worker 线程深处（通常被周围的 try/except 吞没）暴露

    Attributes:
        _sync: 底层同步向量数据库客户端
    """

    def __init__(self, sync_client: VectorDBBase) -> None:
        """
        初始化异步向量数据库客户端

        Args:
            sync_client: 同步的 VectorDBBase 实例
        """
        self._sync = sync_client

    @property
    def sync(self) -> VectorDBBase:
        """
        获取同步客户端的逃生舱口

        用于必须在工作线程内调用同步客户端的代码

        Returns:
            底层同步客户端实例
        """
        """Escape hatch for code that must call the sync client directly
        (e.g. already inside a worker thread)."""
        return self._sync

    async def has_collection(self, collection_name: str) -> bool:
        """
        检查集合是否存在

        Args:
            collection_name: 集合名称

        Returns:
            集合是否存在
        """
        return await asyncio.to_thread(self._sync.has_collection, collection_name)

    async def delete_collection(self, collection_name: str) -> None:
        """
        删除整个集合

        Args:
            collection_name: 集合名称
        """
        return await asyncio.to_thread(self._sync.delete_collection, collection_name)

    async def insert(self, collection_name: str, items: List[VectorItem]) -> None:
        """
        插入向量条目

        Args:
            collection_name: 集合名称
            items: 向量条目列表
        """
        return await asyncio.to_thread(self._sync.insert, collection_name, items)

    async def upsert(self, collection_name: str, items: List[VectorItem]) -> None:
        """
        插入或更新向量条目

        Args:
            collection_name: 集合名称
            items: 向量条目列表
        """
        return await asyncio.to_thread(self._sync.upsert, collection_name, items)

    async def search(
        self,
        collection_name: str,
        vectors: List[List[Union[float, int]]],
        filter: Optional[Dict] = None,
        limit: int = 10,
    ) -> Optional[SearchResult]:
        """
        向量相似度搜索

        Args:
            collection_name: 集合名称
            vectors: 查询向量列表
            filter: 可选的元数据过滤条件
            limit: 返回结果数量限制

        Returns:
            搜索结果
        """
        return await asyncio.to_thread(self._sync.search, collection_name, vectors, filter, limit)

    async def query(
        self,
        collection_name: str,
        filter: Dict,
        limit: Optional[int] = None,
    ) -> Optional[GetResult]:
        """
        按元数据过滤查询向量

        Args:
            collection_name: 集合名称
            filter: 元数据过滤条件
            limit: 可选的结果数量限制

        Returns:
            查询结果
        """
        return await asyncio.to_thread(self._sync.query, collection_name, filter, limit)

    async def get(self, collection_name: str) -> Optional[GetResult]:
        """
        获取集合中的所有向量

        Args:
            collection_name: 集合名称

        Returns:
            所有向量的结果
        """
        return await asyncio.to_thread(self._sync.get, collection_name)

    async def delete(
        self,
        collection_name: str,
        ids: Optional[List[str]] = None,
        filter: Optional[Dict] = None,
    ) -> None:
        """
        删除向量

        Args:
            collection_name: 集合名称
            ids: 要删除的向量 ID 列表
            filter: 元数据过滤条件
        """
        return await asyncio.to_thread(self._sync.delete, collection_name, ids, filter)

    async def reset(self) -> None:
        """
        重置向量数据库

        删除所有集合和数据
        """
        return await asyncio.to_thread(self._sync.reset)


ASYNC_VECTOR_DB_CLIENT = AsyncVectorDBClient(VECTOR_DB_CLIENT)