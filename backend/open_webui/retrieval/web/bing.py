"""
Bing 搜索模块
功能: 使用 Microsoft Bing Search API 进行网络搜索

概述:
Bing 搜索是微软提供的商业搜索引擎服务，支持多种语言和地区设置。
本模块封装了 Bing Web Search API，提供安全过滤、结果格式化等功能。

API 文档: https://docs.microsoft.com/en-us/bing/search-apis/bing-web-search/overview

环境变量:
- BING_SEARCH_API_KEY: Bing API 订阅密钥
- BING_SEARCH_ENDPOINT: API 端点 URL（可选，默认使用 standard endpoint）
"""

import logging
import os
from pprint import pprint
from typing import Optional
import requests
from open_webui.retrieval.web.main import SearchResult, get_filtered_results
import argparse

log = logging.getLogger(__name__)
"""
Documentation: https://docs.microsoft.com/en-us/bing/search-apis/bing-web-search/overview
"""


def search_bing(
    subscription_key: str,
    endpoint: str,
    locale: str,
    query: str,
    count: int,
    filter_list: Optional[list[str]] = None,
) -> list[SearchResult]:
    """
    使用 Bing API 搜索并返回结果

    Args:
        subscription_key: Bing API 订阅密钥
        endpoint: Bing Search API 端点 URL
        locale: 地区/市场代码（如 en-US, zh-CN）
        query: 搜索查询字符串
        count: 返回结果数量
        filter_list: 可选的域名过滤列表

    Returns:
        SearchResult 对象列表
    """
    mkt = locale
    params = {'q': query, 'mkt': mkt, 'count': count}
    headers = {'Ocp-Apim-Subscription-Key': subscription_key}

    try:
        response = requests.get(endpoint, headers=headers, params=params)
        response.raise_for_status()
        json_response = response.json()
        results = json_response.get('webPages', {}).get('value', [])
        if filter_list:
            results = get_filtered_results(results, filter_list)
        return [
            SearchResult(
                link=result['url'],
                title=result.get('name'),
                snippet=result.get('snippet'),
            )
            for result in results
        ]
    except Exception as ex:
        log.error(f'Error: {ex}')
        raise ex


def main():
    """
    命令行入口: 从命令行进行 Bing 搜索测试

    用法:
        python bing.py "搜索词" --count 10 --locale en-US
    """
    parser = argparse.ArgumentParser(description='Search Bing from the command line.')
    parser.add_argument(
        'query',
        type=str,
        default='Top 10 international news today',
        help='The search query.',
    )
    parser.add_argument('--count', type=int, default=10, help='Number of search results to return.')
    parser.add_argument('--filter', nargs='*', help='List of filters to apply to the search results.')
    parser.add_argument(
        '--locale',
        type=str,
        default='en-US',
        help='The locale to use for the search, maps to market in api',
    )

    args = parser.parse_args()

    results = search_bing(args.locale, args.query, args.count, args.filter)
    pprint(results)