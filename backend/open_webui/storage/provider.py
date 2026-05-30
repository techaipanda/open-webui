"""
存储模块: 存储提供者 (Storage Providers)

功能:
- 多种存储后端的支持（Local、S3、GCS、Azure Blob）
- 统一的文件上传/下载/删除接口
- 存储后端的抽象和实现

依赖:
- boto3 (S3)
- google-cloud-storage (GCS)
- azure-storage-blob (Azure)
- python-dotenv (配置)
"""

import os
import shutil
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import BinaryIO, Tuple, Dict

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from open_webui.config import (
    S3_ACCESS_KEY_ID,
    S3_BUCKET_NAME,
    S3_ENDPOINT_URL,
    S3_KEY_PREFIX,
    S3_REGION_NAME,
    S3_SECRET_ACCESS_KEY,
    S3_USE_ACCELERATE_ENDPOINT,
    S3_ADDRESSING_STYLE,
    S3_ENABLE_TAGGING,
    GCS_BUCKET_NAME,
    GOOGLE_APPLICATION_CREDENTIALS_JSON,
    AZURE_STORAGE_ENDPOINT,
    AZURE_STORAGE_CONTAINER_NAME,
    AZURE_STORAGE_KEY,
    STORAGE_PROVIDER,
    UPLOAD_DIR,
)
from google.cloud import storage
from google.cloud.exceptions import GoogleCloudError, NotFound
from open_webui.constants import ERROR_MESSAGES
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceNotFoundError

log = logging.getLogger(__name__)


class StorageProvider(ABC):
    """
    存储提供者抽象基类

    定义所有存储后端必须实现的接口方法。
    """

    @abstractmethod
    def get_file(self, file_path: str) -> str:
        """获取文件，返回本地文件路径"""
        pass

    @abstractmethod
    def upload_file(self, file: BinaryIO, filename: str, tags: Dict[str, str]) -> Tuple[bytes, str]:
        """上传文件，返回文件内容和路径"""
        pass

    @abstractmethod
    def delete_all_files(self) -> None:
        """删除所有文件"""
        pass

    @abstractmethod
    def delete_file(self, file_path: str) -> None:
        """删除指定文件"""
        pass


class LocalStorageProvider(StorageProvider):
    """
    本地存储提供者

    将文件存储在本地文件系统的 UPLOAD_DIR 目录中。
    """

    @staticmethod
    def upload_file(file: BinaryIO, filename: str, tags: Dict[str, str]) -> Tuple[bytes, str]:
        """
        上传文件到本地存储

        参数:
            file: 文件二进制流
            filename: 文件名
            tags: 文件标签（字典）

        返回:
            Tuple[bytes, str]: 文件内容和本地文件路径
        """
        contents = file.read()
        if not contents:
            raise ValueError(ERROR_MESSAGES.EMPTY_CONTENT)
        file_path = os.path.join(UPLOAD_DIR, filename)
        with open(file_path, 'wb') as f:
            f.write(contents)
        return contents, file_path

    @staticmethod
    def get_file(file_path: str) -> str:
        """
        获取本地文件

        参数:
            file_path: 文件路径

        返回:
            str: 本地文件路径
        """
        return file_path

    @staticmethod
    def delete_file(file_path: str) -> None:
        """
        删除本地文件

        参数:
            file_path: 文件路径
        """
        filename = os.path.basename(file_path)
        file_path = os.path.join(UPLOAD_DIR, filename)
        if os.path.isfile(file_path):
            os.remove(file_path)
        else:
            log.warning(f'File {file_path} not found in local storage.')

    @staticmethod
    def delete_all_files() -> None:
        """
        删除本地存储目录中的所有文件
        """
        if os.path.exists(UPLOAD_DIR):
            for filename in os.listdir(UPLOAD_DIR):
                file_path = os.path.join(UPLOAD_DIR, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)  # 删除文件或链接
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)  # 删除目录
                except Exception as e:
                    log.exception(f'Failed to delete {file_path}. Reason: {e}')
        else:
            log.warning(f'Directory {UPLOAD_DIR} not found in local storage.')


