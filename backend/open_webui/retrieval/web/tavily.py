"""
Tavily 搜索模块
功能: 使用 Tavily AI 搜索引擎进行网络搜索

概述:
Tavily 是一个专为 AI 应用设计的搜索 API，提供:
- 快速搜索响应
- 结构化结果
- 搜索结果去重和排名

特点:
- 专为 RAG 和 AI 应用优化
- 返回清晰的搜索结果摘要
- 支持域名过滤

环境变量:
- TAVILY_API_KEY: Tavily API 密钥
"""

import logging
from typing import Optional

import requests
from open_webui.retrieval.web.main import SearchResult, get_filtered_results

log = logging.getLogger(__name__)


def search_tavily(
    api_key: str,
    query: str,
    count: int,
    filter_list: Optional[list[str]] = None,
) -> list[SearchResult]:
    """
    使用 Tavily API 搜索并返回结果

    Args:
        api_key: Tavily API 密钥
        query: 搜索查询字符串
        count: 返回结果数量
        filter_list: 可选的域名过滤列表

    Returns:
        SearchResult 对象列表
    """
    url = 'https://api.tavily.com/search'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}',
    }
    data = {'query': query, 'max_results': count}
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()

    json_response = response.json()

    results = json_response.get('results', [])
    if filter_list:
        results = get_filtered_results(results, filter_list)

    return [
        SearchResult(
            link=result['url'],
            title=result.get('title', ''),
            snippet=result.get('content'),
        )
        for result in results
    ]