"""
Jina 搜索模块
功能: 使用 Jina AI 搜索和网页抓取服务

概述:
Jina 是一个 AI 搜索服务，提供:
- 网络搜索：返回搜索结果摘要
- 网页抓取：提取网页内容为 Markdown
- AI 增强：使用 AI 模型优化搜索和抓取结果

特点:
- 默认不保留图片（X-Retain-Images: none）
- 返回结构化 JSON 结果
- 支持自定义 API 端点

环境变量:
- JINA_API_KEY: Jina API 密钥
"""

import logging

import requests
from open_webui.retrieval.web.main import SearchResult
from yarl import URL

log = logging.getLogger(__name__)


def search_jina(api_key: str, query: str, count: int, base_url: str = '') -> list[SearchResult]:
    """
    使用 Jina API 搜索并返回结果

    Args:
        api_key: Jina API 密钥
        query: 搜索查询字符串
        count: 返回结果数量（最多 10 条）
        base_url: 可选的自定义 API 端点

    Returns:
        SearchResult 对象列表
    """
    jina_search_endpoint = base_url if base_url else 'https://s.jina.ai/'

    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': api_key,
        'X-Retain-Images': 'none',
    }

    payload = {'q': query, 'count': count if count <= 10 else 10}

    url = str(URL(jina_search_endpoint))
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    data = response.json()

    results = []
    for result in data['data']:
        results.append(
            SearchResult(
                link=result['url'],
                title=result.get('title'),
                snippet=result.get('content'),
            )
        )

    return results