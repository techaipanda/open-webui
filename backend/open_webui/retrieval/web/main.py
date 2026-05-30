"""
网络搜索与抓取模块
功能: 提供网页搜索、URL 内容抓取和安全验证功能

主要功能:
- 搜索结果过滤: 根据域名和 IP 地址过滤搜索结果
- URL 验证: 验证 URL 格式和可访问性
- 安全检查: 防止恶意域名和钓鱼网站

支持的搜索后端:
- Bing: 微软搜索服务
- DuckDuckGo: 隐私保护搜索引擎
- Google PSE: Google Programmable Search Engine
- Exa: AI 增强型搜索引擎
- FireCrawl: 网页抓取服务
- Jina: AI 搜索和网页抓取
- SearXNG: 开源元搜索引擎
- Sogou: 搜狗搜索
- Tavily: 专为 AI 设计的搜索 API
- Perplexity: AI 驱动的问答搜索

依赖:
- validators: URL 格式验证
- playwright: 网页渲染和抓取
"""

import validators

from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel

from open_webui.retrieval.web.utils import resolve_hostname
from open_webui.utils.misc import is_string_allowed


def get_filtered_results(results, filter_list):
    """
    过滤搜索结果

    根据允许的域名列表过滤搜索结果，支持:
    - 域名精确匹配
    - IP 地址匹配（IPv4 和 IPv6）
    - 子域名通配

    Args:
        results: 原始搜索结果列表，每个结果包含 url/link/href 字段
        filter_list: 允许的域名/IP 地址列表

    Returns:
        过滤后的搜索结果列表
    """
    if not filter_list:
        return results

    filtered_results = []

    for result in results:
        url = result.get('url') or result.get('link', '') or result.get('href', '')
        if not validators.url(url):
            continue

        domain = urlparse(url).netloc
        if not domain:
            continue

        hostnames = [domain]

        try:
            ipv4_addresses, ipv6_addresses = resolve_hostname(domain)
            hostnames.extend(ipv4_addresses)
            hostnames.extend(ipv6_addresses)
        except Exception:
            pass

        if is_string_allowed(hostnames, filter_list):
            filtered_results.append(result)
            continue

    return filtered_results


class SearchResult(BaseModel):
    """
    搜索结果数据模型

    Attributes:
        link: 搜索结果链接 URL
        title: 搜索结果标题（可选）
        snippet: 搜索结果摘要/片段（可选）
    """
    link: str
    title: Optional[str]
    snippet: Optional[str]