"""
DuckDuckGo 搜索模块
功能: 使用 DuckDuckGo 搜索引擎进行隐私保护的网络搜索

概述:
DuckDuckGo 是一个注重隐私的搜索引擎，不会追踪或存储用户个人信息。
本模块使用 ddgs 库（基于 DuckDuckGo 非官方 API）进行搜索，支持多种后端。

特点:
- 默认不追踪用户
- 支持多种搜索后端（auto, duckduckgo, google, brave 等）
- 支持代理配置
- 支持并发请求控制

环境变量:
- HTTPS_PROXY / HTTP_PROXY: 代理设置（自动从环境变量读取）
"""

import logging
import urllib.request
from typing import Optional

from open_webui.retrieval.web.main import SearchResult, get_filtered_results
from ddgs import DDGS
from ddgs.exceptions import RatelimitException

log = logging.getLogger(__name__)


def search_duckduckgo(
    query: str,
    count: int,
    filter_list: Optional[list[str]] = None,
    concurrent_requests: Optional[int] = None,
    backend: Optional[str] = 'auto',
) -> list[SearchResult]:
    """
    使用 DuckDuckGo API 搜索并返回结果

    Args:
        query: 搜索查询字符串
        count: 返回结果数量
        filter_list: 可选的域名过滤列表
        concurrent_requests: 并发请求数（可选）
        backend: 搜索后端类型（auto, duckduckgo, google, brave 等）

    Returns:
        SearchResult 对象列表
    """
    # The ddgs library (primp-based) does not auto-detect proxy env vars.
    # Resolve via stdlib getproxies() — same pattern as the other loaders.
    env_proxies = urllib.request.getproxies()
    proxy = env_proxies.get('https') or env_proxies.get('http')
    search_results = []
    with DDGS(proxy=proxy) as ddgs:
        if concurrent_requests:
            ddgs.threads = concurrent_requests

        # Use the ddgs.text() method to perform the search
        try:
            kwargs = {'safesearch': 'moderate', 'max_results': count}
            if backend and backend != 'auto':
                kwargs['backend'] = backend
            results = ddgs.text(query, **kwargs)
            search_results = results if results is not None else []
        except RatelimitException as e:
            log.error(f'RatelimitException: {e}')
            search_results = []
    if filter_list:
        search_results = get_filtered_results(search_results, filter_list)

    # Return the list of search results
    return [
        SearchResult(
            link=result['href'],
            title=result.get('title'),
            snippet=result.get('body'),
        )
        for result in search_results
    ]