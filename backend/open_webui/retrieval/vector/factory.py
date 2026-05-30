"""
向量数据库工厂模块
功能: 根据配置创建相应的向量数据库客户端实例

支持的后端:
- Chroma: 轻量级向量数据库，支持本地和远程部署
- pgvector: PostgreSQL 扩展，提供向量存储和相似度搜索
- Qdrant: 高性能向量数据库，支持多租户
- Milvus: 开源向量数据库，支持多种索引类型
- Pinecone: 云原生向量数据库服务
- Weaviate: 面向对象的向量数据库
- OpenSearch: 分布式搜索和分析引擎
- Elasticsearch: 分布式 RESTful 搜索和分析引擎
- Oracle23ai: Oracle 23ai 数据库内置向量支持
- S3Vector: AWS S3 向量存储
- OpenGauss: 华为开源数据库，向量支持
- MariaDB Vector: MariaDB 内置向量支持

多租户支持:
- Qdrant 和 Milvus 支持多租户模式，在单一集合中隔离不同租户的数据

配置:
- 通过环境变量 VECTOR_DB 指定使用的向量数据库类型
"""

from open_webui.retrieval.vector.main import VectorDBBase
from open_webui.retrieval.vector.type import VectorType
from open_webui.config import (
    VECTOR_DB,
    ENABLE_QDRANT_MULTITENANCY_MODE,
    ENABLE_MILVUS_MULTITENANCY_MODE,
)


class Vector:
    """
    向量数据库工厂类

    功能:
        根据向量类型字符串获取对应的向量数据库客户端实例

    方法:
        get_vector(vector_type): 创建并返回指定类型的向量数据库客户端

    使用示例:
        >>> client = Vector.get_vector('chroma')
        >>> client.insert('my_collection', items)
    """

    @staticmethod
    def get_vector(vector_type: str) -> VectorDBBase:
        """
        根据类型获取向量数据库客户端实例

        Args:
            vector_type: 向量数据库类型标识符

        Returns:
            对应的向量数据库客户端实例

        Raises:
            ValueError: 不支持的向量类型
        """
        match vector_type:
            case VectorType.MILVUS:
                if ENABLE_MILVUS_MULTITENANCY_MODE:
                    from open_webui.retrieval.vector.dbs.milvus_multitenancy import (
                        MilvusClient,
                    )

                    return MilvusClient()
                else:
                    from open_webui.retrieval.vector.dbs.milvus import MilvusClient

                    return MilvusClient()
            case VectorType.QDRANT:
                if ENABLE_QDRANT_MULTITENANCY_MODE:
                    from open_webui.retrieval.vector.dbs.qdrant_multitenancy import (
                        QdrantClient,
                    )

                    return QdrantClient()
                else:
                    from open_webui.retrieval.vector.dbs.qdrant import QdrantClient

                    return QdrantClient()
            case VectorType.PINECONE:
                from open_webui.retrieval.vector.dbs.pinecone import PineconeClient

                return PineconeClient()
            case VectorType.S3VECTOR:
                from open_webui.retrieval.vector.dbs.s3vector import S3VectorClient

                return S3VectorClient()
            case VectorType.OPENSEARCH:
                from open_webui.retrieval.vector.dbs.opensearch import OpenSearchClient

                return OpenSearchClient()
            case VectorType.PGVECTOR:
                from open_webui.retrieval.vector.dbs.pgvector import PgvectorClient

                return PgvectorClient()
            case VectorType.OPENGAUSS:
                from open_webui.retrieval.vector.dbs.opengauss import OpenGaussClient

                return OpenGaussClient()
            case VectorType.MARIADB_VECTOR:
                from open_webui.retrieval.vector.dbs.mariadb_vector import (
                    MariaDBVectorClient,
                )

                return MariaDBVectorClient()
            case VectorType.ELASTICSEARCH:
                from open_webui.retrieval.vector.dbs.elasticsearch import (
                    ElasticsearchClient,
                )

                return ElasticsearchClient()
            case VectorType.CHROMA:
                from open_webui.retrieval.vector.dbs.chroma import ChromaClient

                return ChromaClient()
            case VectorType.ORACLE23AI:
                from open_webui.retrieval.vector.dbs.oracle23ai import Oracle23aiClient

                return Oracle23aiClient()
            case VectorType.WEAVIATE:
                from open_webui.retrieval.vector.dbs.weaviate import WeaviateClient

                return WeaviateClient()
            case _:
                raise ValueError(f'Unsupported vector type: {vector_type}')


# 全局向量数据库客户端实例
# 根据配置创建，单例模式
VECTOR_DB_CLIENT = Vector.get_vector(VECTOR_DB)
