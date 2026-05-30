"""
Firecrawl 网页抓取和搜索模块
功能: 使用 Firecrawl API 进行网页抓取和网络搜索

概述:
Firecrawl 是一个网页抓取服务，支持:
- 单页抓取（scrape）：提取单个页面的内容
- 站点爬取（crawl）：递归抓取整个网站
- 地图生成（map）：获取站点结构

输出格式:
- Markdown: 适合 RAG 处理
- HTML: 保留原始结构
- JSON: 结构化数据

环境变量:
- FIRECRAWL_API_KEY: Firecrawl API 密钥
- FIRECRAWL_API_BASE_URL: API 基础 URL（可选）
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

import requests
from langchain_core.documents import Document

if TYPE_CHECKING:
    from open_webui.retrieval.web.main import SearchResult

log = logging.getLogger(__name__)

DEFAULT_FIRECRAWL_API_BASE_URL = 'https://api.firecrawl.dev'
FIRECRAWL_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
FIRECRAWL_MAX_RETRIES = 2


def build_firecrawl_url(base_url: str | None, path: str) -> str:
    """
    构建 Firecrawl API URL

    Args:
        base_url: 基础 URL（None 使用默认）
        path: API 路径

    Returns:
        完整的 API URL
    """
    base_url = (base_url or DEFAULT_FIRECRAWL_API_BASE_URL).rstrip('/')
    path = path.lstrip('/')

    if base_url.endswith('/v2'):
        return f'{base_url}/{path}'

    return f'{base_url}/v2/{path}'


def build_firecrawl_headers(api_key: str | None) -> dict[str, str]:
    """
    构建 Firecrawl 请求头

    Args:
        api_key: API 密钥（None 使用空字符串）

    Returns:
        包含 Authorization 的请求头字典
    """
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key or ""}',
    }


def get_firecrawl_timeout_seconds(timeout: Any) -> float | None:
    """
    解析超时时间为秒数

    Args:
        timeout: 超时值（可以是字符串数字或 None）

    Returns:
        浮点数秒数或 None
    """
    if timeout in (None, ''):
        return None

    try:
        timeout = float(timeout)
    except (TypeError, ValueError):
        return None

    return timeout if timeout > 0 else None


def get_firecrawl_scrape_timeout_ms(timeout: Any) -> int | None:
    """
    获取 Firecrawl 抓取超时（毫秒）

    Args:
        timeout: 超时值

    Returns:
        毫秒数（限制在 1000-300000 之间）或 None
    """
    timeout_seconds = get_firecrawl_timeout_seconds(timeout)
    if timeout_seconds is None:
        return None

    # Firecrawl v2 expects scrape timeouts in milliseconds.
    return min(300000, max(1000, int(timeout_seconds * 1000)))


def get_firecrawl_client_timeout_seconds(timeout: Any, fallback: float = 60) -> float:
    """
    获取 Firecrawl 客户端超时（秒）

    略高于抓取超时，确保完整处理

    Args:
        timeout: 超时值
        fallback: 默认超时值

    Returns:
        客户端超时秒数
    """
    # Keep the local HTTP timeout slightly above Firecrawl's scrape timeout.
    return (get_firecrawl_timeout_seconds(timeout) or fallback) + 10


def get_firecrawl_retry_delay(headers: Any, attempt: int) -> float:
    """
    计算 Firecrawl 重试延迟

    Args:
        headers: 响应头（包含 Retry-After 时优先使用）
        attempt: 当前重试次数

    Returns:
        延迟秒数（最大 10 秒）
    """
    retry_after = headers.get('Retry-After') if headers else None
    if retry_after:
        try:
            return min(10.0, max(0.0, float(retry_after)))
        except (TypeError, ValueError):
            pass

    return min(8.0, float(2**attempt))


def request_firecrawl_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    json: dict[str, Any] | None = None,
    timeout: float | None = None,
    verify: bool = True,
) -> dict[str, Any]:
    """
    发送 Firecrawl API 请求（带重试）

    Args:
        method: HTTP 方法（GET/POST）
        url: 请求 URL
        headers: 请求头
        json: JSON 请求体
        timeout: 超时秒数
        verify: 是否验证 SSL

    Returns:
        响应 JSON 数据

    Raises:
        requests.exceptions.RequestException: 请求失败
    """
    last_error = None

    for attempt in range(FIRECRAWL_MAX_RETRIES + 1):
        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                json=json,
                timeout=timeout,
                verify=verify,
            )

            if response.status_code in FIRECRAWL_RETRY_STATUS_CODES and attempt < FIRECRAWL_MAX_RETRIES:
                delay = get_firecrawl_retry_delay(response.headers, attempt)
                log.warning(
                    'Firecrawl %s %s returned HTTP %s; retrying in %.1fs',
                    method,
                    url,
                    response.status_code,
                    delay,
                )
                time.sleep(delay)
                continue

            response.raise_for_status()
            return response.json()
        except (requests.ConnectionError, requests.Timeout) as e:
            last_error = e
            if attempt >= FIRECRAWL_MAX_RETRIES:
                break

            delay = get_firecrawl_retry_delay(None, attempt)
            log.warning('Firecrawl %s %s failed; retrying in %.1fs: %s', method, url, delay, e)
            time.sleep(delay)

    if last_error:
        raise last_error

    raise RuntimeError(f'Firecrawl {method} {url} failed without a response')


def get_firecrawl_result_url(result: dict[str, Any]) -> str:
    """
    从 Firecrawl 结果中提取 URL

    尝试多个可能的字段以找到 URL

    Args:
        result: Firecrawl 结果字典

    Returns:
        URL 字符串或空字符串
    """
    metadata = result.get('metadata') or {}
    return (
        result.get('url')
        or result.get('link')
        or metadata.get('url')
        or metadata.get('sourceURL')
        or metadata.get('source_url')
        or ''
    )


def scrape_firecrawl_url(
    firecrawl_url: str,
    firecrawl_api_key: str,
    url: str,
    *,
    verify_ssl: bool = True,
    timeout: Any = None,
    params: dict[str, Any] | None = None,
) -> Document | None:
    """
    使用 Firecrawl 抓取单个 URL

    Args:
        firecrawl_url: Firecrawl API 基础 URL
        firecrawl_api_key: API 密钥
        url: 要抓取的 URL
        verify_ssl: 是否验证 SSL
        timeout: 超时时间
        params: 额外参数

    Returns:
        Document 对象或 None（抓取失败时）
    """
    payload = {
        'url': url,
        'formats': ['markdown'],
        'skipTlsVerification': not verify_ssl,
        'removeBase64Images': True,
        **(params or {}),
    }
    scrape_timeout_ms = get_firecrawl_scrape_timeout_ms(timeout)
    if scrape_timeout_ms is not None:
        payload['timeout'] = scrape_timeout_ms

    response = request_firecrawl_json(
        'POST',
        build_firecrawl_url(firecrawl_url, 'scrape'),
        headers=build_firecrawl_headers(firecrawl_api_key),
        json=payload,
        timeout=get_firecrawl_client_timeout_seconds(timeout),
        verify=verify_ssl,
    )
    data = response.get('data') or {}
    content = data.get('markdown') or ''
    if not isinstance(content, str) or not content.strip():
        return None

    metadata = data.get('metadata') or {}
    document_metadata = {'source': get_firecrawl_result_url(data) or url}
    if metadata.get('title'):
        document_metadata['title'] = metadata['title']
    if metadata.get('description'):
        document_metadata['description'] = metadata['description']

    return Document(page_content=content, metadata=document_metadata)


def search_firecrawl(
    firecrawl_url: str,
    firecrawl_api_key: str,
    query: str,
    count: int,
    filter_list: list[str] | None = None,
) -> list[SearchResult]:
    """
    使用 Firecrawl 搜索功能

    Args:
        firecrawl_url: Firecrawl API 基础 URL
        firecrawl_api_key: API 密钥
        query: 搜索查询
        count: 返回结果数量
        filter_list: 可选的域名过滤列表

    Returns:
        SearchResult 对象列表
    """
    try:
        response = request_firecrawl_json(
            'POST',
            build_firecrawl_url(firecrawl_url, 'search'),
            headers=build_firecrawl_headers(firecrawl_api_key),
            json={
                'query': query,
                'limit': count,
                'timeout': count * 3000,
                'ignoreInvalidURLs': True,
            },
            timeout=count * 3 + 10,
        )
        data = response.get('data') or {}
        results = data.get('web') or []

        if filter_list:
            from open_webui.retrieval.web.main import get_filtered_results

            results = get_filtered_results(results, filter_list)

        from open_webui.retrieval.web.main import SearchResult

        search_results = []
        for result in results[:count]:
            url = get_firecrawl_result_url(result)
            if not url:
                continue

            metadata = result.get('metadata') or {}
            search_results.append(
                SearchResult(
                    link=url,
                    title=result.get('title') or metadata.get('title'),
                    snippet=result.get('description') or result.get('snippet') or metadata.get('description'),
                )
            )

        log.info(f'FireCrawl search results: {search_results}')
        return search_results
    except Exception as e:
        log.error(f'Error in FireCrawl search: {e}')
        return []