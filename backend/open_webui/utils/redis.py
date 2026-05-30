"""
工具模块: Redis 连接管理 (Redis Connection Management)

功能:
- Redis 客户端初始化（单机、哨兵、集群模式）
- 连接缓存和复用
- Sentinel 哨兵模式支持
- Redis 连接参数配置

依赖:
- redis (同步/异步 Redis 客户端)
- open_webui.env (Redis 环境变量)
"""

import inspect
from urllib.parse import urlparse
import asyncio
import time

import logging

import redis

from open_webui.env import (
    REDIS_CLUSTER,
    REDIS_HEALTH_CHECK_INTERVAL,
    REDIS_SOCKET_CONNECT_TIMEOUT,
    REDIS_SOCKET_KEEPALIVE,
    REDIS_SENTINEL_HOSTS,
    REDIS_SENTINEL_MAX_RETRY_COUNT,
    REDIS_SENTINEL_PORT,
    REDIS_URL,
    REDIS_RECONNECT_DELAY,
)

log = logging.getLogger(__name__)

# 哨兵最大重试次数
MAX_RETRY_COUNT = REDIS_SENTINEL_MAX_RETRY_COUNT


# 连接缓存：确保同一配置的连接只创建一次
# 缓存属于第一个打开连接的进程，永不超时。
_CONNECTION_CACHE = {}


class SentinelRedisProxy:
    """
    Redis Sentinel 代理

    封装 Sentinel 哨兵模式的 Redis 客户端，支持自动故障转移。
    对于异步模式和非异步模式的方法分别进行包装。
    """

    def __init__(self, sentinel, service, *, async_mode: bool = True, **kw):
        """
        初始化 Sentinel 代理

        参数:
            sentinel: Sentinel 客户端实例
            service: 服务名称（通常是 'mymaster'）
            async_mode: 是否为异步模式
            **kw: 传递给 Sentinel 的额外参数
        """
        self._sentinel = sentinel
        self._service = service
        self._kw = kw
        self._async_mode = async_mode

    def _master(self):
        """获取主节点"""
        return self._sentinel.master_for(self._service, **self._kw)

    def __getattr__(self, item):
        """
        动态代理所有 Redis 方法

        对于工厂方法（pipeline, pubsub 等）直接返回，
        对于数据操作方法则包装以支持故障转移重试。
        """
        master = self._master()
        orig_attr = getattr(master, item)

        if not callable(orig_attr):
            return orig_attr

        # 工厂方法直接返回，不包装
        FACTORY_METHODS = {'pipeline', 'pubsub', 'monitor', 'client', 'transaction'}
        if item in FACTORY_METHODS:
            return orig_attr

        if self._async_mode:
            if inspect.isasyncgenfunction(orig_attr):
                # 异步生成器方法：包装为支持重试的异步生成器

                def _wrapped_iter(*args, **kwargs):
                    async def _iter():
                        for i in range(REDIS_SENTINEL_MAX_RETRY_COUNT):
                            try:
                                method = getattr(self._master(), item)
                                async for value in method(*args, **kwargs):
                                    yield value
                                return
                            except (
                                redis.exceptions.ConnectionError,
                                redis.exceptions.ReadOnlyError,
                            ) as e:
                                if i < REDIS_SENTINEL_MAX_RETRY_COUNT - 1:
                                    log.debug(
                                        'Redis sentinel fail-over (%s). Retry %s/%s',
                                        type(e).__name__,
                                        i + 1,
                                        REDIS_SENTINEL_MAX_RETRY_COUNT,
                                    )
                                    if REDIS_RECONNECT_DELAY:
                                        time.sleep(REDIS_RECONNECT_DELAY / 1000)
                                    continue
                                log.error(
                                    'Redis operation failed after %s retries: %s',
                                    REDIS_SENTINEL_MAX_RETRY_COUNT,
                                    e,
                                )
                                raise e from e

                    return _iter()

                return _wrapped_iter

            # 异步方法：包装为支持重试的异步函数
            async def _wrapped(*args, **kwargs):
                for i in range(REDIS_SENTINEL_MAX_RETRY_COUNT):
                    try:
                        method = getattr(self._master(), item)
                        result = method(*args, **kwargs)
                        if inspect.iscoroutine(result):
                            return await result
                        return result
                    except (
                        redis.exceptions.ConnectionError,
                        redis.exceptions.ReadOnlyError,
                    ) as e:
                        if i < REDIS_SENTINEL_MAX_RETRY_COUNT - 1:
                            log.debug(
                                'Redis sentinel fail-over (%s). Retry %s/%s',
                                type(e).__name__,
                                i + 1,
                                REDIS_SENTINEL_MAX_RETRY_COUNT,
                            )
                            if REDIS_RECONNECT_DELAY:
                                await asyncio.sleep(REDIS_RECONNECT_DELAY / 1000)
                            continue
                        log.error(
                            'Redis operation failed after %s retries: %s',
                            REDIS_SENTINEL_MAX_RETRY_COUNT,
                            e,
                        )
                        raise e from e

            return _wrapped

        else:
            # 同步方法：包装为支持重试的同步函数
            def _wrapped(*args, **kwargs):
                for i in range(REDIS_SENTINEL_MAX_RETRY_COUNT):
                    try:
                        method = getattr(self._master(), item)
                        return method(*args, **kwargs)
                    except (
                        redis.exceptions.ConnectionError,
                        redis.exceptions.ReadOnlyError,
                    ) as e:
                        if i < REDIS_SENTINEL_MAX_RETRY_COUNT - 1:
                            log.debug(
                                'Redis sentinel fail-over (%s). Retry %s/%s',
                                type(e).__name__,
                                i + 1,
                                REDIS_SENTINEL_MAX_RETRY_COUNT,
                            )
                            if REDIS_RECONNECT_DELAY:
                                time.sleep(REDIS_RECONNECT_DELAY / 1000)
                            continue
                        log.error(
                            'Redis operation failed after %s retries: %s',
                            REDIS_SENTINEL_MAX_RETRY_COUNT,
                            e,
                        )
                        raise e from e

            return _wrapped


