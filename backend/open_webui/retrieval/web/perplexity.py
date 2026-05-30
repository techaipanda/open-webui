"""
Perplexity 搜索模块
功能: 使用 Perplexity AI API 进行网络搜索

概述:
Perplexity 是一个 AI 驱动的问答搜索引擎，基于大语言模型。
提供结构化的搜索结果和引用来源。

支持的模型:
- sonar: 标准搜索模型
- sonar-pro: 专业搜索模型
- sonar-reasoning: 推理搜索模型
- sonar-reasoning-pro: 专业推理搜索模型
- sonar-deep-research: 深度研究模型

特点:
- 使用 Chat Completions 格式
- 支持搜索上下文级别（low/medium/high）
- 返回引用来源列表

环境变量:
- PERPLEXITY_API_KEY: Perplexity API 密钥
"""

import logging
from typing import Optional, Literal
import requests

from open_webui.retrieval.web.main import SearchResult, get_filtered_results

MODELS = Literal[
    'sonar',
    'sonar-pro',
    'sonar-reasoning',
    'sonar-reasoning-pro',
    'sonar-deep-research',
]
SEARCH_CONTEXT_USAGE_LEVELS = Literal['low', 'medium', 'high']


log = logging.getLogger(__name__)


def search_perplexity(
    api_key: str,
    query: str,
    count: int,
    filter_list: Optional[list[str]] = None,
    model: MODELS = 'sonar',
    search_context_usage: SEARCH_CONTEXT_USAGE_LEVELS = 'medium',
) -> list[SearchResult]:
    """
    使用 Perplexity API 搜索并返回结果

    Args:
        api_key: Perplexity API 密钥
        query: 搜索查询字符串
        count: 返回结果数量
        filter_list: 可选的域名过滤列表
        model: 使用的 Perplexity 模型
        search_context_usage: 搜索上下文使用级别

    Returns:
        SearchResult 对象列表
    """
    # Handle PersistentConfig object
    if hasattr(api_key, '__str__'):
        api_key = str(api_key)

    try:
        url = 'https://api.perplexity.ai/chat/completions'

        # Create payload for the API call
        payload = {
            'model': model,
            'messages': [
                {
                    'role': 'system',
                    'content': 'You are a search assistant. Provide factual information with citations.',
                },
                {'role': 'user', 'content': query},
            ],
            'temperature': 0.2,  # Lower temperature for more factual responses
            'stream': False,
            'web_search_options': {
                'search_context_usage': search_context_usage,
            },
        }

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }

        # Make the API request
        response = requests.request('POST', url, json=payload, headers=headers)

        # Parse the JSON response
        json_response = response.json()

        # Extract citations from the response
        citations = json_response.get('citations', [])

        # Create search results from citations
        results = []
        for i, citation in enumerate(citations[:count]):
            # Extract content from the response to use as snippet
            content = ''
            if 'choices' in json_response and json_response['choices']:
                if i == 0:
                    content = json_response['choices'][0]['message']['content']

            result = {'link': citation, 'title': f'Source {i + 1}', 'snippet': content}
            results.append(result)

        if filter_list:
            results = get_filtered_results(results, filter_list)

        return [
            SearchResult(link=result['link'], title=result['title'], snippet=result['snippet'])
            for result in results[:count]
        ]

    except Exception as e:
        log.error(f'Error searching with Perplexity API: {e}')
        return []