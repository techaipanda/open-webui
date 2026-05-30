"""
模块名称: 函数调用模块 (Functions Module)
功能: 管理管道（Pipe）函数调用、聊天补全生成、函数模型发现
依赖: asyncio, inspect, json, logging, pydantic, fastapi
说明:
  - 支持同步和异步管道函数执行
  - 处理流式和非流式响应
  - 支持函数流（Function Streams）和子管道（Sub-pipes）
  - 集成OAuth令牌管理和事件发射
"""

import logging
import sys
import inspect
import json
import asyncio

from pydantic import BaseModel
from typing import AsyncGenerator, Generator, Iterator
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from starlette.responses import Response, StreamingResponse


from open_webui.constants import ERROR_MESSAGES
from open_webui.socket.main import (
    get_event_call,
    get_event_emitter,
)


from open_webui.models.users import UserModel
from open_webui.models.functions import Functions
from open_webui.models.models import Models

from open_webui.utils.plugin import (
    load_function_module_by_id,
    get_function_module_from_cache,
)
from open_webui.utils.access_control import check_model_access

from open_webui.env import GLOBAL_LOG_LEVEL, BYPASS_MODEL_ACCESS_CONTROL
from open_webui.config import BYPASS_ADMIN_ACCESS_CONTROL

from open_webui.utils.misc import (
    add_or_update_system_message,
    get_last_user_message,
    prepend_to_first_user_message_content,
    openai_chat_chunk_message_template,
    openai_chat_completion_message_template,
)
from open_webui.utils.payload import (
    apply_model_params_to_body_openai,
    apply_system_prompt_to_body,
)

logging.basicConfig(stream=sys.stdout, level=GLOBAL_LOG_LEVEL)
log = logging.getLogger(__name__)


async def get_function_module_by_id(request: Request, pipe_id: str):
    """
    根据管道ID获取函数模块
    加载并初始化函数的Valves配置

    参数:
        request: FastAPI 请求对象
        pipe_id: 管道唯一标识符

    返回:
        function_module: 已加载并配置好Valves的函数模块
    """
    function_module, _, _ = await get_function_module_from_cache(request, pipe_id)

    if hasattr(function_module, 'valves') and hasattr(function_module, 'Valves'):
        Valves = function_module.Valves
        valves = await Functions.get_function_valves_by_id(pipe_id)

        if valves:
            try:
                # 使用保存的Valves配置初始化函数模块
                function_module.valves = Valves(**{k: v for k, v in valves.items() if v is not None})
            except Exception as e:
                log.exception(f'Error loading valves for function {pipe_id}: {e}')
                raise e
        else:
            function_module.valves = Valves()

    return function_module


async def get_function_models(request):
    """
    获取所有可用的函数管道模型
    发现并返回所有活动的管道（Pipe）函数，包括单管道和歧管（Manifold）管道

    返回:
        list: 管道模型列表，每项包含id、name、object、owned_by等信息
    """
    pipes = await Functions.get_functions_by_type('pipe', active_only=True)
    pipe_models = []

    for pipe in pipes:
        try:
            function_module = await get_function_module_by_id(request, pipe.id)

            has_user_valves = False
            if hasattr(function_module, 'UserValves'):
                has_user_valves = True

            # 检查函数是否为歧管（Manifold）类型（包含多个子管道）
            if hasattr(function_module, 'pipes'):
                sub_pipes = []

                # 处理 pipes 属性：可能是列表、同步函数或异步函数
                try:
                    if callable(function_module.pipes):
                        if asyncio.iscoroutinefunction(function_module.pipes):
                            sub_pipes = await function_module.pipes()
                        else:
                            sub_pipes = function_module.pipes()
                    else:
                        sub_pipes = function_module.pipes
                except Exception as e:
                    log.exception(e)
                    sub_pipes = []

                log.debug(f"get_function_models: function '{pipe.id}' is a manifold of {sub_pipes}")

                # 为每个子管道创建模型条目
                for p in sub_pipes:
                    sub_pipe_id = f'{pipe.id}.{p["id"]}'
                    sub_pipe_name = p['name']

                    # 如果函数模块有name属性，则添加到子管道名称前
                    if hasattr(function_module, 'name'):
                        sub_pipe_name = f'{function_module.name}{sub_pipe_name}'

                    pipe_flag = {'type': pipe.type}

                    pipe_models.append(
                        {
                            'id': sub_pipe_id,
                            'name': sub_pipe_name,
                            'object': 'model',
                            'created': pipe.created_at,
                            'owned_by': 'openai',
                            'pipe': pipe_flag,
                            'has_user_valves': has_user_valves,
                        }
                    )
            else:
                # 单管道函数
                pipe_flag = {'type': 'pipe'}

                log.debug(
                    f"get_function_models: function '{pipe.id}' is a single pipe {{ 'id': {pipe.id}, 'name': {pipe.name} }}"
                )

                pipe_models.append(
                    {
                        'id': pipe.id,
                        'name': pipe.name,
                        'object': 'model',
                        'created': pipe.created_at,
                        'owned_by': 'openai',
                        'pipe': pipe_flag,
                        'has_user_valves': has_user_valves,
                    }
                )
        except Exception as e:
            log.exception(e)
            continue

    return pipe_models


