"""Small synchronous MCP Streamable HTTP client, JSON and SSE response support."""
import json
import time
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

READ_TOOLS = frozenset({
    'now-time-info', 'query-nearby-stores', 'query-store-coupons',
    'query-my-coupons', 'query-meals', 'query-meal-detail',
    'calculate-price', 'list-nutrition-foods',
})

# Transient by nature: retrying is safe because every tool above is read-only.
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


class MCPError(RuntimeError):
    def __init__(self, message, retryable=False, retry_after=None):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, token, retries=2, backoff=0.5):
        if not token or not token.strip():
            raise MCPError('请先在本地设置 MCD_MCP_TOKEN 环境变量')
        self.token = token.strip()
        self.session = None
        self.counter = 0
        self.version = '2025-03-26'
        self.opener = build_opener(NoRedirect())
        self.retries = max(0, int(retries))
        self.backoff = backoff
        # Observability: how many round trips a single recommendation costs.
        self.calls = 0
        self._tools = None

    def _post(self, method, params=None, notification=False):
        message = {'jsonrpc': '2.0', 'method': method}
        if params is not None:
            message['params'] = params
        if not notification:
            self.counter += 1
            message['id'] = self.counter
        attempt = 0
        while True:
            try:
                return self._send(message, method, notification)
            except MCPError as exc:
                if attempt >= self.retries or not exc.retryable:
                    raise
                delay = min(self.backoff * (2 ** attempt), 4.0)
                if exc.retry_after:
                    delay = min(max(delay, exc.retry_after), 5.0)
                time.sleep(delay)
                attempt += 1

    def _send(self, message, method, notification):
        headers = {'Authorization': 'Bearer ' + self.token,
                   'Content-Type': 'application/json',
                   'Accept': 'application/json, text/event-stream'}
        if self.session:
            headers['Mcp-Session-Id'] = self.session
        if method != 'initialize':
            headers['MCP-Protocol-Version'] = self.version
        request = Request('https://mcp.mcd.cn',
                          data=json.dumps(message).encode(), headers=headers, method='POST')
        self.calls += 1
        try:
            with self.opener.open(request, timeout=30) as response:
                self.session = response.headers.get('Mcp-Session-Id', self.session)
                if notification and response.status in (200, 202, 204):
                    return None
                if 'text/event-stream' in response.headers.get('Content-Type', ''):
                    data = []
                    for raw in response:
                        line = raw.decode('utf-8').rstrip('\r\n')
                        if line.startswith('data:'):
                            data.append(line[5:].lstrip(' '))
                        elif not line and data:
                            event = json.loads('\n'.join(data))
                            data = []
                            if event.get('id') == message.get('id'):
                                return self._result(event)
                    raise MCPError('SSE 连接结束，未收到对应响应')
                event = json.loads(response.read())
                if event.get('id') != message.get('id'):
                    raise MCPError('MCP 响应编号不一致')
                return self._result(event)
        except HTTPError as exc:
            hints = {401: 'Token 无效或已过期', 403: '账号无权访问',
                     429: '服务限流，请稍后重试', 404: '会话或接口已失效'}
            raise MCPError(f'HTTP {exc.code}：{hints.get(exc.code, "MCP 请求失败")}',
                           retryable=exc.code in RETRY_STATUS,
                           retry_after=_retry_after(exc)) from None
        except (URLError, TimeoutError, OSError):
            raise MCPError('MCP 网络连接失败或超时', retryable=True) from None
        except (ValueError, UnicodeError):
            raise MCPError('MCP 响应不是有效 JSON/UTF-8') from None

    @staticmethod
    def _result(event):
        if 'error' in event:
            raise MCPError('MCP 返回协议错误，请核对工具参数和服务状态')
        result = event.get('result', {})
        if result.get('isError'):
            raise MCPError('MCP 工具执行失败，请核对参数；未写入结果文件')
        return result

    def initialize(self):
        result = self._post('initialize', {'protocolVersion': self.version,
            'capabilities': {}, 'clientInfo': {'name': 'mai-habit', 'version': '0.1.0'}})
        if result.get('protocolVersion') not in {'2025-03-26', '2025-06-18', '2025-11-25'}:
            raise MCPError('服务协商了不支持的 MCP 协议版本')
        self.version = result['protocolVersion']
        self._post('notifications/initialized', notification=True)

    def tools(self, refresh=False):
        """Cached tool catalog.

        Re-fetching tools/list before every tools/call used to double the round
        trips of one recommendation plan (up to 40 extra requests for 40
        candidates). The catalog is stable for a session, so fetch it once and
        pass refresh=True only after a schema error.
        """
        if self._tools is None or refresh:
            self._tools = self._fetch_tools()
        return list(self._tools)

    def warm(self):
        """Pay for the tool catalog once, up front, on a predictable path."""
        return self.tools()

    def _fetch_tools(self):
        tools, cursor, seen = [], None, set()
        for _ in range(100):
            result = self._post('tools/list', {'cursor': cursor} if cursor else {})
            tools.extend(t for t in result.get('tools', [])
                         if t.get('name') in READ_TOOLS)
            cursor = result.get('nextCursor')
            if not cursor:
                return tools
            if cursor in seen:
                raise MCPError('工具列表分页游标重复')
            seen.add(cursor)
        raise MCPError('工具列表分页超过上限')

    def call(self, name, arguments):
        if name not in READ_TOOLS:
            raise MCPError('该工具不在本项目查询和试算范围内')
        if not isinstance(arguments, dict):
            raise MCPError('工具参数必须是 JSON 对象')
        # Discover real inputSchema instead of assuming undocumented parameters.
        schema = next((t for t in self.tools() if t.get('name') == name), None)
        if schema is None:
            raise MCPError('当前服务未提供此工具')
        required = schema.get('inputSchema', {}).get('required', [])
        if any(key not in arguments for key in required):
            raise MCPError('缺少必填参数，请先运行 mcp-tools 查看 inputSchema')
        return self._post('tools/call', {'name': name, 'arguments': arguments})


def _retry_after(error):
    """Read Retry-After (seconds form only) without trusting its content."""
    try:
        value = str(error.headers.get('Retry-After', '') or '').strip()
    except (AttributeError, TypeError):
        return None
    return float(value) if value.isdigit() else None
