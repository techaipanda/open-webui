"""
PaddleOCR-VL 文档加载器模块
功能: 使用 PaddleOCR-VL API 从 PDF/图片中提取文本

概述:
PaddleOCR-VL 是飞桨 OCR 的视觉语言版本，专注于文档结构识别和文字提取。
支持 PDF 和常见图片格式（PNG, JPG, JPEG, BMP, TIFF, WEBP）。

功能:
- 布局分析：识别文档中的标题、段落、表格等区域
- 文字识别：提取各区域中的文字内容
- 表格识别：处理表格结构（可选）
- 方向分类：检测并修正文档方向（可选）

输出:
- Markdown 格式的文本内容
- 每页作为独立 Document

环境变量:
- PADDLEOCR_VL_API_URL: PaddleOCR-VL API 服务地址
- PADDLEOCR_VL_TOKEN: API 访问令牌
"""

import base64
import os
import requests
import logging
import sys
from typing import List

from langchain_core.documents import Document
from open_webui.env import GLOBAL_LOG_LEVEL

logging.basicConfig(stream=sys.stdout, level=GLOBAL_LOG_LEVEL)
log = logging.getLogger(__name__)


class PaddleOCRVLLoader:
    """
    PaddleOCR-VL 文档加载器

    使用 PaddleOCR-VL API 提取 PDF 或图片中的文本内容

    Attributes:
        api_url: API 服务地址
        token: API 访问令牌
        file_path: 要处理的文件的路径
        file_name: 文件名（从 file_path 提取）
    """

    def __init__(
        self,
        api_url: str,
        token: str,
        file_path: str,
    ):
        """
        初始化 PaddleOCR-VL 加载器

        Args:
            api_url: PaddleOCR-VL API 地址
            token: API 访问令牌
            file_path: 要处理的文档路径

        Raises:
            ValueError: API URL 或 token 为空
            FileNotFoundError: 文件不存在
        """
        if not api_url or not token:
            raise ValueError('PaddleOCR-vl API URL and Token are required.')
        if not os.path.exists(file_path):
            raise FileNotFoundError(f'File not found at {file_path}')

        self.api_url = api_url.rstrip('/')
        self.token = token
        self.file_path = file_path
        self.file_name = os.path.basename(file_path)

    def load(self) -> List[Document]:
        """
        加载并处理文档

        调用 PaddleOCR-VL API 进行布局分析和文字识别

        Returns:
            Document 对象列表，每个页面一个 Document
        """
        log.info(f'Processing with PaddleOCR-vl: {self.file_path}')

        try:
            with open(self.file_path, 'rb') as file:
                file_bytes = file.read()
                file_data = base64.b64encode(file_bytes).decode('ascii')
        except Exception as e:
            log.error(f'Failed to read file {self.file_path}: {e}')
            raise

        headers = {'Authorization': f'token {self.token}', 'Content-Type': 'application/json'}

        # Detect fileType based on file extension
        ext = self.file_path.lower().split('.')[-1]
        image_extensions = ['png', 'jpg', 'jpeg', 'bmp', 'tiff', 'webp']
        file_type = 1 if ext in image_extensions else 0

        payload = {
            'file': file_data,
            'fileType': file_type,
            'useDocOrientationClassify': False,
            'useDocUnwarping': False,
            'useChartRecognition': False,
        }

        try:
            response = requests.post(f'{self.api_url}/layout-parsing', json=payload, headers=headers)
            response.raise_for_status()

            result = response.json().get('result', {})
            layout_results = result.get('layoutParsingResults', [])

            documents = []
            total_pages = len(layout_results)
            skipped_pages = 0

            for i, res in enumerate(layout_results):
                markdown_text = res.get('markdown', {}).get('text', '')

                if isinstance(markdown_text, str):
                    cleaned_content = markdown_text.strip()
                else:
                    cleaned_content = str(markdown_text).strip()

                if not cleaned_content:
                    skipped_pages += 1
                    continue

                documents.append(
                    Document(
                        page_content=cleaned_content,
                        metadata={
                            'page': i,
                            'page_label': i + 1,
                            'total_pages': total_pages,
                            'file_name': self.file_name,
                            'processing_engine': 'paddleocr-vl',
                        },
                    )
                )

            if skipped_pages > 0:
                log.info(f'PaddleOCR-vl: Processed {len(documents)} pages, skipped {skipped_pages} empty pages.')

            if not documents:
                log.warning('No valid text content found by PaddleOCR-vl.')
                return [
                    Document(
                        page_content='No valid text content found in document',
                        metadata={
                            'error': 'no_valid_pages',
                            'file_name': self.file_name,
                            'processing_engine': 'paddleocr-vl',
                        },
                    )
                ]

            return documents

        except Exception as e:
            log.error(f'Error calling PaddleOCR-vl: {e}')
            return [
                Document(
                    page_content=f'Error during OCR processing: {e}',
                    metadata={
                        'error': 'processing_failed',
                        'file_name': self.file_name,
                        'processing_engine': 'paddleocr-vl',
                    },
                )
            ]