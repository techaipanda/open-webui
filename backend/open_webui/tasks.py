# tasks.py
"""
模块名称: 任务管理模块 (Tasks Module)
功能: 管理异步任务的创建、调度、停止和清理
依赖: asyncio, redis.asyncio, fastapi
说明:
  - 支持本地和分布式任务管理（通过Redis pub/sub）
  - 任务与聊天会话关联，支持批量停止和清理
  - 使用Redis作为消息总线实现跨实例协调
"""
import asyncio
from typing import Dict
from uuid import uuid4
import json
import logging
from redis.asyncio import Redis
from fastapi import Request
from typing import Dict, List, Optional

from open_webui.env import REDIS_KEY_PREFIX

log = logging.getLogger(__name__)

# 追踪活跃任务的全局字典
tasks: Dict[str, asyncio.Task] = {}
# 按项目ID（如chat_id）分组任务
item_tasks = {}


# Redis键前缀，用于存储任务状态
REDIS_TASKS_KEY = f'{REDIS_KEY_PREFIX}:tasks'
REDIS_ITEM_TASKS_KEY = f'{REDIS_KEY_PREFIX}:tasks:item'
# Redis发布/订阅频道，用于分布式任务命令（如停止任务）
REDIS_PUBSUB_CHANNEL = f'{REDIS_KEY_PREFIX}:tasks:commands'


async def redis_task_command_listener(app):
    """
    Redis任务命令监听器
    监听Redis pub/sub频道，接收并执行分布式任务命令（如停止任务）
    """
    redis: Redis = app.state.redis
    pubsub = redis.pubsub()
    await pubsub.subscribe(REDIS_PUBSUB_CHANNEL)

    async for message in pubsub.listen():
        if message['type'] != 'message':
            continue
        try:
            command = json.loads(message['data'])
            if command.get('action') == 'stop':
                task_id = command.get('task_id')
                local_task = tasks.get(task_id)
                if local_task:
                    local_task.cancel()
        except Exception as e:
            log.exception(f'Error handling distributed task command: {e}')


### ------------------------------
### REDIS-ENABLED HANDLERS
### ------------------------------


async def redis_save_task(redis: Redis, task_id: str, item_id: Optional[str]):
    """
    将任务信息保存到Redis
    用于跨实例追踪任务状态
    """
    pipe = redis.pipeline()
    pipe.hset(REDIS_TASKS_KEY, task_id, item_id or '')
    if item_id:
        pipe.sadd(f'{REDIS_ITEM_TASKS_KEY}:{item_id}', task_id)
    await pipe.execute()


async def redis_cleanup_task(redis: Redis, task_id: str, item_id: Optional[str]):
    """
    从Redis中清理任务信息
    清理完成后如果该项目没有剩余任务，则删除该项目的任务集合
    """
    pipe = redis.pipeline()
    pipe.hdel(REDIS_TASKS_KEY, task_id)
    if item_id:
        pipe.srem(f'{REDIS_ITEM_TASKS_KEY}:{item_id}', task_id)
        await pipe.execute()
        # 如果该项目没有剩余任务，删除集合
        if await redis.scard(f'{REDIS_ITEM_TASKS_KEY}:{item_id}') == 0:
            await redis.delete(f'{REDIS_ITEM_TASKS_KEY}:{item_id}')
    else:
        await pipe.execute()


async def redis_list_tasks(redis: Redis) -> List[str]:
    """获取所有任务ID"""
    return list(await redis.hkeys(REDIS_TASKS_KEY))


async def redis_list_item_tasks(redis: Redis, item_id: str) -> List[str]:
    """获取指定项目关联的所有任务ID"""
    return list(await redis.smembers(f'{REDIS_ITEM_TASKS_KEY}:{item_id}'))


async def redis_send_command(redis: Redis, command: dict):
    """
    通过Redis发布任务命令
    支持Redis Cluster模式（使用PUBLISH命令广播到所有节点）
    """
    command_json = json.dumps(command)
    # RedisCluster doesn't expose publish() directly, but the
    # PUBLISH command broadcasts across all cluster nodes server-side.
    if hasattr(redis, 'nodes_manager'):
        await redis.execute_command('PUBLISH', REDIS_PUBSUB_CHANNEL, command_json)
    else:
        await redis.publish(REDIS_PUBSUB_CHANNEL, command_json)


