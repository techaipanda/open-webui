"""
网络搜索工具函数模块
功能: 提供 URL 验证、SSL 验证、安全加载器等网络抓取辅助函数

核心功能:
- URL 验证: 检查 URL 格式和安全性，防止 SSRF 攻击
- SSL 证书验证: 确保 HTTPS 连接的安全
- 安全加载器: 封装多种网页抓取引擎（Playwright, Firecrawl, Tavily 等）
- 速率限制: 防止请求过快被封禁
- 代理支持: 支持环境变量和手动配置的代理

安全特性:
- 私有 IP 地址过滤: 阻止访问内网地址
- DNS 重绑定防护: 验证解析后的 IP 地址
- 重定向验证: 防止通过重定向绕过安全检查
- 域名/IP 黑名单: 支持基于过滤列表的访问控制

依赖:
- playwright: 浏览器自动化抓取
- aiohttp: 异步 HTTP 客户端
- validators: URL 格式验证
"""

import asyncio
import ipaddress
import logging
import socket
import ssl
import urllib.parse
import urllib.request

import requests
from datetime import datetime, time, timedelta
from typing import (
    Any,
    AsyncIterator,
    Dict,
    Iterator,
    List,
    Optional,
    Sequence,
    Union,
    Literal,
)

from fastapi.concurrency import run_in_threadpool
import aiohttp
import certifi
import validators
from langchain_community.document_loaders import PlaywrightURLLoader, WebBaseLoader
from langchain_community.document_loaders.base import BaseLoader
from langchain_core.documents import Document

from open_webui.retrieval.loaders.tavily import TavilyLoader
from open_webui.retrieval.loaders.external_web import ExternalWebLoader
from open_webui.retrieval.web.firecrawl import scrape_firecrawl_url
from open_webui.constants import ERROR_MESSAGES
from open_webui.config import (
    ENABLE_RAG_LOCAL_WEB_FETCH,
    PLAYWRIGHT_WS_URL,
    PLAYWRIGHT_TIMEOUT,
    WEB_LOADER_ENGINE,
    WEB_LOADER_TIMEOUT,
    FIRECRAWL_API_BASE_URL,
    FIRECRAWL_API_KEY,
    FIRECRAWL_TIMEOUT,
    TAVILY_API_KEY,
    TAVILY_EXTRACT_DEPTH,
    EXTERNAL_WEB_LOADER_URL,
    EXTERNAL_WEB_LOADER_API_KEY,
    WEB_FETCH_FILTER_LIST,
)
from open_webui.utils.misc import is_string_allowed
from open_webui.env import AIOHTTP_CLIENT_SESSION_SSL, AIOHTTP_CLIENT_ALLOW_REDIRECTS

log = logging.getLogger(__name__)


def resolve_hostname(hostname):
    """
    解析主机名到 IP 地址

    获取给定主机名的所有 IPv4 和 IPv6 地址，用于:
    - 验证 URL 是否指向内网地址
    - 防止 DNS 重绑定攻击

    Args:
        hostname: 主机名（如 example.com）

    Returns:
        tuple: (ipv4_addresses, ipv6_addresses) 两个列表的元组
    """
    # Get address information
    addr_info = socket.getaddrinfo(hostname, None)

    # Extract IP addresses from address information
    ipv4_addresses = [info[4][0] for info in addr_info if info[0] == socket.AF_INET]
    ipv6_addresses = [info[4][0] for info in addr_info if info[0] == socket.AF_INET6]

    return ipv4_addresses, ipv6_addresses


