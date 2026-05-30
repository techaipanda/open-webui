"""
Google Programmable Search Engine 模块
功能: 使用 Google Custom Search API 进行网络搜索

概述:
Google PSE (Programmable Search Engine) 是 Google 提供的自定义搜索引擎服务。
通过配置 Search Engine ID 和 API Key，可以获取搜索结果。

特点:
- 支持分页（每页最多 10 条结果，最多 100 条）
- 支持自定义搜索过滤
- 结果包含链接、标题和摘要

配置步骤:
1. 在 https://programmablesearchengine.google.com/ 创建搜索引擎
2. 获取 Search Engine ID (cx)
3. 在 Google Cloud Console 获取 API Key

环境变量:
- GOOGLE_PSE_API_KEY: Google API 密钥
- GOOGLE_PSE_SEARCH_ENGINE_ID: 搜索引擎 ID
"""

import logging
from typing import Optional

import requests
from open_webui.retrieval.web.main import SearchResult, get_filtered_results

log = logging.getLogger(__name__)


def search_google_pse(
    api_key: str,
    search_engine_id: str,
    query: str,
    count: int,
    filter_list: Optional[list[str]] = None,
    referer: Optional[str] = None,
) -> list[SearchResult]:
    """
    使用 Google Programmable Search API 搜索并返回结果

    Args:
        api_key: Google API 密钥
        search_engine_id: Programmable Search Engine ID (cx)
        query: 搜索查询字符串
        count: 返回结果数量（最多 100 条，Google PSE 每页最多 10 条）
        filter_list: 可选的域名过滤列表
        referer: 可选的 Referer 头（用于 API 限制）

    Returns:
        SearchResult 对象列表
    """
    url = 'https://www.googleapis.com/customsearch/v1'

    headers = {'Content-Type': 'application/json'}
    if referer:
        headers['Referer'] = referer

    all_results = []
    start_index = 1  # Google PSE start parameter is 1-based

    while count > 0:
        num_results_this_page = min(count, 10)  # Google PSE max results per page is 10
        params = {
            'cx': search_engine_id,
            'q': query,
            'key': api_key,
            'num': num_results_this_page,
            'start': start_index,
        }
        response = requests.request('GET', url, headers=headers, params=params)
        response.raise_for_status()
        json_response = response.json()
        results = json_response.get('items', [])
        if results:  # check if results are returned. If not, no more pages to fetch.
            all_results.extend(results)
            count -= len(results)  # Decrement count by the number of results fetched in this page.
            start_index += 10  # Increment start index for the next page
        else:
            break  # No more results from Google PSE, break the loop

    if filter_list:
        all_results = get_filtered_results(all_results, filter_list)

    return [
        SearchResult(
            link=result['link'],
            title=result.get('title'),
            snippet=result.get('snippet'),
        )
        for result in all_results
    ]