"""
工具模块: 日志工具 (Logging Utilities)

功能:
- 配置 Loguru 日志系统
- 格式化日志输出（控制台和文件）
- 拦截标准 logging 模块的日志
- 审计日志支持

依赖:
- loguru
- Python logging 模块
- open_webui.env (配置变量)
"""

import json
import logging
import sys
from typing import TYPE_CHECKING

from loguru import logger

from open_webui.env import (
    ENABLE_AUDIT_STDOUT,
    ENABLE_AUDIT_LOGS_FILE,
    AUDIT_LOGS_FILE_PATH,
    AUDIT_LOG_FILE_ROTATION_SIZE,
    AUDIT_LOG_LEVEL,
    GLOBAL_LOG_LEVEL,
    LOG_FORMAT,
    AUDIT_UVICORN_LOGGER_NAMES,
    ENABLE_OTEL,
    ENABLE_OTEL_LOGS,
    _LEVEL_MAP,
)

if TYPE_CHECKING:
    from loguru import Message, Record


def stdout_format(record: 'Record') -> str:
    """
    生成控制台输出的格式化日志字符串

    格式包括：时间戳、日志级别、源码位置（模块、函数、行号）、
    日志消息和额外数据（序列化为 JSON）。

    参数:
        record (Record): Loguru 记录对象，包含时间、级别、名称、
                        函数、行、消息及任何额外上下文

    返回:
        str: 格式化的日志字符串，用于标准输出
    """
    if record['extra']:
        record['extra']['extra_json'] = json.dumps(record['extra'])
        extra_format = ' - {extra[extra_json]}'
    else:
        extra_format = ''
    return (
        '<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | '
        '<level>{level: <8}</level> | '
        '<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - '
        '<level>{message}</level>' + extra_format + '\n{exception}'
    )


def _json_sink(message: 'Message') -> None:
    """
    将日志记录作为单行 JSON 写入标准输出

    用于 LOG_FORMAT 设置为 "json" 时的 Loguru sink。

    参数:
        message: Loguru 消息对象
    """
    record = message.record
    log_entry = {
        'ts': record['time'].strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
        'level': _LEVEL_MAP.get(record['level'].name, record['level'].name.lower()),
        'msg': record['message'],
        'caller': f'{record["name"]}:{record["function"]}:{record["line"]}',
    }

    if record['extra']:
        log_entry['extra'] = record['extra']

    if record['exception'] is not None:
        log_entry['error'] = ''.join(record['exception'].format_exception()).rstrip()

    sys.stdout.write(json.dumps(log_entry, ensure_ascii=False, default=str) + '\n')
    sys.stdout.flush()


class InterceptHandler(logging.Handler):
    """
    拦截 Python 标准 logging 模块的日志记录

    并将它们重定向到 Loguru 的 logger。
    """

    def emit(self, record):
        """
        由标准 logging 模块每个日志事件调用

        将标准的 LogRecord 转换为与 Loguru 兼容的格式并传递给 Loguru logger。

        参数:
            record: logging 模块的 LogRecord 对象
        """
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).bind(**self._get_extras()).log(level, record.getMessage())
        if ENABLE_OTEL and ENABLE_OTEL_LOGS:
            from open_webui.utils.telemetry.logs import otel_handler

            otel_handler.emit(record)

    def _get_extras(self):
        """获取额外的上下文信息（如 trace_id, span_id）"""
        if not ENABLE_OTEL:
            return {}

        from opentelemetry import trace

        extras = {}
        context = trace.get_current_span().get_span_context()
        if context.is_valid:
            extras['trace_id'] = trace.format_trace_id(context.trace_id)
            extras['span_id'] = trace.format_span_id(context.span_id)
        return extras


def file_format(record: 'Record'):
    """
    将审计日志记录格式化为 JSON 字符串用于文件输出

    参数:
        record: Loguru 记录对象，包含额外的审计数据

    返回:
        str: JSON 格式的审计数据字符串
    """

    audit_data = {
        'id': record['extra'].get('id', ''),
        'timestamp': int(record['time'].timestamp()),
        'user': record['extra'].get('user', dict()),
        'audit_level': record['extra'].get('audit_level', ''),
        'verb': record['extra'].get('verb', ''),
        'request_uri': record['extra'].get('request_uri', ''),
        'response_status_code': record['extra'].get('response_status_code', 0),
        'source_ip': record['extra'].get('source_ip', ''),
        'user_agent': record['extra'].get('user_agent', ''),
        'request_object': record['extra'].get('request_object', b''),
        'response_object': record['extra'].get('response_object', b''),
        'extra': record['extra'].get('extra', {}),
    }

    record['extra']['file_extra'] = json.dumps(audit_data, default=str)
    return '{extra[file_extra]}\n'


def start_logger():
    """
    初始化并配置 Loguru logger

    配置包括：
    - 控制台（stdout）处理器：输出一般日志消息（不包括标记为 auditable 的）
    - 可选的审计日志文件处理器：如果启用了审计日志记录
    - 重新配置 Python 标准 logging 以通过 Loguru 路由
    - 调整 Uvicorn 的日志级别

    参数:
        无（配置来自环境变量）
    """
    logger.remove()

    audit_filter = lambda record: True if ENABLE_AUDIT_STDOUT else 'auditable' not in record['extra']
    if LOG_FORMAT == 'json':
        logger.add(
            _json_sink,
            level=GLOBAL_LOG_LEVEL,
            filter=audit_filter,
        )
    else:
        logger.add(
            sys.stdout,
            level=GLOBAL_LOG_LEVEL,
            format=stdout_format,
            filter=audit_filter,
        )
    if AUDIT_LOG_LEVEL != 'NONE' and ENABLE_AUDIT_LOGS_FILE:
        try:
            logger.add(
                AUDIT_LOGS_FILE_PATH,
                level='INFO',
                rotation=AUDIT_LOG_FILE_ROTATION_SIZE,
                compression='zip',
                format=file_format,
                filter=lambda record: record['extra'].get('auditable') is True,
            )
        except Exception as e:
            logger.error(f'Failed to initialize audit log file handler: {str(e)}')

    logging.basicConfig(handlers=[InterceptHandler()], level=GLOBAL_LOG_LEVEL, force=True)

    for uvicorn_logger_name in ['uvicorn', 'uvicorn.error']:
        uvicorn_logger = logging.getLogger(uvicorn_logger_name)
        uvicorn_logger.setLevel(GLOBAL_LOG_LEVEL)
        uvicorn_logger.handlers = []

    for uvicorn_logger_name in AUDIT_UVICORN_LOGGER_NAMES:
        uvicorn_logger = logging.getLogger(uvicorn_logger_name)
        uvicorn_logger.setLevel(GLOBAL_LOG_LEVEL)
        uvicorn_logger.handlers = [InterceptHandler()]

    logger.info(f'GLOBAL_LOG_LEVEL: {GLOBAL_LOG_LEVEL}')
