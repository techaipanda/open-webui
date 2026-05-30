"""
工具模块: 聊天工具 (Chat Utilities)

功能:
- 聊天补全生成（generate_chat_completion）
- 直接连接模式的聊天生成（generate_direct_chat_completion）
- 聊天完成后处理（chat_completed）

依赖:
- fastapi, starlette
- open_webui.socket.main
- open_webui.routers.openai
- open_webui.routers.ollama
- open_webui.models
"""

import time
import logging
import sys

from aiocache import cached
from typing import Any, Optional
import random
import json

import uuid
import asyncio

from fastapi import HTTPException, Request, status
from starlette.responses import Response, StreamingResponse, JSONResponse


from open_webui.models.users import UserModel

from open_webui.socket.main import (
    sio,
    get_event_call,
    get_event_emitter,
)
from open_webui.functions import generate_function_chat_completion

from open_webui.routers.openai import (
    generate_chat_completion as generate_openai_chat_completion,
)

from open_webui.routers.ollama import (
    generate_chat_completion as generate_ollama_chat_completion,
)

from open_webui.routers.pipelines import (
    process_pipeline_inlet_filter,
    process_pipeline_outlet_filter,
)

from open_webui.models.functions import Functions
from open_webui.models.models import Models

from open_webui.utils.models import get_all_models, check_model_access
from open_webui.utils.payload import convert_payload_openai_to_ollama
from open_webui.utils.response import (
    convert_response_ollama_to_openai,
    convert_streaming_response_ollama_to_openai,
)
from open_webui.utils.filter import (
    get_sorted_filter_ids,
    process_filter_functions,
)

from open_webui.env import GLOBAL_LOG_LEVEL, BYPASS_MODEL_ACCESS_CONTROL

logging.basicConfig(stream=sys.stdout, level=GLOBAL_LOG_LEVEL)
log = logging.getLogger(__name__)


# 当问题已被问起时，让沉默不是答案。
# 但如果答案必须等待，让它诚实到来。
async def generate_direct_chat_completion(
    request: Request,
    form_data: dict,
    user: Any,
    models: dict,
):
    """
    生成直接连接的聊天补全

    用于 WebSocket 直接连接场景，通过事件调用机制与客户端通信。

    参数:
        request: FastAPI 请求对象
        form_data: 聊天请求表单数据
        user: 当前认证用户
        models: 可用模型字典
    """
    log.info('generate_direct_chat_completion')

    metadata = form_data.pop('metadata', {})

    user_id = metadata.get('user_id')
    session_id = metadata.get('session_id')
    request_id = str(uuid.uuid4())  # 生成唯一请求 ID

    event_caller = await get_event_call(metadata)
    if event_caller is None:
        raise Exception(
            'Direct connection requires an active WebSocket session; '
            'cannot generate completion in this context (e.g. background task).'
        )

    # 构建 WebSocket 频道标识
    channel = f'{user_id}:{session_id}:{request_id}'
    logging.info(f'WebSocket channel: {channel}')

    if form_data.get('stream'):
        q = asyncio.Queue()

        async def message_listener(sid, data):
            """
            处理接收到的 socket 消息并推入队列
            """
            await q.put(data)

        # 注册监听器
        sio.on(channel, message_listener)

        # 在后台启动聊天补全处理
        res = await event_caller(
            {
                'type': 'request:chat:completion',
                'data': {
                    'form_data': form_data,
                    'model': models[form_data['model']],
                    'channel': channel,
                    'session_id': session_id,
                },
            }
        )

        log.info(f'res: {res}')

        if res.get('status', False):
            # 定义流式响应生成器
            async def event_generator():
                nonlocal q
                try:
                    while True:
                        data = await q.get()  # 等待新消息
                        if isinstance(data, dict):
                            if 'done' in data and data['done']:
                                break  # 收到 'done' 时停止流式传输

                            yield f'data: {json.dumps(data)}\n\n'
                        elif isinstance(data, str):
                            if 'data:' in data:
                                yield f'{data}\n\n'
                            else:
                                yield f'data: {data}\n\n'
                except Exception as e:
                    log.debug(f'Error in event generator: {e}')
                    pass

            # 定义后台任务运行事件生成器
            async def background():
                try:
                    del sio.handlers['/'][channel]
                except Exception as e:
                    pass

            # 返回流式响应
            return StreamingResponse(event_generator(), media_type='text/event-stream', background=background)
        else:
            raise Exception(str(res))
    else:
        res = await event_caller(
            {
                'type': 'request:chat:completion',
                'data': {
                    'form_data': form_data,
                    'model': models[form_data['model']],
                    'channel': channel,
                    'session_id': session_id,
                },
            }
        )

        if 'error' in res and res['error']:
            raise Exception(res['error'])

        return res