def validate_url(url: Union[str, Sequence[str]]):
    """
    验证 URL 的安全性和有效性

    安全检查包括:
    1. URL 格式验证（使用 validators 库）
    2. 协议检查（仅允许 http/https）
    3. 解析器混淆字符检查（防止 URL 解析不一致）
    4. 过滤列表检查（基于域名/IP）
    5. 内网地址检查（防止 SSRF）

    Args:
        url: 单个 URL 字符串或 URL 序列

    Returns:
        bool: 验证通过返回 True

    Raises:
        ValueError: URL 无效或被安全策略阻止
    """
    if isinstance(url, str):
        if isinstance(validators.url(url), validators.ValidationError):
            raise ValueError(ERROR_MESSAGES.INVALID_URL)

        # Reject parser-confusing chars: urlparse and requests/aiohttp split
        # on these differently, e.g. http://127.0.0.1\@1.1.1.1 → urlparse
        # extracts 1.1.1.1 (public, passes filter) while requests connects
        # to 127.0.0.1 (internal). Same shape with tab/CR/LF.
        if any(ch in url for ch in ('\\', '\t', '\n', '\r')):
            log.warning(f'Blocked URL with parser-confusing char: {url!r}')
            raise ValueError(ERROR_MESSAGES.INVALID_URL)

        parsed_url = urllib.parse.urlparse(url)

        # Protocol validation - only allow http/https
        if parsed_url.scheme not in ['http', 'https']:
            log.warning(f'Blocked non-HTTP(S) protocol: {parsed_url.scheme} in URL: {url}')
            raise ValueError(ERROR_MESSAGES.INVALID_URL)

        # Blocklist check using unified filtering logic
        if WEB_FETCH_FILTER_LIST:
            if not is_string_allowed(url, WEB_FETCH_FILTER_LIST):
                log.warning(f'URL blocked by filter list: {url}')
                raise ValueError(ERROR_MESSAGES.INVALID_URL)

        if not ENABLE_RAG_LOCAL_WEB_FETCH:
            # Local web fetch is disabled, filter out any URLs that resolve to private IP addresses
            parsed_url = urllib.parse.urlparse(url)
            # Get IPv4 and IPv6 addresses
            ipv4_addresses, ipv6_addresses = resolve_hostname(parsed_url.hostname)
            # Check if any of the resolved addresses are private
            # This is technically still vulnerable to DNS rebinding attacks, as we don't control WebBaseLoader
            for ip in ipv4_addresses + ipv6_addresses:
                addr = ipaddress.ip_address(ip)
                if not addr.is_global:
                    raise ValueError(ERROR_MESSAGES.INVALID_URL)
        return True
    elif isinstance(url, Sequence):
        return all(validate_url(u) for u in url)
    else:
        return False


def safe_validate_urls(url: Sequence[str]) -> Sequence[str]:
    """
    安全地验证多个 URL

    过滤掉无效或不安全的 URL，保留通过验证的 URL

    Args:
        url: URL 序列

    Returns:
        通过验证的 URL 列表
    """
    valid_urls = []
    for u in url:
        try:
            if validate_url(u):
                valid_urls.append(u)
        except Exception as e:
            log.debug(f'Invalid URL {u}: {str(e)}')
            continue
    return valid_urls


def extract_metadata(soup, url):
    """
    从 BeautifulSoup 解析的 HTML 中提取元数据

    Args:
        soup: BeautifulSoup 解析对象
        url: 原始 URL（作为 source 字段）

    Returns:
        dict: 包含 source, title, description, language 的元数据字典
    """
    metadata = {'source': url}
    if title := soup.find('title'):
        metadata['title'] = title.get_text()
    if description := soup.find('meta', attrs={'name': 'description'}):
        metadata['description'] = description.get('content', 'No description found.')
    if html := soup.find('html'):
        metadata['language'] = html.get('lang', 'No language found.')
    return metadata


def verify_ssl_cert(url: str) -> bool:
    """
    验证 URL 的 SSL 证书

    Args:
        url: 要验证的 URL（必须是 https:// 开头）

    Returns:
        bool: 证书有效返回 True，无效或非 HTTPS 返回 False
    """
    """Verify SSL certificate for the given URL."""
    if not url.startswith('https://'):
        return True

    try:
        hostname = url.split('://')[-1].split('/')[0]
        context = ssl.create_default_context(cafile=certifi.where())
        with context.wrap_socket(ssl.socket(), server_hostname=hostname) as s:
            s.connect((hostname, 443))
        return True
    except ssl.SSLError:
        return False
    except Exception as e:
        log.warning(f'SSL verification failed for {url}: {str(e)}')
        return False