class S3StorageProvider(StorageProvider):
    """
    Amazon S3 存储提供者

    将文件上传到 S3 兼容的存储服务（支持 AWS S3、MinIO 等）。
    """

    def __init__(self):
        """
        初始化 S3 客户端

        支持两种认证方式：
        1. 显式凭证（access key + secret key）
        2. 默认凭证（支持 IAM roles for EC2, EKS 等）
        """
        config = Config(
            s3={
                'use_accelerate_endpoint': S3_USE_ACCELERATE_ENDPOINT,
                'addressing_style': S3_ADDRESSING_STYLE,
            },
            # KIT change - see https://github.com/boto/boto3/issues/4400#issuecomment-2600742103∆
            request_checksum_calculation='when_required',
            response_checksum_validation='when_required',
        )

        # 如果提供了 access key 和 secret，使用它们进行认证
        if S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY:
            self.s3_client = boto3.client(
                's3',
                region_name=S3_REGION_NAME,
                endpoint_url=S3_ENDPOINT_URL,
                aws_access_key_id=S3_ACCESS_KEY_ID,
                aws_secret_access_key=S3_SECRET_ACCESS_KEY,
                config=config,
            )
        else:
            # 如果没有提供显式凭证，回退到默认 AWS 凭证
            # 这支持工作负载标识（EC2、EKS 等的 IAM 角色）
            self.s3_client = boto3.client(
                's3',
                region_name=S3_REGION_NAME,
                endpoint_url=S3_ENDPOINT_URL,
                config=config,
            )

        self.bucket_name = S3_BUCKET_NAME
        self.key_prefix = S3_KEY_PREFIX if S3_KEY_PREFIX else ''

    @staticmethod
    def sanitize_tag_value(s: str) -> str:
        """
        清理标签值，只保留 S3 允许的字符

        参数:
            s: 原始标签值字符串

        返回:
            str: 清理后的标签值
        """
        return re.sub(r'[^a-zA-Z0-9 äöüÄÖÜß\+\-=\._:/@]', '', s)

    def upload_file(self, file: BinaryIO, filename: str, tags: Dict[str, str]) -> Tuple[bytes, str]:
        """
        上传文件到 S3 存储

        先上传到本地，然后同步到 S3。

        参数:
            file: 文件二进制流
            filename: 文件名
            tags: 文件标签

        返回:
            Tuple[bytes, str]: 文件内容和 S3 对象路径
        """
        contents, file_path = LocalStorageProvider.upload_file(file, filename, tags)
        s3_key = os.path.join(self.key_prefix, filename)
        try:
            self.s3_client.upload_file(file_path, self.bucket_name, s3_key)
            if S3_ENABLE_TAGGING and tags:
                sanitized_tags = {self.sanitize_tag_value(k): self.sanitize_tag_value(v) for k, v in tags.items()}
                tagging = {'TagSet': [{'Key': k, 'Value': v} for k, v in sanitized_tags.items()]}
                self.s3_client.put_object_tagging(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Tagging=tagging,
                )
            return (
                contents,
                f's3://{self.bucket_name}/{s3_key}',
            )
        except ClientError as e:
            raise RuntimeError(f'Error uploading file to S3: {e}')

    def get_file(self, file_path: str) -> str:
        """
        从 S3 下载文件到本地

        参数:
            file_path: S3 对象路径（格式：s3://bucket/key）

        返回:
            str: 本地文件路径
        """
        try:
            s3_key = self._extract_s3_key(file_path)
            local_file_path = self._get_local_file_path(s3_key)
            self.s3_client.download_file(self.bucket_name, s3_key, local_file_path)
            return local_file_path
        except ClientError as e:
            raise RuntimeError(f'Error downloading file from S3: {e}')

    def delete_file(self, file_path: str) -> None:
        """
        从 S3 删除文件

        参数:
            file_path: S3 对象路径
        """
        try:
            s3_key = self._extract_s3_key(file_path)
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
        except ClientError as e:
            raise RuntimeError(f'Error deleting file from S3: {e}')

        # 同时删除本地文件
        LocalStorageProvider.delete_file(file_path)

    def delete_all_files(self) -> None:
        """
        删除 S3 存储桶中的所有文件

        只删除通过 open-webui 上传的文件（前缀匹配 key_prefix）。
        """
        try:
            response = self.s3_client.list_objects_v2(Bucket=self.bucket_name)
            if 'Contents' in response:
                for content in response['Contents']:
                    # 跳过不是从 open-webui 上传的对象
                    if not content['Key'].startswith(self.key_prefix):
                        continue

                    self.s3_client.delete_object(Bucket=self.bucket_name, Key=content['Key'])
        except ClientError as e:
            raise RuntimeError(f'Error deleting all files from S3: {e}')

        # 同时删除本地所有文件
        LocalStorageProvider.delete_all_files()

    # S3 key 是分配给对象的名称，不包括桶名，但包括内部路径和文件名
    def _extract_s3_key(self, full_file_path: str) -> str:
        return '/'.join(full_file_path.split('//')[1].split('/')[1:])

    def _get_local_file_path(self, s3_key: str) -> str:
        return os.path.join(UPLOAD_DIR, s3_key.split('/')[-1])