async def cleanup_task(redis, task_id: str, id=None):
    """
    清理已完成或取消的任务
    从全局任务字典和项目任务字典中移除
    """
    if redis:
        await redis_cleanup_task(redis, task_id, id)

    tasks.pop(task_id, None)  # 移除任务

    # 如果提供了ID，也从item_tasks中移除
    if id and task_id in item_tasks.get(id, []):
        item_tasks[id].remove(task_id)
        if not item_tasks[id]:
            item_tasks.pop(id, None)


async def create_task(redis, coroutine, id=None):
    """
    创建新的异步任务并添加到全局任务字典
    返回任务ID和任务对象
    """
    task_id = str(uuid4())  # 生成唯一ID
    task = asyncio.create_task(coroutine)  # 创建任务

    # 添加完成回调用于清理
    task.add_done_callback(lambda t: asyncio.create_task(cleanup_task(redis, task_id, id)))
    tasks[task_id] = task

    # 如果提供了ID，关联任务
    if item_tasks.get(id):
        item_tasks[id].append(task_id)
    else:
        item_tasks[id] = [task_id]

    if redis:
        await redis_save_task(redis, task_id, id)

    return task_id, task


async def list_tasks(redis):
    """列出所有当前活跃的任务ID"""
    if redis:
        return await redis_list_tasks(redis)
    return list(tasks.keys())


async def list_task_ids_by_item_id(redis, id):
    """列出与指定ID关联的所有任务"""
    if redis:
        return await redis_list_item_tasks(redis, id)
    return item_tasks.get(id, [])


async def stop_task(redis, task_id: str):
    """
    取消正在运行的任务并从全局任务列表中移除
    支持分布式停止命令（通过Redis pub/sub）
    """
    if redis:
        # 清理前获取item_id以便同时清理集合
        item_id = await redis.hget(REDIS_TASKS_KEY, task_id)
        # PUBSUB: 所有实例检查并停止该任务
        await redis_send_command(
            redis,
            {
                'action': 'stop',
                'task_id': task_id,
            },
        )
        # 直接清理Redis（hdel/srem是幂等的）
        await redis_cleanup_task(redis, task_id, item_id or None)
        return {'status': True, 'message': f'Task {task_id} stopped.'}

    task = tasks.pop(task_id, None)
    if not task:
        return {'status': False, 'message': f'Task with ID {task_id} not found.'}

    task.cancel()  # 请求取消任务
    try:
        await task  # 等待任务处理取消
    except asyncio.CancelledError:
        # 任务成功取消
        return {'status': True, 'message': f'Task {task_id} successfully stopped.'}

    if task.cancelled() or task.done():
        return {'status': True, 'message': f'Task {task_id} successfully cancelled.'}

    return {'status': True, 'message': f'Cancellation requested for {task_id}.'}


async def stop_item_tasks(redis: Redis, item_id: str):
    """
    停止与指定项目ID关联的所有任务
    """
    task_ids = await list_task_ids_by_item_id(redis, item_id)
    if not task_ids:
        return {'status': True, 'message': f'No tasks found for item {item_id}.'}

    for task_id in task_ids:
        result = await stop_task(redis, task_id)
        if not result['status']:
            return result  # 返回第一个失败

    return {'status': True, 'message': f'All tasks for item {item_id} stopped.'}


async def has_active_tasks(redis, chat_id: str) -> bool:
    """检查聊天是否有任何活跃任务"""
    task_ids = await list_task_ids_by_item_id(redis, chat_id)
    return len(task_ids) > 0


async def get_active_chat_ids(redis, chat_ids: List[str]) -> List[str]:
    """过滤出有活跃任务的聊天ID列表"""
    active = []
    for chat_id in chat_ids:
        if await has_active_tasks(redis, chat_id):
            active.append(chat_id)
    return active