class RateLimitMixin:
    """
    速率限制混入类

    提供请求速率控制，防止超过 API 限制
    """

    async def _wait_for_rate_limit(self):
        """
        异步等待以遵守速率限制

        根据 requests_per_second 配置等待适当的时间
        """
        """Wait to respect the rate limit if specified."""
        if self.requests_per_second and self.last_request_time:
            min_interval = timedelta(seconds=1.0 / self.requests_per_second)
            time_since_last = datetime.now() - self.last_request_time
            if time_since_last < min_interval:
                await asyncio.sleep((min_interval - time_since_last).total_seconds())
        self.last_request_time = datetime.now()

    def _sync_wait_for_rate_limit(self):
        """
        同步速率限制等待

        用于不支持异步的上下文
        """
        """Synchronous version of rate limit wait."""
        if self.requests_per_second and self.last_request_time:
            min_interval = timedelta(seconds=1.0 / self.requests_per_second)
            time_since_last = datetime.now() - self.last_request_time
            if time_since_last < min_interval:
                time.sleep((min_interval - time_since_last).total_seconds())
        self.last_request_time = datetime.now()


class URLProcessingMixin:
    """
    URL 处理混入类

    提供 SSL 验证和速率限制的异步/同步支持
    """

    async def _verify_ssl_cert(self, url: str) -> bool:
        """
        异步验证 URL 的 SSL 证书

        Args:
            url: 要验证的 URL

        Returns:
            bool: 证书有效返回 True
        """
        """Verify SSL certificate for a URL."""
        return await run_in_threadpool(verify_ssl_cert, url)

    async def _safe_process_url(self, url: str) -> bool:
        """
        异步执行 URL 安全检查

        包括 SSL 验证和速率限制

        Args:
            url: 要处理的 URL

        Returns:
            bool: 检查通过返回 True

        Raises:
            ValueError: SSL 验证失败
        """
        """Perform safety checks before processing a URL."""
        if self.verify_ssl and not await self._verify_ssl_cert(url):
            raise ValueError(f'SSL certificate verification failed for {url}')
        await self._wait_for_rate_limit()
        return True

    def _safe_process_url_sync(self, url: str) -> bool:
        """
        同步执行 URL 安全检查

        Args:
            url: 要处理的 URL

        Returns:
            bool: 检查通过返回 True

        Raises:
            ValueError: SSL 验证失败
        """
        """Synchronous version of safety checks."""
        if self.verify_ssl and not verify_ssl_cert(url):
            raise ValueError(f'SSL certificate verification failed for {url}')
        self._sync_wait_for_rate_limit()
        return True


