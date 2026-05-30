"""
Exa 搜索模块
功能: 使用 Exa AI 搜索引擎进行网络搜索

概述:
Exa 是一个 AI 增强型搜索引擎，支持神经搜索和关键词搜索。
通过自然语言查询找到相关网页，并提供全文内容。

特点:
- 自动搜索类型（auto）：根据查询自动选择关键词或神经搜索
- 域名过滤：可以指定只返回特定域名的结果
- 高亮显示：返回搜索结果中的文本片段

环境变量:
- EXA_API_KEY: Exa API 密钥
"""

import logging
from dataclasses import dataclass
from typing import Optional

import requests
from open_webui.retrieval.web.main import SearchResult

log = logging.getLogger(__name__)

EXA_API_BASE = 'https://api.exa.ai'


@dataclass
class ExaResult:
    """
    Exa 搜索结果数据类

    Attributes:
        url: 结果 URL
        title: 结果标题
        text: 结果正文摘要
    """
    url: str
    title: str
    text: str


def search_exa(
    api_key: str,
    query: str,
    count: int,
    filter_list: Optional[list[str]] = None,
) -> list[SearchResult]:
    """
    使用 Exa API 搜索并返回结果

    Args:
        api_key: Exa API 密钥
        query: 搜索查询字符串（支持自然语言）
        count: 返回结果数量
        filter_list: 可选的域名过滤列表

    Returns:
        SearchResult 对象列表
    """
    log.info(f'Searching with Exa for query: {query}')

    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}

    payload = {
        'query': query,
        'numResults': count or 5,
        'includeDomains': filter_list,
        'contents': {'text': True, 'highlights': True},
        'type': 'auto',  # Use the auto search type (keyword or neural)
    }

    try:
        response = requests.post(f'{EXA_API_BASE}/search', headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

        results = []
        for result in data['results']:
            results.append(
                ExaResult(
                    url=result['url'],
                    title=result['title'],
                    text=result['text'],
                )
            )

        log.info(f'Found {len(results)} results')
        return [
            SearchResult(
                link=result.url,
                title=result.title,
                snippet=result.text,
            )
            for result in results
        ]
    except Exception as e:
        log.error(f'Error searching Exa: {e}')
        return []