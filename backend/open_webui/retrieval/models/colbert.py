"""
ColBERT 重排序模型模块
功能: 使用 ColBERT 模型进行文档重排序

概述:
ColBERT（Contextualized Late Interaction over BERT）是一种高效的神经排序模型。
它使用 BERT 对查询和文档分别编码，然后在延迟交互阶段计算相关性分数。

核心原理:
1. 编码阶段：分别对查询和文档进行编码，每个词产生一个向量
2. 延迟交互：查询向量与文档向量进行最大相似度匹配（MaxSim）
3. 聚合阶段：将所有匹配分数求和得到最终相关性分数

特点:
- 延迟交互：可以在编码阶段做预计算，提高推理效率
- 深度语义理解：利用 BERT 的上下文理解能力
- 支持 GPU 加速

模型来源:
- 默认使用 ColBERT 官方预训练模型
- 支持从 HuggingFace 或本地加载自定义模型

环境变量:
- COLBERT_ENV: 设置为 'docker' 时启用 Docker 特殊处理
"""

import os
import logging
import torch
import numpy as np
from colbert.infra import ColBERTConfig
from colbert.modeling.checkpoint import Checkpoint


from open_webui.retrieval.models.base_reranker import BaseReranker

log = logging.getLogger(__name__)


class ColBERT(BaseReranker):
    """
    ColBERT 重排序模型实现

    Attributes:
        device: 计算设备（cuda 或 cpu）
        ckpt: ColBERT 检查点/模型
    """

    def __init__(self, name, **kwargs) -> None:
        """
        初始化 ColBERT 模型

        Args:
            name: 模型名称或路径
            **kwargs: 其他参数（env='docker' 时启用特殊处理）
        """
        log.info('ColBERT: Loading model', name)
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'

        DOCKER = kwargs.get('env') == 'docker'
        if DOCKER:
            # This is a workaround for the issue with the docker container
            # where the torch extension is not loaded properly
            # and the following error is thrown:
            # /root/.cache/torch_extensions/py311_cpu/segmented_maxsim_cpp/segmented_maxsim_cpp.so: cannot open shared object file: No such file or directory

            lock_file = '/root/.cache/torch_extensions/py311_cpu/segmented_maxsim_cpp/lock'
            if os.path.exists(lock_file):
                os.remove(lock_file)

        self.ckpt = Checkpoint(
            name,
            colbert_config=ColBERTConfig(model_name=name),
        ).to(self.device)
        pass

    def calculate_similarity_scores(self, query_embeddings, document_embeddings):
        """
        计算查询与文档之间的相似度分数

        使用 MaxSim 算法计算每个文档的分数：
        1. 对查询和文档向量进行矩阵乘法
        2. 对每行取最大值（最大相似度）
        3. 对所有最大值求和

        Args:
            query_embeddings: 查询向量 (batch, query_len, dim)
            document_embeddings: 文档向量 (batch, doc_len, dim)

        Returns:
            归一化的相似度分数数组
        """
        query_embeddings = query_embeddings.to(self.device)
        document_embeddings = document_embeddings.to(self.device)

        # Validate dimensions to ensure compatibility
        if query_embeddings.dim() != 3:
            raise ValueError(f'Expected query embeddings to have 3 dimensions, but got {query_embeddings.dim()}.')
        if document_embeddings.dim() != 3:
            raise ValueError(f'Expected document embeddings to have 3 dimensions, but got {document_embeddings.dim()}.')
        if query_embeddings.size(0) not in [1, document_embeddings.size(0)]:
            raise ValueError('There should be either one query or queries equal to the number of documents.')

        # Transpose the query embeddings to align for matrix multiplication
        transposed_query_embeddings = query_embeddings.permute(0, 2, 1)
        # Compute similarity scores using batch matrix multiplication
        computed_scores = torch.matmul(document_embeddings, transposed_query_embeddings)
        # Apply max pooling to extract the highest semantic similarity across each document's sequence
        maximum_scores = torch.max(computed_scores, dim=1).values

        # Sum up the maximum scores across features to get the overall document relevance scores
        final_scores = maximum_scores.sum(dim=1)

        normalized_scores = torch.softmax(final_scores, dim=0)

        return normalized_scores.detach().cpu().numpy().astype(np.float32)

    def predict(self, sentences, batch_size=32):
        """
        预测查询-文档对的相关性分数

        Args:
            sentences: (查询, 文档) 元组列表
            batch_size: 批处理大小

        Returns:
            浮点数分数列表
        """
        query = sentences[0][0]
        docs = [i[1] for i in sentences]

        # Embedding the documents
        embedded_docs = self.ckpt.docFromText(docs, bsize=batch_size)[0]
        # Embedding the queries
        embedded_queries = self.ckpt.queryFromText([query], bsize=batch_size)
        embedded_query = embedded_queries[0]

        # Calculate retrieval scores for the query against all documents
        scores = self.calculate_similarity_scores(embedded_query.unsqueeze(0), embedded_docs)

        return scores