"""
工具模块: 认证工具 (Authentication Utilities)

功能:
- JWT Token 的生成、验证和解析
- 用户密码的哈希和验证
- API Key 认证管理
- 用户认证状态检查

依赖:
- python-jose (JWT 编解码)
- bcrypt (密码哈希)
- cryptography (加密功能)
"""

import logging
import uuid
import jwt
import base64
import hmac
import hashlib
import requests
import os
import bcrypt

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
import json


from datetime import datetime, timedelta
import pytz
from pytz import UTC
from typing import Optional, Union, List, Dict


from open_webui.utils.access_control import has_permission
from open_webui.models.users import Users
from open_webui.models.auths import Auths


from open_webui.constants import ERROR_MESSAGES

from open_webui.env import (
    ENABLE_OTEL,
    ENABLE_PASSWORD_VALIDATION,
    OFFLINE_MODE,
    LICENSE_BLOB,
    PASSWORD_VALIDATION_HINT,
    PASSWORD_VALIDATION_REGEX_PATTERN,
    REDIS_KEY_PREFIX,
    pk,
    WEBUI_SECRET_KEY,
    TRUSTED_SIGNATURE_KEY,
    STATIC_DIR,
    WEBUI_AUTH_TRUSTED_EMAIL_HEADER,
)

from fastapi import BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

log = logging.getLogger(__name__)

SESSION_SECRET = WEBUI_SECRET_KEY
ALGORITHM = 'HS256'

##############
# Auth Utils
##############


###############
# 认证工具函数
###############


def verify_signature(payload: str, signature: str) -> bool:
    """
    验证 HMAC 签名

    用于验证来自可信源的请求签名，防止中间人攻击和请求篡改。

    参数:
        payload: 原始载荷数据（字符串）
        signature: Base64 编码的 HMAC-SHA256 签名

    返回:
        bool: 签名验证是否通过
    """
    try:
        expected_signature = base64.b64encode(
            hmac.new(TRUSTED_SIGNATURE_KEY, payload.encode(), hashlib.sha256).digest()
        ).decode()

        # 使用 constant-time 比较防止时序攻击
        return hmac.compare_digest(expected_signature, signature)

    except Exception:
        return False


def override_static(path: str, content: str):
    """
    覆盖静态文件内容

    用于从许可证数据覆盖静态资源文件。

    参数:
        path: 文件路径（相对于静态目录）
        content: Base64 编码的文件内容
    """
    # 安全检查：防止路径遍历攻击
    if '/' in path or '..' in path:
        log.error(f'Invalid path: {path}')
        return

    file_path = os.path.join(STATIC_DIR, path)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    # 将 Base64 内容转换回原始二进制数据并写入文件
    with open(file_path, 'wb') as f:
        f.write(base64.b64decode(content))


def get_license_data(app, key):
    def data_handler(data):
        for k, v in data.items():
            if k == 'resources':
                for p, c in v.items():
                    globals().get('override_static', lambda a, b: None)(p, c)
            elif k == 'count':
                setattr(app.state, 'USER_COUNT', v)
            elif k == 'name':
                setattr(app.state, 'WEBUI_NAME', v)
            elif k == 'metadata':
                setattr(app.state, 'LICENSE_METADATA', v)

    def handler(u):
        res = requests.post(
            f'{u}/api/v1/license/',
            json={'key': key, 'version': '1'},
            timeout=5,
        )

        if getattr(res, 'ok', False):
            payload = getattr(res, 'json', lambda: {})()
            data_handler(payload)
            return True
        else:
            log.error(f'License: retrieval issue: {getattr(res, "text", "unknown error")}')

    if key:
        us = [
            'https://api.openwebui.com',
            'https://licenses.api.openwebui.com',
        ]
        try:
            for u in us:
                if handler(u):
                    return True
        except Exception as ex:
            log.exception(f'License: Uncaught Exception: {ex}')

    try:
        if LICENSE_BLOB:
            nl = 12
            kb = hashlib.sha256((key.replace('-', '').upper()).encode()).digest()

            def nt(b):
                return b[:nl], b[nl:]

            lb = base64.b64decode(LICENSE_BLOB)
            ln, lt = nt(lb)

            aesgcm = AESGCM(kb)
            p = json.loads(aesgcm.decrypt(ln, lt, None))
            pk.verify(base64.b64decode(p['s']), p['p'].encode())

            pb = base64.b64decode(p['p'])
            pn, pt = nt(pb)

            data = json.loads(aesgcm.decrypt(pn, pt, None).decode())

            exp = data.get('exp')
            if exp:
                if isinstance(exp, str):
                    from datetime import date

                    exp = date.fromisoformat(exp)
                if exp < datetime.now().date():
                    return False

            data_handler(data)
            return True
    except Exception as e:
        log.error(f'License: {e}')

    return False


