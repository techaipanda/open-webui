"""
向量数据库类型枚举模块
功能: 定义支持的向量数据库类型常量

每种类型对应一个向量数据库后端实现:
- MILVUS: 开源向量数据库，支持多种索引类型
- MARIADB_VECTOR: MariaDB 内置向量支持
- QDRANT: 高性能向量数据库
- CHROMA: 轻量级向量数据库
- PINECONE: 云原生向量数据库服务
- ELASTICSEARCH: 分布式搜索引擎
- OPENSEARCH: 开放式搜索和分析平台
- PGVECTOR: PostgreSQL 向量扩展
- ORACLE23AI: Oracle 23ai 内置向量支持
- S3VECTOR: AWS S3 向量存储
- WEAVIATE: 面向对象的向量数据库
- OPENGAUSS: 华为开源数据库向量支持
"""

from enum import StrEnum


class VectorType(StrEnum):
    """
    向量数据库类型枚举

    使用字符串枚举便于配置和环境变量使用
    """
    MILVUS = 'milvus'
    MARIADB_VECTOR = 'mariadb-vector'
    QDRANT = 'qdrant'
    CHROMA = 'chroma'
    PINECONE = 'pinecone'
    ELASTICSEARCH = 'elasticsearch'
    OPENSEARCH = 'opensearch'
    PGVECTOR = 'pgvector'
    ORACLE23AI = 'oracle23ai'
    S3VECTOR = 's3vector'
    WEAVIATE = 'weaviate'
    OPENGAUSS = 'opengauss'