async def generate_chat_completion(
    request: Request,
    form_data: dict,
    user: Any,
    bypass_filter: bool = False,
    bypass_system_prompt: bool = False,
):
    """
    生成聊天补全

    核心聊天补全生成函数，处理来自前端或 API 的聊天请求。
    支持多种模型类型（OpenAI、Ollama、Function、Pipe、Arena）。

    参数:
        request: FastAPI 请求对象
        form_data: 聊天请求表单数据，包含 messages、model 等
        user: 当前认证用户
        bypass_filter: 是否跳过模型访问过滤（默认 False）
        bypass_system_prompt: 是否跳过系统提示处理（默认 False）

    返回:
        dict 或 StreamingResponse: 聊天补全响应
    """
    log.debug(f'generate_chat_completion: {form_data}')
    if BYPASS_MODEL_ACCESS_CONTROL:
        bypass_filter = True

    # 通过 request.state 传播 bypass_filter，以便下游路由处理器可以读取
    # 而无需将其作为查询参数暴露
    request.state.bypass_filter = bypass_filter

    # 合并 metadata
    if hasattr(request.state, 'metadata'):
        if 'metadata' not in form_data:
            form_data['metadata'] = request.state.metadata
        else:
            form_data['metadata'] = {
                **form_data['metadata'],
                **request.state.metadata,
            }

    # 直接连接模式：合并模型到服务器模型以便任务函数可以解析
    if getattr(request.state, 'direct', False) and hasattr(request.state, 'model'):
        models = {
            **request.app.state.MODELS,
            request.state.model['id']: request.state.model,
        }
        log.debug(f'direct connection to model: {request.state.model["id"]}')
    else:
        models = request.app.state.MODELS

    model_id = form_data['model']
    if model_id not in models:
        raise Exception('Model not found')

    model = models[model_id]

    # 直接连接模式使用专用生成函数
    if getattr(request.state, 'direct', False) and model_id == getattr(request.state, 'model', {}).get('id'):
        return await generate_direct_chat_completion(request, form_data, user=user, models=models)
    else:
        # 检查用户是否有权访问该模型
        if not bypass_filter and user.role == 'user':
            try:
                await check_model_access(user, model)
            except Exception as e:
                raise e

        # Arena 模型 - 子模型已在 process_chat_payload 中解析
        # 将 selected_model_id 注入响应以便前端使用
        metadata = form_data.get('metadata', {})
        selected_model_id = metadata.pop('selected_model_id', None)
        # 也从 request.state.metadata 中清除以防止在递归调用时重新添加
        if hasattr(request.state, 'metadata'):
            request.state.metadata.pop('selected_model_id', None)

        # 回退：如果 generate_chat_completion 是从没有经过 process_chat_payload
        # 的路径调用的（例如用于标题/跟进/标签生成的后台任务），现在解析
        if not selected_model_id and model.get('owned_by') == 'arena':
            model_ids = model.get('info', {}).get('meta', {}).get('model_ids')
            filter_mode = model.get('info', {}).get('meta', {}).get('filter_mode')
            if model_ids and filter_mode == 'exclude':
                model_ids = [
                    available_model['id']
                    for available_model in list(request.app.state.MODELS.values())
                    if available_model.get('owned_by') != 'arena' and available_model['id'] not in model_ids
                ]

            if isinstance(model_ids, list) and model_ids:
                selected_model_id = random.choice(model_ids)
            else:
                model_ids = [
                    available_model['id']
                    for available_model in list(request.app.state.MODELS.values())
                    if available_model.get('owned_by') != 'arena'
                ]
                selected_model_id = random.choice(model_ids)

            form_data['model'] = selected_model_id

        if selected_model_id:
            if form_data.get('stream') == True:

                async def stream_wrapper(stream):
                    yield f'data: {json.dumps({"selected_model_id": selected_model_id})}\n\n'
                    async for chunk in stream:
                        yield chunk

                response = await generate_chat_completion(
                    request,
                    form_data,
                    user,
                    bypass_filter=True,
                    bypass_system_prompt=bypass_system_prompt,
                )
                return StreamingResponse(
                    stream_wrapper(response.body_iterator),
                    media_type='text/event-stream',
                    background=response.background,
                )
            else:
                return {
                    **(
                        await generate_chat_completion(
                            request,
                            form_data,
                            user,
                            bypass_filter=True,
                            bypass_system_prompt=bypass_system_prompt,
                        )
                    ),
                    'selected_model_id': selected_model_id,
                }

        # Pipe 模型：使用函数调用生成
        if model.get('pipe'):
            return await generate_function_chat_completion(request, form_data, user=user, models=models)
        # Ollama 模型：使用 /ollama/api/chat 端点
        if model.get('owned_by') == 'ollama':
            form_data = convert_payload_openai_to_ollama(form_data)
            response = await generate_ollama_chat_completion(
                request=request,
                form_data=form_data,
                user=user,
                bypass_system_prompt=bypass_system_prompt,
            )
            if form_data.get('stream'):
                response.headers['content-type'] = 'text/event-stream'
                return StreamingResponse(
                    convert_streaming_response_ollama_to_openai(response),
                    headers=dict(response.headers),
                    background=response.background,
                )
            else:
                return convert_response_ollama_to_openai(response)
        # 默认：使用 OpenAI 兼容端点
        else:
            return await generate_openai_chat_completion(
                request=request,
                form_data=form_data,
                user=user,
                bypass_system_prompt=bypass_system_prompt,
            )