bearer_security = HTTPBearer(auto_error=False)


def get_password_hash(password: str) -> str:
    """
    哈希用户密码

    使用 bcrypt 算法对密码进行单向哈希存储。bcrypt 会自动生成随机盐值，
    因此相同的密码每次哈希结果都不同。

    参数:
        password: 明文密码字符串

    返回:
        str: Base64 编码的 bcrypt 哈希字符串
    """
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def validate_password(password: str) -> bool:
    """
    验证密码格式

    检查密码是否符合系统设置的验证规则（长度、复杂度等）。

    参数:
        password: 待验证的密码字符串

    返回:
        bool: 密码是否通过验证

    异常:
        Exception: 密码不符合要求时抛出异常
    """
    # bcrypt 最多支持 72 字节的输入，超过部分会被截断
    if len(password.encode('utf-8')) > 72:
        raise Exception(
            ERROR_MESSAGES.PASSWORD_TOO_LONG,
        )

    if ENABLE_PASSWORD_VALIDATION:
        # 检查密码复杂度是否满足正则表达式要求
        if not PASSWORD_VALIDATION_REGEX_PATTERN.match(password):
            raise Exception(ERROR_MESSAGES.INVALID_PASSWORD(PASSWORD_VALIDATION_HINT))

    return True


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码是否匹配

    使用 bcrypt 验证明文密码与存储的哈希值是否匹配。

    参数:
        plain_password: 用户输入的明文密码
        hashed_password: 数据库中存储的 bcrypt 哈希值

    返回:
        bool: 密码是否匹配，匹配返回 True
        None: 当哈希值为空时返回 None
    """
    return (
        bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8'),
        )
        if hashed_password
        else None
    )


# 愿签发者的名字被铭记在每一个关卡，
# 愿其中的声明在创造者身后长久地受到尊重，
# 纵使会话已经关闭。
def create_token(data: dict, expires_delta: Union[timedelta, None] = None) -> str:
    """
    创建 JWT Token

    生成一个新的 JSON Web Token，包含用户信息和可选的过期时间。
    每个 token 都有唯一的 jti（JWT ID）用于撤销追踪。

    参数:
        data: 要编码到 token 中的数据字典，通常包含用户 ID
        expires_delta: 可选的过期时间增量，如果不提供则使用默认配置

    返回:
        str: 编码后的 JWT 字符串
    """
    payload = data.copy()

    # 添加过期时间（如果指定）
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
        payload.update({'exp': expire})

    # 生成唯一标识符用于 token 撤销
    jti = str(uuid.uuid4())
    payload.update({'jti': jti, 'iat': datetime.now(UTC)})

    encoded_jwt = jwt.encode(payload, SESSION_SECRET, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Optional[dict]:
    """
    解码 JWT Token

    验证并解码 JWT token，返回其中的 payload 数据。

    参数:
        token: JWT 格式的 token 字符串

    返回:
        dict: 包含用户信息的 payload（包含 user_id, exp, iat 等）
        None: Token 无效或已过期时返回 None
    """
    try:
        decoded = jwt.decode(token, SESSION_SECRET, algorithms=[ALGORITHM])
        return decoded
    except Exception:
        return None


async def is_valid_token(request, decoded) -> bool:
    """
    检查 JWT Token 是否已被撤销

    支持两种撤销机制：
    1. 单 token 撤销（基于 jti）：用于用户主动登出
    2. 用户级别撤销（基于 revoked_at）：用于 OIDC 后台登出，
       当用户的 iat（签发时间）早于 revoked_at 时拒绝

    参数:
        request: FastAPI 请求对象，用于访问 Redis
        decoded: 解码后的 token payload 字典

    返回:
        bool: Token 是否有效（未被撤销）
    """
    if request.app.state.redis:
        # 单 token 撤销机制
        jti = decoded.get('jti')
        if jti:
            revoked = await request.app.state.redis.get(f'{REDIS_KEY_PREFIX}:auth:token:{jti}:revoked')
            if revoked:
                return False

        # 用户级别撤销（OIDC 后台登出）
        user_id = decoded.get('id')
        if user_id:
            revoked_at = await request.app.state.redis.get(f'{REDIS_KEY_PREFIX}:auth:user:{user_id}:revoked_at')
            if revoked_at:
                try:
                    revoked_at_ts = int(revoked_at)
                    token_iat = decoded.get('iat')
                    # 没有 iat 意味着是旧版 token，无法验证签发时间，拒绝
                    if token_iat is None or token_iat <= revoked_at_ts:
                        return False
                except (ValueError, TypeError):
                    pass

    return True


async def invalidate_token(request, token):
    """
    撤销 JWT Token

    将 token 标记为已撤销，存储到 Redis 中并设置与 token 过期时间相同的 TTL。

    参数:
        request: FastAPI 请求对象
        token: 要撤销的 JWT token 字符串
    """
    decoded = decode_token(token)

    # 如果 token 无效或已过期，无需撤销
    if not decoded:
        return

    # 需要 Redis 来存储已撤销的 token
    if request.app.state.redis:
        jti = decoded.get('jti')
        exp = decoded.get('exp')

        if jti and exp:
            # 计算 token 剩余的有效时间作为 Redis 键的过期时间
            ttl = exp - int(datetime.now(UTC).timestamp())

            if ttl > 0:
                # 在 Redis 中存储已撤销的 token，设置自动过期
                await request.app.state.redis.set(
                    f'{REDIS_KEY_PREFIX}:auth:token:{jti}:revoked',
                    '1',
                    ex=ttl,
                )


def extract_token_from_auth_header(auth_header: str):
    """
    从 Authorization header 中提取 Token

    参数:
        auth_header: Authorization header 值，格式为 "Bearer <token>"

    返回:
        str: 提取后的 token 字符串（不包含 "Bearer " 前缀）
    """
    return auth_header[len('Bearer ') :]


def create_api_key():
    """
    创建 API Key

    生成一个新的随机 API Key，格式为 sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

    返回:
        str: 新生成的 API Key 字符串
    """
    key = str(uuid.uuid4()).replace('-', '')
    return f'sk-{key}'


def get_http_authorization_cred(auth_header: Optional[str]):
    """
    解析 HTTP Authorization 凭证

    将 Authorization header 解析为 HTTPAuthorizationCredentials 对象。

    参数:
        auth_header: Authorization header 字符串，格式为 "Scheme credentials"

    返回:
        HTTPAuthorizationCredentials: 包含 scheme 和 credentials 的对象
        None: header 为空或解析失败时返回 None
    """
    if not auth_header:
        return None
    try:
        scheme, credentials = auth_header.split(' ')
        return HTTPAuthorizationCredentials(scheme=scheme, credentials=credentials)
    except Exception:
        return None


async def get_current_user(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    auth_token: HTTPAuthorizationCredentials = Depends(bearer_security),
    # 注意：这里故意不使用 Depends(get_session)。
    # 会话在内部使用短生命周期上下文管理器管理。
    # 这样可以确保连接在 auth 查询后立即释放，
    # 而不是在整个请求期间保持（例如 30+ 秒的 LLM 调用）。
):
    """
    获取当前认证用户

    从请求中提取并验证用户身份。支持的认证方式：
    1. Bearer Token（JWT）：从 Authorization header 或 cookie 中获取
    2. API Key：以 sk- 开头的密钥

    参数:
        request: FastAPI 请求对象
        response: FastAPI 响应对象
        background_tasks: 后台任务管理器
        auth_token: HTTP Bearer 凭证（自动从 Authorization header 解析）

    返回:
        UserModel: 认证成功的用户对象

    异常:
        HTTPException(401): 认证失败时抛出
    """
    token = None

    # 从 Bearer token 中获取凭证
    if auth_token is not None:
        token = auth_token.credentials

    # 尝试从 cookie 中获取 token
    if token is None and 'token' in request.cookies:
        token = request.cookies.get('token')

    # 回退到 request.state.token（例如 x-api-key header 设置的）
    if token is None and hasattr(request.state, 'token') and request.state.token:
        token = request.state.token.credentials

    if token is None:
        raise HTTPException(status_code=401, detail='Not authenticated')

    # API Key 认证
    if token.startswith('sk-'):
        user = await get_current_user_by_api_key(request, token)

        # 添加用户信息到当前 tracing span
        if ENABLE_OTEL:
            from opentelemetry import trace

            current_span = trace.get_current_span()
            if current_span:
                current_span.set_attribute('client.user.id', user.id)
                current_span.set_attribute('client.user.email', user.email)
                current_span.set_attribute('client.user.role', user.role)
                current_span.set_attribute('client.auth.type', 'api_key')

        return user

    # JWT Token 认证
    try:
        try:
            data = decode_token(token)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Invalid token',
            )

        if data is not None and 'id' in data:
            # 检查 token 是否已被撤销
            if data.get('jti') and not await is_valid_token(request, data):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail='Invalid token',
                )

            user = await Users.get_user_by_id(data['id'])
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=ERROR_MESSAGES.INVALID_TOKEN,
                )
            else:
                # 验证受信任的 email header（如果配置了）
                if WEBUI_AUTH_TRUSTED_EMAIL_HEADER:
                    trusted_email = request.headers.get(WEBUI_AUTH_TRUSTED_EMAIL_HEADER, '').lower()
                    if trusted_email and user.email != trusted_email:
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail='User mismatch. Please sign in again.',
                        )

                # 添加用户信息到当前 tracing span
                if ENABLE_OTEL:
                    from opentelemetry import trace

                    current_span = trace.get_current_span()
                    if current_span:
                        current_span.set_attribute('client.user.id', user.id)
                        current_span.set_attribute('client.user.email', user.email)
                        current_span.set_attribute('client.user.role', user.role)
                        current_span.set_attribute('client.auth.type', 'jwt')

                # 通过 asyncio.create_task 异步更新用户最后活跃时间（不阻塞）
                import asyncio

                asyncio.create_task(Users.update_last_active_by_id(user.id))
            return user
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ERROR_MESSAGES.UNAUTHORIZED,
            )
    except Exception as e:
        # 删除无效的 token cookie
        if request.cookies.get('token'):
            response.delete_cookie('token')

        if request.cookies.get('oauth_id_token'):
            response.delete_cookie('oauth_id_token')

        # 删除 OAuth 会话（如果存在）
        if request.cookies.get('oauth_session_id'):
            response.delete_cookie('oauth_session_id')

        raise e


async def get_current_user_by_api_key(request, api_key: str):
    """
    通过 API Key 获取用户

    验证 API Key 并返回关联的用户。支持端点限制检查。

    参数:
        request: FastAPI 请求对象
        api_key: API Key 字符串（以 sk- 开头）

    返回:
        UserModel: 认证成功的用户对象

    异常:
        HTTPException(401): API Key 无效
        HTTPException(403): 用户无权使用 API Key 或访问受限端点
    """
    # 每个函数调用在内部管理自己的短生命周期会话
    user = await Users.get_user_by_api_key(api_key)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.INVALID_TOKEN,
        )

    # 检查用户是否有权使用 API Key 功能
    if not request.state.enable_api_keys or (
        user.role != 'admin'
        and not await has_permission(
            user.id,
            'features.api_keys',
            request.app.state.config.USER_PERMISSIONS,
        )
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=ERROR_MESSAGES.API_KEY_NOT_ALLOWED)

    # 端点限制检查 - 在这里检查（而非中间件）以便无论 API Key 如何传输都适用
    #（Authorization header、cookie、x-api-key header 等）
    if request.app.state.config.ENABLE_API_KEYS_ENDPOINT_RESTRICTIONS:
        allowed_paths = [
            path.strip() for path in str(request.app.state.config.API_KEYS_ALLOWED_ENDPOINTS).split(',') if path.strip()
        ]
        request_path = request.url.path
        is_allowed = any(request_path == allowed or request_path.startswith(allowed + '/') for allowed in allowed_paths)
        if not is_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
            )

    # 添加用户信息到当前 span
    if ENABLE_OTEL:
        from opentelemetry import trace

        current_span = trace.get_current_span()
        if current_span:
            current_span.set_attribute('client.user.id', user.id)
            current_span.set_attribute('client.user.email', user.email)
            current_span.set_attribute('client.user.role', user.role)
            current_span.set_attribute('client.auth.type', 'api_key')

    await Users.update_last_active_by_id(user.id)
    return user


def get_verified_user(user=Depends(get_current_user)):
    """
    获取已验证的用户（仅限普通用户和管理员）

    依赖 get_current_user 进行身份验证，然后检查用户角色是否为 'user' 或 'admin'。

    参数:
        user: 通过 Depends 注入的已认证用户

    返回:
        UserModel: 验证通过的用户对象

    异常:
        HTTPException(401): 用户角色不是 user 或 admin
    """
    if user.role not in {'user', 'admin'}:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )
    return user


def get_admin_user(user=Depends(get_current_user)):
    """
    获取管理员用户

    依赖 get_current_user 进行身份验证，然后检查用户角色是否为 'admin'。

    参数:
        user: 通过 Depends 注入的已认证用户

    返回:
        UserModel: 管理员用户对象

    异常:
        HTTPException(401): 用户角色不是 admin
    """
    if user.role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )
    return user


async def create_admin_user(email: str, password: str, name: str = 'Admin'):
    """
    创建管理员用户（用于无人值守/自动化部署）

    当环境变量中配置了管理员邮箱和密码时，在系统首次启动时创建管理员账户。

    参数:
        email: 管理员邮箱地址
        password: 管理员密码
        name: 管理员显示名称，默认为 'Admin'

    返回:
        UserModel: 创建成功返回用户对象
        None: 用户已存在或创建失败时返回 None
    """

    if not email or not password:
        return None

    # 如果已有用户，跳过创建
    if await Users.has_users():
        log.debug('Users already exist, skipping admin creation')
        return None

    log.info(f'Creating admin account from environment variables: {email}')
    try:
        hashed = get_password_hash(password)
        user = await Auths.insert_new_auth(
            email=email.lower(),
            password=hashed,
            name=name,
            role='admin',
        )
        if user:
            log.info(f'Admin account created successfully: {email}')
            return user
        else:
            log.error('Failed to create admin account from environment variables')
            return None
    except Exception as e:
        log.error(f'Error creating admin account: {e}')
        return None