def parse_redis_service_url(redis_url):
    """
    解析 Redis 服务 URL

    从 redis://user:pass@host:port/db 的 URL 中提取连接信息。

    参数:
        redis_url: Redis 连接 URL

    返回:
        dict: 包含 username, password, service, port, db 的字典
    """
    parsed_url = urlparse(redis_url)
    if parsed_url.scheme != 'redis' and parsed_url.scheme != 'rediss':
        raise ValueError("Invalid Redis URL scheme. Must be 'redis' or 'rediss'.")

    return {
        'username': parsed_url.username or None,
        'password': parsed_url.password or None,
        'service': parsed_url.hostname or 'mymaster',
        'port': parsed_url.port or 6379,
        'db': int(parsed_url.path.lstrip('/') or 0),
    }


def get_redis_client(async_mode=False):
    """
    获取 Redis 客户端实例

    从环境变量读取配置并创建 Redis 客户端。
    出错时返回 None。

    参数:
        async_mode: 是否为异步模式

    返回:
        Redis 客户端实例或 None
    """
    try:
        return get_redis_connection(
            redis_url=REDIS_URL,
            redis_sentinels=get_sentinels_from_env(REDIS_SENTINEL_HOSTS, REDIS_SENTINEL_PORT),
            redis_cluster=REDIS_CLUSTER,
            async_mode=async_mode,
        )
    except Exception as e:
        log.debug(f'Failed to get Redis client: {e}')
        return None


