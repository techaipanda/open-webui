"""
SearXNG 搜索模块
功能: 使用 SearXNG 元搜索引擎进行网络搜索

概述:
SearXNG 是一个开源的元搜索引擎，聚合多个搜索引擎的结果。
它不追踪用户，提供隐私保护的搜索体验。

特点:
- 开源且自托管
- 支持多种搜索引擎聚合
- 可配置的语言、时间范围、类别过滤
- 不追踪用户行为

配置:
需要在 config.yaml 中配置 SearXNG 实例 URL

参数说明:
- language: 语言过滤（如 "all", "en-US", "zh-CN"）
- safesearch: 安全搜索过滤（0=关闭, 1=中等, 2=严格）
- time_range: 时间范围（如 "2023-04-05..today" 或 "all-time"）
- categories: 搜索类别（如 "general", "news", "science"）
"""

import logging
from typing import Optional

import requests
from open_webui.retrieval.web.main import SearchResult, get_filtered_results

log = logging.getLogger(__name__)


def search_searxng(
    query_url: str,
    query: str,
    count: int,
    filter_list: Optional[list[str]] = None,
    **kwargs,
) -> list[SearchResult]:
    """
    使用 SearXNG 搜索并返回结果

    Args:
        query_url: SearXNG 服务器基础 URL
        query: 搜索查询字符串
        count: 返回结果数量
        filter_list: 可选的域名过滤列表

    Keyword Args:
        language: 语言过滤（默认 "all"）
        safesearch: 安全搜索过滤（默认 1=中等）
        time_range: 时间范围过滤（默认空=全部）
        categories: 搜索类别列表（默认空=全部）

    Returns:
        SearchResult 对象列表（按相关性降序排列）

    Raises:
        requests.exceptions.RequestException: 请求失败
    """

    # Default values for optional parameters are provided as empty strings or None when not specified.
    language = kwargs.get('language', 'all').strip().rstrip(',')
    safesearch = kwargs.get('safesearch', '1')
    time_range = kwargs.get('time_range', '')
    categories = ''.join(kwargs.get('categories', []))

    params = {
        'q': query,
        'format': 'json',
        'pageno': 1,
        'safesearch': safesearch,
        'language': language,
        'time_range': time_range,
        'categories': categories,
        'theme': 'simple',
        'image_proxy': 0,
    }

    # Legacy query format
    if '<query>' in query_url:
        # Strip all query parameters from the URL
        query_url = query_url.split('?')[0]

    log.debug(f'searching {query_url}')

    response = requests.get(
        query_url,
        headers={
            'User-Agent': 'Open WebUI (https://github.com/open-webui/open-webui) RAG Bot',
            'Accept': 'text/html',
            'Accept-Encoding': 'gzip, deflate',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
        },
        params=params,
    )

    response.raise_for_status()  # Raise an exception for HTTP errors.

    json_response = response.json()
    results = json_response.get('results', [])
    sorted_results = sorted(results, key=lambda x: x.get('score', 0), reverse=True)
    if filter_list:
        sorted_results = get_filtered_results(sorted_results, filter_list)
    return [
        SearchResult(link=result['url'], title=result.get('title'), snippet=result.get('content'))
        for result in sorted_results[:count]
    ]