async def generate_function_chat_completion(request, form_data, user, models: dict = {}):
    """
    生成函数管道聊天补全
    处理管道函数的调用，包括流式和非流式响应

    参数:
        request: FastAPI 请求对象
        form_data: 聊天补全请求表单数据
        user: 当前用户对象
        models: 可用的模型字典（可选）

    返回:
        StreamingResponse 或 dict: 流式响应或标准响应
    """
    async def execute_pipe(pipe, params):
        """执行管道函数，支持同步和异步函数"""
        if inspect.iscoroutinefunction(pipe):
            return await pipe(**params)
        else:
            return pipe(**params)

    async def get_message_content(res: str | Generator | AsyncGenerator) -> str:
        """
        从响应中提取消息内容
        支持字符串、生成器和异步生成器
        """
        if isinstance(res, str):
            return res
        if isinstance(res, Generator):
            return ''.join(map(str, res))
        if isinstance(res, AsyncGenerator):
            return ''.join([str(stream) async for stream in res])

    def process_line(form_data: dict, line):
        """
        处理管道输出的每一行
        将不同类型的输出转换为 SSE 格式
        """
        # 处理 Pydantic 模型
        if isinstance(line, BaseModel):
            line = line.model_dump_json()
            line = f'data: {line}'
        # 处理字典类型
        if isinstance(line, dict):
            line = f'data: {json.dumps(line)}'

        # 尝试解码字节串
        try:
            line = line.decode('utf-8')
        except Exception:
            pass

        # 确保格式为 SSE（Server-Sent Events）
        if line.startswith('data:'):
            return f'{line}\n\n'
        else:
            line = openai_chat_chunk_message_template(form_data['model'], line)
            return f'data: {json.dumps(line)}\n\n'

    def get_pipe_id(form_data: dict) -> str:
        """
        从表单数据中提取管道ID
        对于歧管管道，ID格式为 'pipe_id.sub_pipe_id'
        """
        pipe_id = form_data['model']
        if '.' in pipe_id:
            pipe_id, _ = pipe_id.split('.', 1)
        return pipe_id

    async def get_function_params(function_module, form_data, user, extra_params=None):
        """
        构建传递给管道函数的参数
        合并表单数据、额外参数和用户Valves配置
        """
        if extra_params is None:
            extra_params = {}

        pipe_id = get_pipe_id(form_data)

        # 获取管道函数的签名
        sig = inspect.signature(function_module.pipe)
        # 合并 body 和 extra_params 中函数签名支持的参数
        params = {'body': form_data} | {k: v for k, v in extra_params.items() if k in sig.parameters}

        # 如果函数支持用户级Valves，加载用户配置
        if '__user__' in params and hasattr(function_module, 'UserValves'):
            user_valves = await Functions.get_user_valves_by_id_and_user_id(pipe_id, user.id)
            try:
                params['__user__']['valves'] = function_module.UserValves(**user_valves)
            except Exception as e:
                log.exception(e)
                params['__user__']['valves'] = function_module.UserValves()

        return params

    # 获取模型信息
    model_id = form_data.get('model')
    model_info = await Models.get_model_by_id(model_id)

    # 从表单数据中提取元数据
    metadata = form_data.pop('metadata', {})

    files = metadata.get('files', [])
    tool_ids = metadata.get('tool_ids', [])
    # 确保 tool_ids 不为 None
    if tool_ids is None:
        tool_ids = []

    # 初始化事件发射器和调用器
    __event_emitter__ = None
    __event_call__ = None
    __task__ = None
    __task_body__ = None

    # 从元数据中提取会话和任务信息
    if metadata:
        if all(k in metadata for k in ('session_id', 'chat_id', 'message_id')):
            __event_emitter__ = await get_event_emitter(metadata)
            __event_call__ = await get_event_call(metadata)
        __task__ = metadata.get('task', None)
        __task_body__ = metadata.get('task_body', None)

    # 获取OAuth令牌（用于第三方认证）
    oauth_token = None
    try:
        oauth_session_id = request.cookies.get('oauth_session_id', None)
        if oauth_session_id:
            oauth_token = await request.app.state.oauth_manager.get_oauth_token(
                user.id,
                oauth_session_id,
            )

        # 后备方案：无cookie时（自动化、API密钥等场景）使用最近的会话
        if oauth_token is None:
            from open_webui.models.oauth_sessions import OAuthSessions

            sessions = await OAuthSessions.get_sessions_by_user_id(user.id)
            if sessions:
                best = max(sessions, key=lambda s: s.updated_at)
                oauth_token = await request.app.state.oauth_manager.get_oauth_token(
                    user.id,
                    best.id,
                )
    except Exception as e:
        log.error(f'Error getting OAuth token: {e}')

    # 构建额外参数
    extra_params = {
        '__event_emitter__': __event_emitter__,
        '__event_call__': __event_call__,
        '__chat_id__': metadata.get('chat_id', None),
        '__session_id__': metadata.get('session_id', None),
        '__message_id__': metadata.get('message_id', None),
        '__task__': __task__,
        '__task_body__': __task_body__,
        '__files__': files,
        '__user__': user.model_dump() if isinstance(user, UserModel) else {},
        '__metadata__': metadata,
        '__oauth_token__': oauth_token,
        '__request__': request,
    }
    extra_params['__tools__'] = metadata.get('tools', {})

    # 应用模型参数和系统提示词
    if model_info:
        if model_info.base_model_id:
            form_data['model'] = model_info.base_model_id

        if not BYPASS_MODEL_ACCESS_CONTROL:
            bypass = isinstance(user, UserModel) and user.role == 'admin' and BYPASS_ADMIN_ACCESS_CONTROL
            await check_model_access(user if isinstance(user, UserModel) else UserModel(**user), model_info, bypass)

        params = model_info.params.model_dump()

        if params:
            system = params.pop('system', None)
            form_data = apply_model_params_to_body_openai(params, form_data)
            form_data = await apply_system_prompt_to_body(system, form_data, metadata, user)

    # 获取并执行管道
    pipe_id = get_pipe_id(form_data)
    function_module = await get_function_module_by_id(request, pipe_id)

    pipe = function_module.pipe
    params = await get_function_params(function_module, form_data, user, extra_params)

    # 流式响应处理
    if form_data.get('stream', False):

        async def stream_content():
            """流式内容生成器"""
            try:
                res = await execute_pipe(pipe, params)

                # 直接返回 StreamingResponse
                if isinstance(res, StreamingResponse):
                    async for data in res.body_iterator:
                        yield data
                    return
                if isinstance(res, dict):
                    yield f'data: {json.dumps(res)}\n\n'
                    return

            except Exception as e:
                log.error(f'Error: {e}')
                yield f'data: {json.dumps({"error": {"detail": str(e)}})}\n\n'
                return

            # 处理字符串响应
            if isinstance(res, str):
                message = openai_chat_chunk_message_template(form_data['model'], res)
                yield f'data: {json.dumps(message)}\n\n'

            # 处理同步生成器
            if isinstance(res, Iterator):
                for line in res:
                    yield process_line(form_data, line)

            # 处理异步生成器
            if isinstance(res, AsyncGenerator):
                async for line in res:
                    yield process_line(form_data, line)

            # 发送结束消息
            if isinstance(res, str) or isinstance(res, Generator):
                finish_message = openai_chat_chunk_message_template(form_data['model'], '')
                finish_message['choices'][0]['finish_reason'] = 'stop'
                yield f'data: {json.dumps(finish_message)}\n\n'
                yield 'data: [DONE]'

        return StreamingResponse(stream_content(), media_type='text/event-stream')
    else:
        # 非流式响应处理
        try:
            res = await execute_pipe(pipe, params)

        except Exception as e:
            log.error(f'Error: {e}')
            return {'error': {'detail': str(e)}}

        if isinstance(res, StreamingResponse) or isinstance(res, dict):
            return res
        if isinstance(res, BaseModel):
            return res.model_dump()

        message = await get_message_content(res)
        return openai_chat_completion_message_template(form_data['model'], message)