class GCSStorageProvider(StorageProvider):
    """
    Google Cloud Storage (GCS) 存储提供者

    将文件存储到 Google Cloud Storage。
    支持服务账号凭证和默认凭证（适用于 GCE 环境）。
    """

    def __init__(self):
        """
        初始化 GCS 客户端

        凭证优先级：
        1. GOOGLE_APPLICATION_CREDENTIALS_JSON 环境变量
        2. 默认凭证（本地环境使用用户凭证，GCE 使用元数据服务）
        """
        self.bucket_name = GCS_BUCKET_NAME

        if GOOGLE_APPLICATION_CREDENTIALS_JSON:
            self.gcs_client = storage.Client.from_service_account_info(
                info=json.loads(GOOGLE_APPLICATION_CREDENTIALS_JSON)
            )
        else:
            # 如果没有提供凭证 json，则从环境拾取凭证
            # 本地环境使用用户凭证
            # GCE 实例使用 Google 元数据服务
            self.gcs_client = storage.Client()
        self.bucket = self.gcs_client.bucket(GCS_BUCKET_NAME)

    def upload_file(self, file: BinaryIO, filename: str, tags: Dict[str, str]) -> Tuple[bytes, str]:
        """
        上传文件到 GCS 存储

        参数:
            file: 文件二进制流
            filename: 文件名
            tags: 文件标签

        返回:
            Tuple[bytes, str]: 文件内容和 GCS 对象路径
        """
        contents, file_path = LocalStorageProvider.upload_file(file, filename, tags)
        try:
            blob = self.bucket.blob(filename)
            blob.upload_from_filename(file_path)
            return contents, 'gs://' + self.bucket_name + '/' + filename
        except GoogleCloudError as e:
            raise RuntimeError(f'Error uploading file to GCS: {e}')

    def get_file(self, file_path: str) -> str:
        """
        从 GCS 下载文件到本地

        参数:
            file_path: GCS 对象路径（格式：gs://bucket/filename）

        返回:
            str: 本地文件路径
        """
        try:
            filename = file_path.removeprefix('gs://').split('/')[1]
            local_file_path = os.path.join(UPLOAD_DIR, filename)
            blob = self.bucket.get_blob(filename)
            blob.download_to_filename(local_file_path)

            return local_file_path
        except NotFound as e:
            raise RuntimeError(f'Error downloading file from GCS: {e}')

    def delete_file(self, file_path: str) -> None:
        """
        从 GCS 删除文件

        参数:
            file_path: GCS 对象路径
        """
        try:
            filename = file_path.removeprefix('gs://').split('/')[1]
            blob = self.bucket.get_blob(filename)
            blob.delete()
        except NotFound as e:
            raise RuntimeError(f'Error deleting file from GCS: {e}')

        # 同时删除本地文件
        LocalStorageProvider.delete_file(file_path)

    def delete_all_files(self) -> None:
        """
        删除 GCS 存储桶中的所有文件
        """
        try:
            blobs = self.bucket.list_blobs()

            for blob in blobs:
                blob.delete()

        except NotFound as e:
            raise RuntimeError(f'Error deleting all files from GCS: {e}')

        # 同时删除本地所有文件
        LocalStorageProvider.delete_all_files()


