"""
外部重排序模型模块
功能: 通过外部 API 服务进行文档重排序

概述:
外部重排序允许使用任何兼容的 rerank API 服务。
通过配置 API URL 和密钥，可以集成任何支持以下格式的服务：

请求格式:
- URL: 外部服务 endpoint（默认 http://localhost:8080/v1/rerank）
- Method: POST
- Body: {model, query, documents, top_n}

响应格式:
- JSON: {results: [{index, relevance_score}, ...]}

特点:
- 灵活集成：支持任何兼容的 rerank API
- 简单易用：只需提供 API URL 和密钥
- 用户信息传递：支持将用户信息头传递给外部服务

环境变量:
- RERANKING_MODEL: 重排序模型名称（可选）
- EXTERNAL_RERANKING_API_KEY: 外部 API 密钥
- EXTERNAL_RERANKING_API_URL: 外部 API URL
"""

import logging
import requests
from typing import Optional, List, Tuple
from urllib.parse import quote


from open_webui.env import ENABLE_FORWARD_USER_INFO_HEADERS, REQUESTS_VERIFY
from open_webui.retrieval.models.base_reranker import BaseReranker
from open_webui.utils.headers import include_user_info_headers

log = logging.getLogger(__name__)


class ExternalReranker(BaseReranker):
    """
    外部 API 重排序模型实现

    通过 HTTP POST 调用外部兼容的 rerank 服务

    Attributes:
        api_key: API 密钥
        url: 外部服务 URL
        model: 模型名称
        timeout: 请求超时时间
    """

    def __init__(
        self,
        api_key: str,
        url: str = 'http://localhost:8080/v1/rerank',
        model: str = 'reranker',
        timeout: Optional[int] = None,
    ):
        """
        初始化外部重排序模型

        Args:
            api_key: API 密钥
            url: 外部服务 URL
            model: 模型名称
            timeout: 请求超时时间（秒）
        """
        self.api_key = api_key
        self.url = url
        self.model = model
        self.timeout = timeout

    def predict(self, sentences: List[Tuple[str, str]], user=None) -> Optional[List[float]]:
        """
        通过外部 API 预测相关性分数

        Args:
            sentences: (查询, 文档) 元组列表
            user: 可选的用户信息（用于传递用户头）

        Returns:
            浮点数分数列表，或失败时返回 None
        """
        query = sentences[0][0]
        docs = [i[1] for i in sentences]

        payload = {
            'model': self.model,
            'query': query,
            'documents': docs,
            'top_n': len(docs),
        }

        try:
            log.info(f'ExternalReranker:predict:model {self.model}')
            log.info(f'ExternalReranker:predict:query {query}')

            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}',
            }

            if ENABLE_FORWARD_USER_INFO_HEADERS and user:
                headers = include_user_info_headers(headers, user)

            r = requests.post(
                f'{self.url}',
                headers=headers,
                json=payload,
                timeout=self.timeout,
                verify=REQUESTS_VERIFY,
            )

            r.raise_for_status()
            data = r.json()

            if 'results' in data:
                sorted_results = sorted(data['results'], key=lambda x: x['index'])
                return [result['relevance_score'] for result in sorted_results]
            else:
                log.error('No results found in external reranking response')
                return None

        except Exception as e:
            log.exception(f'Error in external reranking: {e}')
            return None