"""
外部网页加载器模块
功能: 通过外部服务加载和处理网页内容

概述:
外部网页加载器允许使用自定义的网页处理服务。
通过配置服务 URL 和 API 密钥，可以集成任何兼容的网页提取 API。

请求格式:
- Method: POST
- URL: {external_url}
- Headers: User-Agent, Authorization
- Body: JSON {urls: [...]}

响应格式:
- JSON 数组: [{page_content, metadata}, ...]

特点:
- 批量处理：支持同时处理多个 URL
- 失败容忍：跳过失败的 URL 继续处理

环境变量:
- EXTERNAL_WEB_LOADER_URL: 外部服务 URL
- EXTERNAL_WEB_LOADER_API_KEY: API 密钥
"""

import requests
import logging
from typing import Iterator, List, Union

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

log = logging.getLogger(__name__)


class ExternalWebLoader(BaseLoader):
    """
    外部网页加载器

    通过外部 API 服务加载网页内容

    Attributes:
        external_url: 外部服务 URL
        external_api_key: API 密钥
        urls: URL 列表
        continue_on_failure: 失败是否继续
    """

    def __init__(
        self,
        web_paths: Union[str, List[str]],
        external_url: str,
        external_api_key: str,
        continue_on_failure: bool = True,
        **kwargs,
    ) -> None:
        """
        初始化外部网页加载器

        Args:
            web_paths: 单个 URL 或 URL 列表
            external_url: 外部服务 URL
            external_api_key: API 密钥
            continue_on_failure: 失败是否继续
            **kwargs: 其他参数
        """
        self.external_url = external_url
        self.external_api_key = external_api_key
        self.urls = web_paths if isinstance(web_paths, list) else [web_paths]
        self.continue_on_failure = continue_on_failure

    def lazy_load(self) -> Iterator[Document]:
        """
        懒加载文档

        批量处理 URL，每批 20 个

        Yields:
            Document: 提取的网页内容
        """
        batch_size = 20
        for i in range(0, len(self.urls), batch_size):
            urls = self.urls[i : i + batch_size]
            try:
                response = requests.post(
                    self.external_url,
                    headers={
                        'User-Agent': 'Open WebUI (https://github.com/open-webui/open-webui) External Web Loader',
                        'Authorization': f'Bearer {self.external_api_key}',
                    },
                    json={
                        'urls': urls,
                    },
                )
                response.raise_for_status()
                results = response.json()
                for result in results:
                    yield Document(
                        page_content=result.get('page_content', ''),
                        metadata=result.get('metadata', {}),
                    )
            except Exception as e:
                if self.continue_on_failure:
                    log.error(f'Error extracting content from batch {urls}: {e}')
                else:
                    raise e