class AzureStorageProvider(StorageProvider):
    """
    Azure Blob Storage 存储提供者

    将文件存储到 Azure Blob Storage。
    支持存储账号密钥和 Azure Managed Identity 认证。
    """

    def __init__(self):
        """
        初始化 Azure Blob Service Client

        认证方式：
        1. 存储账号密钥
        2. DefaultAzureCredential（支持 Managed Identity）
        """
        self.endpoint = AZURE_STORAGE_ENDPOINT
        self.container_name = AZURE_STORAGE_CONTAINER_NAME
        storage_key = AZURE_STORAGE_KEY

        if storage_key:
            # 使用存储账号端点和密钥配置
            self.blob_service_client = BlobServiceClient(account_url=self.endpoint, credential=storage_key)
        else:
            # 使用 DefaultAzureCredential 支持 Managed Identity 认证
            self.blob_service_client = BlobServiceClient(account_url=self.endpoint, credential=DefaultAzureCredential())
        self.container_client = self.blob_service_client.get_container_client(self.container_name)

    def upload_file(self, file: BinaryIO, filename: str, tags: Dict[str, str]) -> Tuple[bytes, str]:
        """
        上传文件到 Azure Blob Storage

        参数:
            file: 文件二进制流
            filename: 文件名
            tags: 文件标签

        返回:
            Tuple[bytes, str]: 文件内容和 Azure 对象路径
        """
        contents, file_path = LocalStorageProvider.upload_file(file, filename, tags)
        try:
            blob_client = self.container_client.get_blob_client(filename)
            blob_client.upload_blob(contents, overwrite=True)
            return contents, f'{self.endpoint}/{self.container_name}/{filename}'
        except Exception as e:
            raise RuntimeError(f'Error uploading file to Azure Blob Storage: {e}')

    def get_file(self, file_path: str) -> str:
        """
        从 Azure 下载文件到本地

        参数:
            file_path: Azure 对象路径

        返回:
            str: 本地文件路径
        """
        try:
            filename = file_path.split('/')[-1]
            local_file_path = os.path.join(UPLOAD_DIR, filename)
            blob_client = self.container_client.get_blob_client(filename)
            with open(local_file_path, 'wb') as download_file:
                download_file.write(blob_client.download_blob().readall())
            return local_file_path
        except ResourceNotFoundError as e:
            raise RuntimeError(f'Error downloading file from Azure Blob Storage: {e}')

    def delete_file(self, file_path: str) -> None:
        """
        从 Azure 删除文件

        参数:
            file_path: Azure 对象路径
        """
        try:
            filename = file_path.split('/')[-1]
            blob_client = self.container_client.get_blob_client(filename)
            blob_client.delete_blob()
        except ResourceNotFoundError as e:
            raise RuntimeError(f'Error deleting file from Azure Blob Storage: {e}')

        # 同时删除本地文件
        LocalStorageProvider.delete_file(file_path)

    def delete_all_files(self) -> None:
        """
        删除 Azure 容器中的所有文件
        """
        try:
            blobs = self.container_client.list_blobs()
            for blob in blobs:
                self.container_client.delete_blob(blob.name)
        except Exception as e:
            raise RuntimeError(f'Error deleting all files from Azure Blob Storage: {e}')

        # 同时删除本地所有文件
        LocalStorageProvider.delete_all_files()


def get_storage_provider(storage_provider: str):
    """
    获取存储提供者实例

    参数:
        storage_provider: 存储后端类型 ('local', 's3', 'gcs', 'azure')

    返回:
        StorageProvider: 存储提供者实例

    异常:
        RuntimeError: 不支持的存储后端时抛出
    """
    if storage_provider == 'local':
        Storage = LocalStorageProvider()
    elif storage_provider == 's3':
        Storage = S3StorageProvider()
    elif storage_provider == 'gcs':
        Storage = GCSStorageProvider()
    elif storage_provider == 'azure':
        Storage = AzureStorageProvider()
    else:
        raise RuntimeError(f'Unsupported storage provider: {storage_provider}')
    return Storage


# 默认存储实例
Storage = get_storage_provider(STORAGE_PROVIDER)
