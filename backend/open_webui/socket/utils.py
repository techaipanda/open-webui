"""
Socket.IO 工具模块: Redis 协作 (Socket.IO Utilities: Redis Collaboration)

功能:
- Socket.IO 事件处理的 Redis 协作支持
- Ydoc 文档协同编辑的 Redis 后端
- 分布式环境下的实时同步

依赖:
- redis (Redis 客户端)
- pycrdt (CRDT 协同编辑库)
- open_webui.utils.redis
"""

import json
import uuid
from open_webui.utils.redis import get_redis_connection
from open_webui.env import REDIS_KEY_PREFIX
from typing import Optional, List, Tuple
import pycrdt as Y


class RedisLock:
    """
    Redis 分布式锁

    用于在分布式环境中实现互斥访问的锁机制。
    支持锁的获取、续期和释放。
    """

    def __init__(
        self,
        redis_url,
        lock_name,
        timeout_secs,
        redis_sentinels=[],
        redis_cluster=False,
    ):
        self.lock_name = lock_name
        self.lock_id = str(uuid.uuid4())
        self.timeout_secs = timeout_secs
        self.lock_obtained = False
        self.redis = get_redis_connection(
            redis_url,
            redis_sentinels,
            redis_cluster=redis_cluster,
            decode_responses=True,
        )

    def aquire_lock(self):
        """
        获取锁

        使用 NX 模式确保只在锁不存在时设置成功。
        """
        # nx=True will only set this key if it _hasn't_ already been set
        self.lock_obtained = self.redis.set(self.lock_name, self.lock_id, nx=True, ex=self.timeout_secs)
        return self.lock_obtained

    def renew_lock(self):
        """
        续期锁

        使用 XX 模式确保只在锁已存在时更新。
        """
        # xx=True will only set this key if it _has_ already been set
        return self.redis.set(self.lock_name, self.lock_id, xx=True, ex=self.timeout_secs)

    def release_lock(self):
        """
        释放锁

        只有锁的持有者才能释放锁，防止误删其他进程的锁。
        """
        lock_value = self.redis.get(self.lock_name)
        if lock_value and lock_value == self.lock_id:
            self.redis.delete(self.lock_name)


class RedisDict:
    """
    Redis Hash 字典

    将 Redis Hash 封装为字典接口，方便存储和读取 Python 对象。
    支持 JSON 序列化和反序列化。
    """

    def __init__(self, name, redis_url, redis_sentinels=[], redis_cluster=False):
        self.name = name
        self.redis = get_redis_connection(
            redis_url,
            redis_sentinels,
            redis_cluster=redis_cluster,
            decode_responses=True,
        )

    def __setitem__(self, key, value):
        """
        设置键值对

        参数:
            key: 键
            value: 值（会被 JSON 序列化）
        """
        serialized_value = json.dumps(value)
        self.redis.hset(self.name, key, serialized_value)

    def __getitem__(self, key):
        """
        获取键值

        参数:
            key: 键

        返回:
            反序列化后的值
        """
        value = self.redis.hget(self.name, key)
        if value is None:
            raise KeyError(key)
        return json.loads(value)

    def __delitem__(self, key):
        """
        删除键值对

        参数:
            key: 键
        """
        result = self.redis.hdel(self.name, key)
        if result == 0:
            raise KeyError(key)

    def __contains__(self, key):
        """检查键是否存在"""
        return self.redis.hexists(self.name, key)

    def __len__(self):
        """返回字典中键的数量"""
        return self.redis.hlen(self.name)

    def keys(self):
        """返回所有键"""
        return self.redis.hkeys(self.name)

    def values(self):
        """返回所有值（反序列化后的对象）"""
        return [json.loads(v) for v in self.redis.hvals(self.name)]

    def items(self):
        """返回所有键值对"""
        return [(k, json.loads(v)) for k, v in self.redis.hgetall(self.name).items()]

    def set(self, mapping: dict):
        """
        批量设置键值对

        先获取现有键，再进行增量和删除操作，避免清空字典导致并发读取失败。
        """
        if not mapping:
            self.redis.delete(self.name)
            return

        # Fetch existing keys before writing so we know which ones to remove.
        # HKEYS is cheap — it transfers only short key strings, not large JSON values.
        existing_keys = set(self.redis.hkeys(self.name))
        new_keys = set(mapping.keys())
        keys_to_remove = existing_keys - new_keys

        # HSET first (add/update all new values), then HDEL (remove stale keys).
        # We never DELETE the whole hash — this eliminates the race window
        # where concurrent readers would see an empty models dict.
        self.redis.hset(self.name, mapping={k: json.dumps(v) for k, v in mapping.items()})
        if keys_to_remove:
            self.redis.hdel(self.name, *keys_to_remove)

    def get(self, key, default=None):
        """
        获取键值，支持默认值

        参数:
            key: 键
            default: 默认值（键不存在时返回）
        """
        try:
            return self[key]
        except KeyError:
            return default

    def clear(self):
        """清空字典"""
        self.redis.delete(self.name)

    def update(self, other=None, **kwargs):
        """
        更新字典

        参数:
            other: 其他字典
            **kwargs: 关键字参数
        """
        if other is not None:
            for k, v in other.items() if hasattr(other, 'items') else other:
                self[k] = v
        for k, v in kwargs.items():
            self[k] = v

    def setdefault(self, key, default=None):
        """
        设置默认值

        如果键不存在，则设置为默认值并返回；如果已存在，则返回现有值。
        """
        if key not in self:
            self[key] = default
        return self[key]