class SafeFireCrawlLoader(BaseLoader, RateLimitMixin, URLProcessingMixin):
    """
    Firecrawl 安全加载器

    使用 Firecrawl API 进行网页抓取，支持:
    - 速率限制
    - SSL 证书验证
    - 代理配置
    - 多种抓取模式（crawl/scrape/map）

    Attributes:
        web_paths: 要抓取的 URL 列表
        verify_ssl: 是否验证 SSL 证书
        requests_per_second: 每秒请求数限制
    """

    def __init__(
        self,
        web_paths,
        verify_ssl: bool = True,
        trust_env: bool = False,
        requests_per_second: Optional[float] = None,
        continue_on_failure: bool = True,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        timeout: Optional[int] = None,
        mode: Literal['crawl', 'scrape', 'map'] = 'scrape',
        proxy: Optional[Dict[str, str]] = None,
        params: Optional[Dict] = None,
    ):
        """
        初始化 Firecrawl 安全加载器

        Args:
            web_paths: URL 路径列表
            verify_ssl: 是否验证 SSL
            trust_env: 是否使用环境变量代理
            requests_per_second: 速率限制
            continue_on_failure: 失败是否继续
            api_key: Firecrawl API 密钥
            api_url: Firecrawl API 基础 URL
            timeout: 请求超时时间
            mode: 抓取模式
            proxy: 代理配置
            params: 额外参数
        """
        proxy_server = proxy.get('server') if proxy else None
        if trust_env and not proxy_server:
            env_proxies = urllib.request.getproxies()
            env_proxy_server = env_proxies.get('https') or env_proxies.get('http')
            if env_proxy_server:
                if proxy:
                    proxy['server'] = env_proxy_server
                else:
                    proxy = {'server': env_proxy_server}
        self.web_paths = web_paths
        self.verify_ssl = verify_ssl
        self.requests_per_second = requests_per_second
        self.last_request_time = None
        self.trust_env = trust_env
        self.continue_on_failure = continue_on_failure
        self.api_key = api_key
        self.api_url = (api_url or 'https://api.firecrawl.dev').rstrip('/')
        self.timeout = timeout
        self.mode = mode
        self.params = params or {}

    def lazy_load(self) -> Iterator[Document]:
        """
        同步懒加载文档

        Yields:
            Document: 抓取到的文档
        """
        try:
            for url in self.web_paths:
                doc = scrape_firecrawl_url(
                    self.api_url,
                    self.api_key,
                    url,
                    verify_ssl=self.verify_ssl,
                    timeout=self.timeout,
                    params=self.params,
                )
                if doc is not None:
                    yield doc
        except Exception as e:
            if self.continue_on_failure:
                log.warning(f'Error extracting content from URLs with Firecrawl: {e}')
            else:
                raise e

    async def alazy_load(self):
        """
        异步懒加载文档

        Yields:
            Document: 抓取到的文档
        """
        try:
            docs = await run_in_threadpool(lambda: list(self.lazy_load()))
            for doc in docs:
                yield doc
        except Exception as e:
            if self.continue_on_failure:
                log.warning(f'Error extracting content from URLs with Firecrawl: {e}')
            else:
                raise e


class SafeTavilyLoader(BaseLoader, RateLimitMixin, URLProcessingMixin):
    """
    Tavily 安全加载器

    使用 Tavily API 进行网页抓取，支持:
    - 基础和高级提取模式
    - 速率限制
    - SSL 验证

    Attributes:
        web_paths: URL 列表
        api_key: Tavily API 密钥
        extract_depth: 提取深度（basic/advanced）
    """

    def __init__(
        self,
        web_paths: Union[str, List[str]],
        api_key: str,
        extract_depth: Literal['basic', 'advanced'] = 'basic',
        continue_on_failure: bool = True,
        requests_per_second: Optional[float] = None,
        verify_ssl: bool = True,
        trust_env: bool = False,
        proxy: Optional[Dict[str, str]] = None,
    ):
        """
        初始化 Tavily 安全加载器

        Args:
            web_paths: URL 或 URL 列表
            api_key: Tavily API 密钥
            extract_depth: 提取深度
            continue_on_failure: 失败是否继续
            requests_per_second: 速率限制
            verify_ssl: 是否验证 SSL
            trust_env: 是否使用环境变量代理
            proxy: 代理配置
        """
        # Initialize proxy configuration if using environment variables
        proxy_server = proxy.get('server') if proxy else None
        if trust_env and not proxy_server:
            env_proxies = urllib.request.getproxies()
            env_proxy_server = env_proxies.get('https') or env_proxies.get('http')
            if env_proxy_server:
                if proxy:
                    proxy['server'] = env_proxy_server
                else:
                    proxy = {'server': env_proxy_server}

        # Store parameters for creating TavilyLoader instances
        self.web_paths = web_paths if isinstance(web_paths, list) else [web_paths]
        self.api_key = api_key
        self.extract_depth = extract_depth
        self.continue_on_failure = continue_on_failure
        self.verify_ssl = verify_ssl
        self.trust_env = trust_env
        self.proxy = proxy

        # Add rate limiting
        self.requests_per_second = requests_per_second
        self.last_request_time = None

    def lazy_load(self) -> Iterator[Document]:
        """
        同步懒加载文档

        Yields:
            Document: 抓取到的文档
        """
        """Load documents with rate limiting support, delegating to TavilyLoader."""
        valid_urls = []
        for url in self.web_paths:
            try:
                self._safe_process_url_sync(url)
                valid_urls.append(url)
            except Exception as e:
                log.warning(f'SSL verification failed for {url}: {str(e)}')
                if not self.continue_on_failure:
                    raise e
        if not valid_urls:
            if self.continue_on_failure:
                log.warning('No valid URLs to process after SSL verification')
                return
            raise ValueError('No valid URLs to process after SSL verification')
        try:
            loader = TavilyLoader(
                urls=valid_urls,
                api_key=self.api_key,
                extract_depth=self.extract_depth,
                continue_on_failure=self.continue_on_failure,
            )
            yield from loader.lazy_load()
        except Exception as e:
            if self.continue_on_failure:
                log.exception(f'Error extracting content from URLs: {e}')
            else:
                raise e

    async def alazy_load(self) -> AsyncIterator[Document]:
        """
        异步懒加载文档

        Yields:
            Document: 抓取到的文档
        """
        """Async version with rate limiting and SSL verification."""
        valid_urls = []
        for url in self.web_paths:
            try:
                await self._safe_process_url(url)
                valid_urls.append(url)
            except Exception as e:
                log.warning(f'SSL verification failed for {url}: {str(e)}')
                if not self.continue_on_failure:
                    raise e

        if not valid_urls:
            if self.continue_on_failure:
                log.warning('No valid URLs to process after SSL verification')
                return
            raise ValueError('No valid URLs to process after SSL verification')

        try:
            loader = TavilyLoader(
                urls=valid_urls,
                api_key=self.api_key,
                extract_depth=self.extract_depth,
                continue_on_failure=self.continue_on_failure,
            )
            async for document in loader.alazy_load():
                yield document
        except Exception as e:
            if self.continue_on_failure:
                log.exception(f'Error loading URLs: {e}')
            else:
                raise e


