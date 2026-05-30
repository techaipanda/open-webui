"""
模块名称: 常量定义模块 (Constants Module)
功能: 定义全局错误消息、Webhook消息、任务类型等常量
依赖: enum (Python 标准库)
说明:
  - MESSAGES: 通用消息枚举
  - WEBHOOK_MESSAGES: Webhook通知消息枚举
  - ERROR_MESSAGES: 错误消息枚举（包含用户认证、文件上传、API密钥等错误提示）
  - TASKS: 后台任务类型枚举（标题生成、标签生成、后续问题生成等）
"""

from enum import Enum


class MESSAGES(str, Enum):
    """
    通用消息常量
    用于系统中的通用提示信息
    """
    DEFAULT = lambda msg='': f'{msg if msg else ""}'
    MODEL_ADDED = lambda model='': f"The model '{model}' has been added successfully."
    MODEL_DELETED = lambda model='': f"The model '{model}' has been deleted successfully."


class WEBHOOK_MESSAGES(str, Enum):
    """
    Webhook消息常量
    用于第三方服务通知的消息模板
    """
    DEFAULT = lambda msg='': f'{msg if msg else ""}'
    USER_SIGNUP = lambda username='': f'New user signed up: {username}' if username else 'New user signed up'


class ERROR_MESSAGES(str, Enum):
    """
    错误消息常量
    包含系统运行过程中可能遇到的各种错误提示
    """
    def __str__(self) -> str:
        return super().__str__()

    DEFAULT = lambda err='': f'{"Something went wrong :/" if err == "" else "[ERROR: " + str(err) + "]"}'
    # 环境变量相关错误
    ENV_VAR_NOT_FOUND = 'Required environment variable not found. Terminating now.'
    # 用户相关错误
    CREATE_USER_ERROR = 'Oops! Something went wrong while creating your account. Please try again later. If the issue persists, contact support for assistance.'
    DELETE_USER_ERROR = 'Oops! Something went wrong. We encountered an issue while trying to delete the user. Please give it another shot.'
    EMAIL_MISMATCH = 'Uh-oh! This email does not match the email your provider is registered with. Please check your email and try again.'
    EMAIL_TAKEN = 'Uh-oh! This email is already registered. Sign in with your existing account or choose another email to start anew.'
    USERNAME_TAKEN = 'Uh-oh! This username is already registered. Please choose another username.'
    PASSWORD_TOO_LONG = (
        'Uh-oh! The password you entered is too long. Please make sure your password is less than 72 bytes long.'
    )
    # 资源冲突错误
    COMMAND_TAKEN = 'Uh-oh! This command is already registered. Please choose another command string.'
    FILE_EXISTS = 'Uh-oh! This file is already registered. Please choose another file.'
    ID_TAKEN = 'Uh-oh! This id is already registered. Please choose another id string.'
    MODEL_ID_TAKEN = 'Uh-oh! This model id is already registered. Please choose another model id string.'
    NAME_TAG_TAKEN = 'Uh-oh! This name tag is already registered. Please choose another name tag string.'
    MODEL_ID_TOO_LONG = 'The model id is too long. Please make sure your model id is less than 256 characters long.'
    # 认证相关错误
    INVALID_TOKEN = 'Your session has expired or the token is invalid. Please sign in again.'
    INVALID_CRED = 'The email or password provided is incorrect. Please check for typos and try logging in again.'
    INVALID_EMAIL_FORMAT = "The email format you entered is invalid. Please double-check and make sure you're using a valid email address (e.g., yourname@example.com)."
    INCORRECT_PASSWORD = 'The password provided is incorrect. Please check for typos and try again.'
    INVALID_TRUSTED_HEADER = (
        'Your provider has not provided a trusted header. Please contact your administrator for assistance.'
    )
    EXISTING_USERS = "You can't turn off authentication because there are existing users. If you want to disable WEBUI_AUTH, make sure your web interface doesn't have any existing users and is a fresh installation."
    # 权限相关错误
    UNAUTHORIZED = '401 Unauthorized'
    ACCESS_PROHIBITED = (
        'You do not have permission to access this resource. Please contact your administrator for assistance.'
    )
    ACTION_PROHIBITED = 'The requested action has been restricted as a security measure.'
    # 文件相关错误
    FILE_NOT_SENT = 'FILE_NOT_SENT'
    FILE_NOT_SUPPORTED = "Oops! It seems like the file format you're trying to upload is not supported. Please upload a file with a supported format and try again."
    NOT_FOUND = "We could not find what you're looking for :/"
    USER_NOT_FOUND = "We could not find what you're looking for :/"
    API_KEY_NOT_FOUND = "Oops! It looks like there's a hiccup. The API key is missing. Please make sure to provide a valid API key to access this feature."
    API_KEY_NOT_ALLOWED = 'Use of API key is not enabled in the environment.'
    # 安全相关错误
    MALICIOUS = 'Unusual activities detected, please try again in a few minutes.'
    # 工具/依赖相关错误
    PANDOC_NOT_INSTALLED = 'Pandoc is not installed on the server. Please contact your administrator for assistance.'
    INCORRECT_FORMAT = lambda err='': f'Invalid format. Please use the correct format{err}'
    RATE_LIMIT_EXCEEDED = 'API rate limit exceeded'
    # 模型相关错误
    MODEL_NOT_FOUND = lambda name='': f"Model '{name}' was not found"
    OPENAI_NOT_FOUND = lambda name='': 'OpenAI API was not found'
    OLLAMA_NOT_FOUND = 'WebUI could not connect to Ollama'
    CREATE_API_KEY_ERROR = 'Oops! Something went wrong while creating your API key. Please try again later. If the issue persists, contact support for assistance.'
    API_KEY_CREATION_NOT_ALLOWED = 'API key creation is not allowed in the environment.'
    # 内容相关错误
    EMPTY_CONTENT = 'The content provided is empty. Please ensure that there is text or data is present before proceeding.'
    DB_NOT_SQLITE = 'This feature is only available when running with SQLite databases.'
    INVALID_URL = 'Oops! The URL you provided is invalid. Please double-check and try again.'
    WEB_SEARCH_ERROR = lambda err='': f'{err if err else "Oops! Something went wrong while searching the web."}'
    OLLAMA_API_DISABLED = 'The Ollama API is disabled. Please enable it to use this feature.'
    FILE_TOO_LARGE = lambda size='': (
        f"Oops! The file you're trying to upload is too large. Please upload a file that is less than {size}."
    )
    DUPLICATE_CONTENT = 'Duplicate content detected. Please provide unique content to proceed.'
    FILE_NOT_PROCESSED = (
        'Extracted content is not available for this file. Please ensure that the file is processed before proceeding.'
    )
    INVALID_PASSWORD = lambda err='': err if err else 'The password does not meet the required validation criteria.'
    # 自动化相关错误
    AUTOMATION_LIMIT_EXCEEDED = lambda size='': f'Automation limit reached ({size})'
    AUTOMATION_TOO_FREQUENT = lambda interval='': f'Schedule too frequent. Minimum interval is {interval} seconds.'
    AUTOMATION_INVALID_RRULE = lambda err='': f'Invalid RRULE: {err}'
    AUTOMATION_NO_FUTURE_RUNS = 'RRULE has no future occurrences'
    # 通用功能错误
    FEATURE_DISABLED = lambda name='': f'{name} is disabled'
    INPUT_TOO_LONG = lambda size='': f'Input prompt exceeds maximum length of {size}'
    SERVER_CONNECTION_ERROR = 'Open WebUI: Server Connection Error'
    REQUIRED_FIELD_EMPTY = lambda name='': f'Required field {name} is empty'
    OAUTH_NOT_CONFIGURED = lambda name='': f"Provider '{name}' is not configured"


class TASKS(str, Enum):
    """
    后台任务类型枚举
    用于标识不同的异步处理任务
    """
    def __str__(self) -> str:
        return super().__str__()

    DEFAULT = lambda task='': f'{task if task else "generation"}'
    TITLE_GENERATION = 'title_generation'  # 聊天标题生成任务
    FOLLOW_UP_GENERATION = 'follow_up_generation'  # 后续问题生成任务
    TAGS_GENERATION = 'tags_generation'  # 标签生成任务
    EMOJI_GENERATION = 'emoji_generation'  # 表情符号生成任务
    QUERY_GENERATION = 'query_generation'  # 搜索查询生成任务
    IMAGE_PROMPT_GENERATION = 'image_prompt_generation'  # 图片提示生成任务
    AUTOCOMPLETE_GENERATION = 'autocomplete_generation'  # 自动补全生成任务
    FUNCTION_CALLING = 'function_calling'  # 函数调用任务
    MOA_RESPONSE_GENERATION = 'moa_response_generation'  # 多模型聚合响应生成任务
