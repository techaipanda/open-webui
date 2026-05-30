"""
外部搜索模块
功能: 通过外部搜索服务进行网络搜索

概述:
外部搜索允许使用自定义的搜索服务 API。
通过配置外部搜索 URL 和 API 密钥，可以集成任何兼容的搜索服务。

请求格式:
- URL: 外部搜索服务 endpoint
- Method: POST
- Headers: 包含 Authorization 和 User-Agent
- Body: JSON 格式 {query, count}

响应格式:
- JSON 数组，每个元素包含 link, title, snippet

特点:
- 支持用户信息头传递
- 支持会话信息传递（chat_id）
- 支持域名过滤

环境变量:
- EXTERNAL_WEB_LOADER_URL: 外部搜索服务 URL
- EXTERNAL_WEB_LOADER_API_KEY: 外部搜索服务 API 密钥
"""

import logging
from typing import Optional, List

import requests

from fastapi import Request


from open_webui.retrieval.web.main import SearchResult, get_filtered_results
from open_webui.utils.headers import include_user_info_headers
from open_webui.env import FORWARD_SESSION_INFO_HEADER_CHAT_ID

log = logging.getLogger(__name__)


def search_external(
    request: Request,
    external_url: str,
    external_api_key: str,
    query: str,
    count: int,
    filter_list: Optional[List[str]] = None,
    user=None,
) -> List[SearchResult]:
    """
    使用外部搜索服务搜索并返回结果

    Args:
        request: FastAPI 请求对象
        external_url: 外部搜索服务 URL
        external_api_key: API 密钥
        query: 搜索查询字符串
        count: 返回结果数量
        filter_list: 可选的域名过滤列表
        user: 可选的用户信息

    Returns:
        SearchResult 对象列表
    """
    try:
        headers = {
            'User-Agent': 'Open WebUI (https://github.com/open-webui/open-webui) RAG Bot',
            'Authorization': f'Bearer {external_api_key}',
        }
        headers = include_user_info_headers(headers, user)

        chat_id = getattr(request.state, 'chat_id', None)
        if chat_id:
            headers[FORWARD_SESSION_INFO_HEADER_CHAT_ID] = str(chat_id)

        response = requests.post(
            external_url,
            headers=headers,
            json={
                'query': query,
                'count': count,
            },
        )
        response.raise_for_status()
        results = response.json()
        if filter_list:
            results = get_filtered_results(results, filter_list)
        results = [
            SearchResult(
                link=result.get('link'),
                title=result.get('title'),
                snippet=result.get('snippet'),
            )
            for result in results[:count]
        ]
        log.info(f'External search results: {results}')
        return results
    except Exception as e:
        log.error(f'Error in External search: {e}')
        return []