# 聊天补全的别名
chat_completion = generate_chat_completion


async def chat_completed(request: Request, form_data: dict, user: Any):
    """
    处理聊天完成后的事件

    在聊天完成后调用管道出口过滤器并更新消息状态。

    参数:
        request: FastAPI 请求对象
        form_data: 聊天完成后的表单数据
        user: 当前认证用户

    返回:
        dict: 处理后的结果
    """
    if not request.app.state.MODELS:
        await get_all_models(request, user=user)

    if getattr(request.state, 'direct', False) and hasattr(request.state, 'model'):
        models = {
            **request.app.state.MODELS,
            request.state.model['id']: request.state.model,
        }
    else:
        models = request.app.state.MODELS

    data = form_data

    if not data.get('id'):
        raise Exception('Missing message id')

    model_id = data['model']
    if model_id not in models:
        raise Exception('Model not found')

    model = models[model_id]

    try:
        data = await process_pipeline_outlet_filter(request, data, user, models)
    except HTTPException:
        raise
    except Exception as e:
        raise Exception(f'Error: {e}')

    if not data.get('id'):
        raise Exception('Missing message id')

    # 构建元数据用于事件发射器
    metadata = {
        'chat_id': data['chat_id'],
        'message_id': data['id'],
        'filter_ids': data.get('filter_ids', []),
        'session_id': data['session_id'],
        'user_id': user.id,
    }

    extra_params = {
        '__event_emitter__': await get_event_emitter(metadata),
        '__event_call__': await get_event_call(metadata),
        '__user__': user.model_dump() if isinstance(user, UserModel) else {},
        '__metadata__': metadata,
        '__request__': request,
        '__model__': model,
    }

    try:
        filter_ids = await get_sorted_filter_ids(request, model, metadata.get('filter_ids', []))
        filter_functions = await Functions.get_functions_by_ids(filter_ids)

        result, _ = await process_filter_functions(
            request=request,
            filter_functions=filter_functions,
            filter_type='outlet',
            form_data=data,
            extra_params=extra_params,
        )
        return result
    except Exception as e:
        raise Exception(f'Error: {e}')
