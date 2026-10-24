from io import BytesIO
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/mai-habit/scripts'))
from mcp_client import Client, MCPError


class Response(BytesIO):
    def __init__(self, body=b'', headers=None, status=200):
        super().__init__(body)
        self.headers = headers or {'Content-Type': 'application/json'}
        self.status = status


def rpc(cid, result):
    return Response(json.dumps({'jsonrpc': '2.0', 'id': cid, 'result': result}).encode())


class MCPTests(unittest.TestCase):
    def test_handshake_and_session_forwarded(self):
        client = Client('FAKE-TEST-TOKEN')
        first = rpc(1, {'protocolVersion': '2025-03-26'})
        first.headers['Mcp-Session-Id'] = 'test-session'
        opener = Mock()
        opener.open.side_effect = [first, Response(status=202), rpc(2, {'tools': []})]
        client.opener = opener
        client.initialize()
        self.assertEqual([], client.tools())
        requests = [call.args[0] for call in opener.open.call_args_list]
        self.assertEqual('notifications/initialized', json.loads(requests[1].data)['method'])
        self.assertEqual('test-session', requests[2].get_header('Mcp-session-id'))
        self.assertEqual('2025-03-26', requests[2].get_header('Mcp-protocol-version'))

    def test_sse_skips_notification_and_reads_matching_response(self):
        client = Client('FAKE-TEST-TOKEN')
        client.opener = Mock()
        body = b': keepalive\n\ndata: {"jsonrpc":"2.0","method":"notifications/message"}\n\nevent: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"tools":[]}}\n\n'
        client.opener.open.return_value = Response(body, {'Content-Type': 'text/event-stream'})
        self.assertEqual([], client.tools())

    def test_pagination_and_write_tools_hidden(self):
        client = Client('FAKE-TEST-TOKEN')
        client.opener = Mock()
        client.opener.open.side_effect = [
            rpc(1, {'tools': [{'name': 'create-order'}, {'name': 'query-meals'}], 'nextCursor': 'page2'}),
            rpc(2, {'tools': [{'name': 'calculate-price'}]})]
        self.assertEqual(['query-meals', 'calculate-price'], [t['name'] for t in client.tools()])
        with self.assertRaises(MCPError):
            client.call('create-order', {})
        self.assertEqual(2, client.opener.open.call_count)

    def test_tool_arguments_follow_discovered_schema(self):
        client = Client('FAKE-TEST-TOKEN')
        client.opener = Mock()
        client.opener.open.return_value = rpc(1, {'tools': [{'name': 'query-meals', 'inputSchema': {'required': ['actualStoreField']}}]})
        with self.assertRaises(MCPError):
            client.call('query-meals', {})
        self.assertEqual(1, client.opener.open.call_count)

    def test_tool_call_receives_result(self):
        client = Client('FAKE-TEST-TOKEN')
        client.opener = Mock()
        client.opener.open.side_effect = [
            rpc(1, {'tools': [{'name': 'query-meals', 'inputSchema': {'required': ['store']}}]}),
            rpc(2, {'content': [{'type': 'text', 'text': 'MOCK MENU'}]})]
        result = client.call('query-meals', {'store': 'MOCK'})
        self.assertEqual('MOCK MENU', result['content'][0]['text'])
        request = client.opener.open.call_args_list[-1].args[0]
        self.assertEqual({'name': 'query-meals', 'arguments': {'store': 'MOCK'}}, json.loads(request.data)['params'])

    def test_http_error_does_not_echo_token_or_server_body(self):
        client = Client('FAKE-TEST-TOKEN')
        client.opener = Mock()
        client.opener.open.side_effect = HTTPError('https://mcp.mcd.cn', 401, 'FAKE-TEST-TOKEN', {}, None)
        with self.assertRaises(MCPError) as error:
            client.tools()
        self.assertNotIn('FAKE-TEST-TOKEN', str(error.exception))
        self.assertIn('401', str(error.exception))


if __name__ == '__main__':
    unittest.main()