class SafePlaywrightURLLoader(PlaywrightURLLoader, RateLimitMixin, URLProcessingMixin):
    """
    Playwright 安全加载器

    使用 Playwright 浏览器自动化抓取网页，支持:
    - 远程浏览器连接（WebSocket）
    - SSL 证书验证
    - 速率限制
    - 代理配置

    Attributes:
        web_paths: URL 列表
        verify_ssl: 是否验证 SSL
        requests_per_second: 每秒请求数限制
        playwright_ws_url: 远程浏览器 WebSocket URL
    """

    def __init__(
        self,
        web_paths: List[str],
        verify_ssl: bool = True,
        trust_env: bool = False,
        requests_per_second: Optional[float] = None,
        continue_on_failure: bool = True,
        headless: bool = True,
        remove_selectors: Optional[List[str]] = None,
        proxy: Optional[Dict[str, str]] = None,
        playwright_ws_url: Optional[str] = None,
        playwright_timeout: Optional[int] = 10000,
    ):
        """
        初始化 Playwright 安全加载器

        Args:
            web_paths: URL 列表
            verify_ssl: 是否验证 SSL
            trust_env: 是否使用环境变量代理
            requests_per_second: 速率限制
            continue_on_failure: 失败是否继续
            headless: 是否无头模式
            remove_selectors: 要移除的 CSS 选择器
            proxy: 代理配置
            playwright_ws_url: 远程浏览器 WebSocket URL
            playwright_timeout: 操作超时时间
        """
        """Initialize with additional safety parameters and remote browser support."""

        proxy_server = proxy.get('server') if proxy else None
        if trust_env and not proxy_server:
            env_proxies = urllib.request.getproxies()
            env_proxy_server = env_proxies.get('https') or env_proxies.get('http')
            if env_proxy_server:
                if proxy:
                    proxy['server'] = env_proxy_server
                else:
                    proxy = {'server': env_proxy_server}

        # We'll set headless to False if using playwright_ws_url since it's handled by the remote browser
        super().__init__(
            urls=web_paths,
            continue_on_failure=continue_on_failure,
            headless=headless if playwright_ws_url is None else False,
            remove_selectors=remove_selectors,
            proxy=proxy,
        )
        self.verify_ssl = verify_ssl
        self.requests_per_second = requests_per_second
        self.last_request_time = None
        self.playwright_ws_url = playwright_ws_url
        self.trust_env = trust_env
        self.playwright_timeout = playwright_timeout

    def lazy_load(self) -> Iterator[Document]:
        """
        同步懒加载文档

        Yields:
            Document: 抓取到的文档
        """
        """Safely load URLs synchronously with support for remote browser."""
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            # Use remote browser if ws_endpoint is provided, otherwise use local browser
            if self.playwright_ws_url:
                browser = p.chromium.connect(self.playwright_ws_url)
            else:
                browser = p.chromium.launch(headless=self.headless, proxy=self.proxy)

            for url in self.urls:
                try:
                    self._safe_process_url_sync(url)
                    page = browser.new_page()
                    response = page.goto(url, timeout=self.playwright_timeout)
                    if response is None:
                        raise ValueError(f'page.goto() returned None for url {url}')

                    text = self.evaluator.evaluate(page, browser, response)
                    metadata = {'source': url}
                    yield Document(page_content=text, metadata=metadata)
                except Exception as e:
                    if self.continue_on_failure:
                        log.exception(f'Error loading {url}: {e}')
                        continue
                    raise e
            browser.close()

    async def alazy_load(self) -> AsyncIterator[Document]:
        """
        异步懒加载文档

        Yields:
            Document: 抓取到的文档
        """
        """Safely load URLs asynchronously with support for remote browser."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            # Use remote browser if ws_endpoint is provided, otherwise use local browser
            if self.playwright_ws_url:
                browser = await p.chromium.connect(self.playwright_ws_url)
            else:
                browser = await p.chromium.launch(headless=self.headless, proxy=self.proxy)

            for url in self.urls:
                try:
                    await self._safe_process_url(url)
                    page = await browser.new_page()
                    response = await page.goto(url, timeout=self.playwright_timeout)
                    if response is None:
                        raise ValueError(f'page.goto() returned None for url {url}')

                    text = await self.evaluator.evaluate_async(page, browser, response)
                    metadata = {'source': url}
                    yield Document(page_content=text, metadata=metadata)
                except Exception as e:
                    if self.continue_on_failure:
                        log.exception(f'Error loading {url}: {e}')
                        continue
                    raise e
            await browser.close()


class SafeWebBaseLoader(WebBaseLoader):
    """
    安全 WebBase 加载器

    增强的 WebBaseLoader，包含:
    - 重定向安全检查（防止 SSRF）
    - 异步支持
    - 元数据提取

    Attributes:
        trust_env: 是否使用环境变量代理
    """

    def __init__(self, trust_env: bool = False, *args, **kwargs):
        """
        初始化安全 WebBase 加载器

        Args:
            trust_env: 是否使用代理环境变量
        """
        """Initialize SafeWebBaseLoader
        Args:
            trust_env (bool, optional): set to True if using proxy to make web requests, for example
                using http(s)_proxy environment variables. Defaults to False.
        """
        super().__init__(*args, **kwargs)
        self.trust_env = trust_env
        # Prevent redirect-based SSRF on the synchronous _scrape() path.
        # validate_url() is called once on the originally-submitted URL, but the
        # parent WebBaseLoader's _scrape() invokes self.session.get(url, **self.requests_kwargs)
        # which by default follows redirects. Without the override below, an attacker
        # can submit a public URL that 302-redirects to an internal address (RFC1918,
        # 127.0.0.1, 169.254.169.254, etc.) and the redirected target is fetched without
        # re-validation. Matches the policy enforced on the async _fetch() path below.
        self.requests_kwargs = {
            **(self.requests_kwargs or {}),
            'allow_redirects': AIOHTTP_CLIENT_ALLOW_REDIRECTS,
        }

    async def _fetch(self, url: str, retries: int = 3, cooldown: int = 2, backoff: float = 1.5) -> str:
        """
        异步获取 URL 内容（带重试）

        Args:
            url: 要抓取的 URL
            retries: 重试次数
            cooldown: 冷却时间（秒）
            backoff: 退避系数

        Returns:
            str: 页面 HTML 内容

        Raises:
            ValueError: 重试次数超限
        """
        async with aiohttp.ClientSession(trust_env=self.trust_env) as session:
            for i in range(retries):
                try:
                    kwargs: Dict = dict(
                        headers=self.session.headers,
                        cookies=self.session.cookies.get_dict(),
                    )
                    if not self.session.verify:
                        kwargs['ssl'] = False
                    else:
                        kwargs['ssl'] = AIOHTTP_CLIENT_SESSION_SSL

                    async with session.get(
                        url,
                        **(self.requests_kwargs | kwargs),
                        allow_redirects=AIOHTTP_CLIENT_ALLOW_REDIRECTS,
                    ) as response:
                        if self.raise_for_status:
                            response.raise_for_status()
                        return await response.text()
                except aiohttp.ClientConnectionError as e:
                    if i == retries - 1:
                        raise
                    else:
                        log.warning(f'Error fetching {url} with attempt {i + 1}/{retries}: {e}. Retrying...')
                        await asyncio.sleep(cooldown * backoff**i)
        raise ValueError('retry count exceeded')

    def _unpack_fetch_results(self, results: Any, urls: List[str], parser: Union[str, None] = None) -> List[Any]:
        """
        将抓取结果解析为 BeautifulSoup 对象

        Args:
            results: 原始 HTML 字符串列表
            urls: URL 列表
            parser: BeautifulSoup 解析器（可选）

        Returns:
            List[BeautifulSoup]: 解析后的 soup 对象列表
        """
        """Unpack fetch results into BeautifulSoup objects."""
        from bs4 import BeautifulSoup

        final_results = []
        for i, result in enumerate(results):
            url = urls[i]
            if parser is None:
                if url.endswith('.xml'):
                    parser = 'xml'
                else:
                    parser = self.default_parser
                self._check_parser(parser)
            final_results.append(BeautifulSoup(result, parser, **self.bs_kwargs))
        return final_results

    async def ascrape_all(self, urls: List[str], parser: Union[str, None] = None) -> List[Any]:
        """
        异步抓取所有 URL

        Args:
            urls: URL 列表
            parser: BeautifulSoup 解析器（可选）

        Returns:
            List[BeautifulSoup]: 解析后的 soup 对象列表
        """
        """Async fetch all urls, then return soups for all results."""
        results = await self.fetch_all(urls)
        return self._unpack_fetch_results(results, urls, parser=parser)

    def lazy_load(self) -> Iterator[Document]:
        """
        同步懒加载文档

        Yields:
            Document: 抓取到的文档
        """
        """Lazy load text from the url(s) in web_path with error handling."""
        for path in self.web_paths:
            try:
                soup = self._scrape(path, bs_kwargs=self.bs_kwargs)
                text = soup.get_text(**self.bs_get_text_kwargs)

                # Build metadata
                metadata = extract_metadata(soup, path)

                yield Document(page_content=text, metadata=metadata)
            except Exception as e:
                # Log the error and continue with the next URL
                log.exception(f'Error loading {path}: {e}')

    async def alazy_load(self) -> AsyncIterator[Document]:
        """
        异步懒加载文档

        Yields:
            Document: 抓取到的文档
        """
        """Async lazy load text from the url(s) in web_path."""
        results = await self.ascrape_all(self.web_paths)
        for path, soup in zip(self.web_paths, results):
            text = soup.get_text(**self.bs_get_text_kwargs)
            metadata = {'source': path}
            if title := soup.find('title'):
                metadata['title'] = title.get_text()
            if description := soup.find('meta', attrs={'name': 'description'}):
                metadata['description'] = description.get('content', 'No description found.')
            if html := soup.find('html'):
                metadata['language'] = html.get('lang', 'No language found.')
            yield Document(page_content=text, metadata=metadata)

    async def aload(self) -> list[Document]:
        """
        加载所有文档到列表

        Returns:
            List[Document]: 文档列表
        """
        """Load data into Document objects."""
        return [document async for document in self.alazy_load()]


def get_web_loader(
    urls: Union[str, Sequence[str]],
    verify_ssl: bool = True,
    requests_per_second: int = 2,
    trust_env: bool = False,
):
    """
    获取适合的网页加载器

    根据配置选择合适的加载器引擎（safe_web/playwright/firecrawl/tavily/external）

    Args:
        urls: 单个 URL 或 URL 序列
        verify_ssl: 是否验证 SSL
        requests_per_second: 速率限制
        trust_env: 是否使用环境变量代理

    Returns:
        BaseLoader: 配置好的加载器实例

    Raises:
        ValueError: URL 无效或引擎不支持
    """
    # Check if the URLs are valid
    safe_urls = safe_validate_urls([urls] if isinstance(urls, str) else urls)

    if not safe_urls:
        log.warning(f'All provided URLs were blocked or invalid: {urls}')
        raise ValueError(ERROR_MESSAGES.INVALID_URL)

    web_loader_args = {
        'web_paths': safe_urls,
        'verify_ssl': verify_ssl,
        'requests_per_second': requests_per_second,
        'continue_on_failure': True,
        'trust_env': trust_env,
    }

    if WEB_LOADER_ENGINE.value == '' or WEB_LOADER_ENGINE.value == 'safe_web':
        WebLoaderClass = SafeWebBaseLoader

        request_kwargs = {}
        if WEB_LOADER_TIMEOUT.value:
            try:
                timeout_value = float(WEB_LOADER_TIMEOUT.value)
            except ValueError:
                timeout_value = None

            if timeout_value:
                request_kwargs['timeout'] = timeout_value

        if request_kwargs:
            web_loader_args['requests_kwargs'] = request_kwargs

    if WEB_LOADER_ENGINE.value == 'playwright':
        WebLoaderClass = SafePlaywrightURLLoader
        web_loader_args['playwright_timeout'] = PLAYWRIGHT_TIMEOUT.value
        if PLAYWRIGHT_WS_URL.value:
            web_loader_args['playwright_ws_url'] = PLAYWRIGHT_WS_URL.value

    if WEB_LOADER_ENGINE.value == 'firecrawl':
        WebLoaderClass = SafeFireCrawlLoader
        web_loader_args['api_key'] = FIRECRAWL_API_KEY.value
        web_loader_args['api_url'] = FIRECRAWL_API_BASE_URL.value
        if FIRECRAWL_TIMEOUT.value:
            try:
                web_loader_args['timeout'] = int(FIRECRAWL_TIMEOUT.value)
            except ValueError:
                pass

    if WEB_LOADER_ENGINE.value == 'tavily':
        WebLoaderClass = SafeTavilyLoader
        web_loader_args['api_key'] = TAVILY_API_KEY.value
        web_loader_args['extract_depth'] = TAVILY_EXTRACT_DEPTH.value

    if WEB_LOADER_ENGINE.value == 'external':
        WebLoaderClass = ExternalWebLoader
        web_loader_args['external_url'] = EXTERNAL_WEB_LOADER_URL.value
        web_loader_args['external_api_key'] = EXTERNAL_WEB_LOADER_API_KEY.value

    if WebLoaderClass:
        web_loader = WebLoaderClass(**web_loader_args)

        log.debug(
            'Using WEB_LOADER_ENGINE %s for %s URLs',
            web_loader.__class__.__name__,
            len(safe_urls),
        )

        return web_loader
    else:
        raise ValueError(
            f'Invalid WEB_LOADER_ENGINE: {WEB_LOADER_ENGINE.value}. '
            "Please set it to 'safe_web', 'playwright', 'firecrawl', or 'tavily'."
        )