class YdocManager:
    """
    Ydoc 协同文档管理器

    管理 Yjs CRDT 文档的更新和用户状态。
    支持 Redis 后端和内存后端两种模式。
    """

    COMPACTION_THRESHOLD = 500  # 压缩阈值，达到此数量的更新后进行压缩

    def __init__(
        self,
        redis=None,
        redis_key_prefix: str = f'{REDIS_KEY_PREFIX}:ydoc:documents',
    ):
        self._updates = {}  # 内存模式：存储更新
        self._users = {}   # 内存模式：存储用户
        self._redis = redis
        self._redis_key_prefix = redis_key_prefix

    async def append_to_updates(self, document_id: str, update: bytes):
        """
        添加文档更新

        将 CRDT 更新追加到文档的更新列表中。
        当更新数量达到阈值时触发压缩。

        参数:
            document_id: 文档 ID
            update: CRDT 更新字节数据
        """
        document_id = document_id.replace(':', '_')
        if self._redis:
            redis_key = f'{self._redis_key_prefix}:{document_id}:updates'
            await self._redis.rpush(redis_key, json.dumps(list(update)))
            list_len = await self._redis.llen(redis_key)
            if list_len >= self.COMPACTION_THRESHOLD:
                await self._compact_updates_redis(document_id)
        else:
            if document_id not in self._updates:
                self._updates[document_id] = []
            self._updates[document_id].append(update)
            if len(self._updates[document_id]) >= self.COMPACTION_THRESHOLD:
                self._compact_updates_memory(document_id)

    async def _compact_updates_redis(self, document_id: str):
        """
        Redis 后端压缩：将前一半更新合并为一个快照

        滚动压缩策略，将最老的一半更新合并后删除。
        """
        redis_key = f'{self._redis_key_prefix}:{document_id}:updates'
        all_updates = await self._redis.lrange(redis_key, 0, -1)
        if len(all_updates) <= 1:
            return
        mid = len(all_updates) // 2
        ydoc = Y.Doc()
        for raw in all_updates[:mid]:
            ydoc.apply_update(bytes(json.loads(raw)))
        snapshot = json.dumps(list(ydoc.get_update()))
        pipe = self._redis.pipeline()
        pipe.delete(redis_key)
        pipe.rpush(redis_key, snapshot, *all_updates[mid:])
        await pipe.execute()

    def _compact_updates_memory(self, document_id: str):
        """
        内存后端压缩：将前一半更新合并为一个快照
        """
        updates = self._updates.get(document_id, [])
        if len(updates) <= 1:
            return
        mid = len(updates) // 2
        ydoc = Y.Doc()
        for update in updates[:mid]:
            ydoc.apply_update(bytes(update))
        self._updates[document_id] = [ydoc.get_update()] + updates[mid:]

    async def get_updates(self, document_id: str) -> List[bytes]:
        """
        获取文档的所有更新

        参数:
            document_id: 文档 ID

        返回:
            更新字节列表
        """
        document_id = document_id.replace(':', '_')

        if self._redis:
            redis_key = f'{self._redis_key_prefix}:{document_id}:updates'
            updates = await self._redis.lrange(redis_key, 0, -1)
            return [bytes(json.loads(update)) for update in updates]
        else:
            return self._updates.get(document_id, [])

    async def document_exists(self, document_id: str) -> bool:
        """
        检查文档是否存在

        参数:
            document_id: 文档 ID

        返回:
            是否存在
        """
        document_id = document_id.replace(':', '_')

        if self._redis:
            redis_key = f'{self._redis_key_prefix}:{document_id}:updates'
            return await self._redis.exists(redis_key) > 0
        else:
            return document_id in self._updates

    async def get_users(self, document_id: str) -> List[str]:
        """
        获取文档的在线用户列表

        参数:
            document_id: 文档 ID

        返回:
            用户 ID 列表
        """
        document_id = document_id.replace(':', '_')

        if self._redis:
            redis_key = f'{self._redis_key_prefix}:{document_id}:users'
            users = await self._redis.smembers(redis_key)
            return list(users)
        else:
            return self._users.get(document_id, [])

    async def add_user(self, document_id: str, user_id: str):
        """
        添加用户到文档

        参数:
            document_id: 文档 ID
            user_id: 用户 ID
        """
        document_id = document_id.replace(':', '_')

        if self._redis:
            redis_key = f'{self._redis_key_prefix}:{document_id}:users'
            await self._redis.sadd(redis_key, user_id)
        else:
            if document_id not in self._users:
                self._users[document_id] = set()
            self._users[document_id].add(user_id)

    async def remove_user(self, document_id: str, user_id: str):
        """
        从文档移除用户

        参数:
            document_id: 文档 ID
            user_id: 用户 ID
        """
        document_id = document_id.replace(':', '_')

        if self._redis:
            redis_key = f'{self._redis_key_prefix}:{document_id}:users'
            await self._redis.srem(redis_key, user_id)
        else:
            if document_id in self._users and user_id in self._users[document_id]:
                self._users[document_id].remove(user_id)

    async def remove_user_from_all_documents(self, user_id: str):
        """
        从所有文档移除用户

        当用户断开连接时调用，清理其参与的所有文档的关联。

        参数:
            user_id: 用户 ID
        """
        if self._redis:
            keys = []
            async for key in self._redis.scan_iter(match=f'{self._redis_key_prefix}:*', count=100):
                keys.append(key)
            for key in keys:
                if key.endswith(':users'):
                    await self._redis.srem(key, user_id)

                    document_id = key.split(':')[-2]
                    if len(await self.get_users(document_id)) == 0:
                        await self.clear_document(document_id)

        else:
            for document_id in list(self._users.keys()):
                if user_id in self._users[document_id]:
                    self._users[document_id].remove(user_id)
                    if not self._users[document_id]:
                        del self._users[document_id]

                        await self.clear_document(document_id)

    async def clear_document(self, document_id: str):
        """
        清理文档的所有数据和状态

        参数:
            document_id: 文档 ID
        """
        document_id = document_id.replace(':', '_')

        if self._redis:
            redis_key = f'{self._redis_key_prefix}:{document_id}:updates'
            await self._redis.delete(redis_key)
            redis_users_key = f'{self._redis_key_prefix}:{document_id}:users'
            await self._redis.delete(redis_users_key)
        else:
            if document_id in self._updates:
                del self._updates[document_id]
            if document_id in self._users:
                del self._users[document_id]
