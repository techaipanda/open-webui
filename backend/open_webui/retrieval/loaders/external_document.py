"""
外部文档加载器模块
功能: 通过外部服务加载和处理文档

概述:
外部文档加载器允许使用自定义的文档处理服务。
通过配置服务 URL 和 API 密钥，可以集成任何兼容的文档处理 API。

请求格式:
- Method: PUT
- URL: {external_url}/process
- Headers: Content-Type, Authorization, X-Filename
- Body: 文件二进制数据

响应格式:
- JSON: {page_content: string, metadata: object}
- 或 JSON 数组: [{page_content, metadata}, ...]

特点:
- 支持自定义 MIME 类型
- 文件名通过 X-Filename 头传递
- 用户信息头传递支持

环境变量:
- EXTERNAL_DOCUMENT_LOADER_URL: 外部服务 URL
- EXTERNAL_DOCUMENT_LOADER_API_KEY: API 密钥
"""

import requests
import logging, os
from typing import Iterator, List, Union
from urllib.parse import quote

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document
from open_webui.utils.headers import include_user_info_headers

log = logging.getLogger(__name__)


class ExternalDocumentLoader(BaseLoader):
    """
    外部文档加载器

    通过外部 API 服务加载和解析文档

    Attributes:
        url: 外部服务 URL
        api_key: API 密钥
        file_path: 要处理的文档路径
        mime_type: 可选的 MIME 类型
        user: 可选的用户信息
    """

    def __init__(
        self,
        file_path,
        url: str,
        api_key: str,
        mime_type=None,
        user=None,
        **kwargs,
    ) -> None:
        """
        初始化外部文档加载器

        Args:
            file_path: 文档路径
            url: 外部服务 URL
            api_key: API 密钥
            mime_type: 可选的 MIME 类型
            user: 可选的用户信息
            **kwargs: 其他参数
        """
        self.url = url
        self.api_key = api_key

        self.file_path = file_path
        self.mime_type = mime_type

        self.user = user

    def load(self) -> List[Document]:
        """
        加载并解析文档

        向外部服务发送 PUT 请求获取处理结果

        Returns:
            Document 对象列表

        Raises:
            Exception: 请求失败或解析错误
        """
        with open(self.file_path, 'rb') as f:
            data = f.read()

        headers = {}
        if self.mime_type is not None:
            headers['Content-Type'] = self.mime_type

        if self.api_key is not None:
            headers['Authorization'] = f'Bearer {self.api_key}'

        try:
            headers['X-Filename'] = quote(os.path.basename(self.file_path))
        except Exception:
            pass

        if self.user is not None:
            headers = include_user_info_headers(headers, self.user)

        url = self.url
        if url.endswith('/'):
            url = url[:-1]

        try:
            response = requests.put(f'{url}/process', data=data, headers=headers)
        except Exception as e:
            log.error(f'Error connecting to endpoint: {e}')
            raise Exception(f'Error connecting to endpoint: {e}')

        if response.ok:
            response_data = response.json()
            if response_data:
                if isinstance(response_data, dict):
                    return [
                        Document(
                            page_content=response_data.get('page_content'),
                            metadata=response_data.get('metadata'),
                        )
                    ]
                elif isinstance(response_data, list):
                    documents = []
                    for document in response_data:
                        documents.append(
                            Document(
                                page_content=document.get('page_content'),
                                metadata=document.get('metadata'),
                            )
                        )
                    return documents
                else:
                    raise Exception('Error loading document: Unable to parse content')

            else:
                raise Exception('Error loading document: No content returned')
        else:
            raise Exception(f'Error loading document: {response.status_code} {response.text}')