def get_redis_connection(
    redis_url,
    redis_sentinels,
    redis_cluster=False,
    async_mode=False,
    decode_responses=True,
):
    """
    创建 Redis 连接

    支持三种模式：
    1. 单机模式：直接使用 Redis URL
    2. 哨兵模式：通过 Sentinel 哨兵自动发现主从节点
    3. 集群模式：Redis Cluster 集群

    参数:
        redis_url: Redis 连接 URL
        redis_sentinels: 哨兵主机列表
        redis_cluster: 是否使用集群模式
        async_mode: 是否为异步模式
        decode_responses: 是否自动解码响应

    返回:
        Redis 客户端实例
    """
    # 使用连接参数作为缓存键
    cache_key = (
        redis_url,
        tuple(redis_sentinels) if redis_sentinels else (),
        async_mode,
        decode_responses,
    )

    # 检查缓存
    if cache_key in _CONNECTION_CACHE:
        return _CONNECTION_CACHE[cache_key]

    connection = None

    # 连接超时配置
    connect_timeout_kwargs = (
        {'socket_connect_timeout': REDIS_SOCKET_CONNECT_TIMEOUT} if REDIS_SOCKET_CONNECT_TIMEOUT is not None else {}
    )

    # Keepalive 配置
    keepalive_kwargs = {'socket_keepalive': True} if REDIS_SOCKET_KEEPALIVE else {}

    # 健康检查配置
    health_check_kwargs = {'health_check_interval': REDIS_HEALTH_CHECK_INTERVAL} if REDIS_HEALTH_CHECK_INTERVAL else {}

    if async_mode:
        import redis.asyncio as redis

        # 异步模式：哨兵
        if redis_sentinels:
            redis_config = parse_redis_service_url(redis_url)
            sentinel = redis.sentinel.Sentinel(
                redis_sentinels,
                port=redis_config['port'],
                db=redis_config['db'],
                username=redis_config['username'],
                password=redis_config['password'],
                decode_responses=decode_responses,
                socket_connect_timeout=REDIS_SOCKET_CONNECT_TIMEOUT,
                **keepalive_kwargs,
                **health_check_kwargs,
            )
            connection = SentinelRedisProxy(
                sentinel,
                redis_config['service'],
                async_mode=async_mode,
            )
        # 异步模式：集群
        elif redis_cluster:
            if not redis_url:
                raise ValueError('Redis URL must be provided for cluster mode.')
            return redis.cluster.RedisCluster.from_url(
                redis_url,
                decode_responses=decode_responses,
                **connect_timeout_kwargs,
                **keepalive_kwargs,
                **health_check_kwargs,
            )
        # 异步模式：单机
        elif redis_url:
            connection = redis.from_url(
                redis_url,
                decode_responses=decode_responses,
                **connect_timeout_kwargs,
                **keepalive_kwargs,
                **health_check_kwargs,
            )
    else:
        import redis

        # 同步模式：哨兵
        if redis_sentinels:
            redis_config = parse_redis_service_url(redis_url)
            sentinel = redis.sentinel.Sentinel(
                redis_sentinels,
                port=redis_config['port'],
                db=redis_config['db'],
                username=redis_config['username'],
                password=redis_config['password'],
                decode_responses=decode_responses,
                socket_connect_timeout=REDIS_SOCKET_CONNECT_TIMEOUT,
                **keepalive_kwargs,
                **health_check_kwargs,
            )
            connection = SentinelRedisProxy(
                sentinel,
                redis_config['service'],
                async_mode=async_mode,
            )
        # 同步模式：集群
        elif redis_cluster:
            if not redis_url:
                raise ValueError('Redis URL must be provided for cluster mode.')
            return redis.cluster.RedisCluster.from_url(
                redis_url,
                decode_responses=decode_responses,
                **connect_timeout_kwargs,
                **keepalive_kwargs,
                **health_check_kwargs,
            )
        # 同步模式：单机
        elif redis_url:
            connection = redis.Redis.from_url(
                redis_url,
                decode_responses=decode_responses,
                **connect_timeout_kwargs,
                **keepalive_kwargs,
                **health_check_kwargs,
            )

    # 缓存连接
    _CONNECTION_CACHE[cache_key] = connection
    return connection


def get_sentinels_from_env(sentinel_hosts_env, sentinel_port_env):
    """
    从环境变量解析哨兵主机列表

    参数:
        sentinel_hosts_env: 哨兵主机环境变量（逗号分隔的字符串）
        sentinel_port_env: 哨兵端口环境变量

    返回:
        list: 哨兵主机端口元组列表
    """
    if sentinel_hosts_env:
        sentinel_hosts = sentinel_hosts_env.split(',')
        sentinel_port = int(sentinel_port_env)
        return [(host, sentinel_port) for host in sentinel_hosts]
    return []


def get_sentinel_url_from_env(redis_url, sentinel_hosts_env, sentinel_port_env):
    """
    从环境变量构建 Sentinel URL

    参数:
        redis_url: Redis URL
        sentinel_hosts_env: 哨兵主机环境变量
        sentinel_port_env: 哨兵端口环境变量

    返回:
        str: Redis Sentinel URL
    """
    redis_config = parse_redis_service_url(redis_url)
    username = redis_config['username'] or ''
    password = redis_config['password'] or ''
    auth_part = ''
    if username or password:
        auth_part = f'{username}:{password}@'
    hosts_part = ','.join(f'{host}:{sentinel_port_env}' for host in sentinel_hosts_env.split(','))
    return f'redis+sentinel://{auth_part}{hosts_part}/{redis_config["db"]}/{redis_config["service"]}'
