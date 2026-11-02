import json
import os
from unittest.mock import patch
from telegram_api import Telegram


class FakeResponse:
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self): return json.dumps({"ok": True, "result": {"message_id": 42}}).encode()


def test_telegram_default_direct_api():
    with patch.dict(os.environ, {}, clear=True), patch('urllib.request.urlopen', return_value=FakeResponse()) as urlopen:
        result = Telegram('123:abcd').call('sendMessage', {'chat_id': 1, 'text': 'Hi'})
        assert result['message_id'] == 42
        request = urlopen.call_args.args[0]
        assert request.full_url == 'https://api.telegram.org/bot123:abcd/sendMessage'
        assert request.get_header('X-moi-dela-proxy-key') is None


def test_telegram_private_relay_json_and_document():
    env = {'TELEGRAM_API_PROXY_URL': 'https://example.workers.dev/', 'TELEGRAM_PROXY_KEY': 'super-secret'}
    with patch.dict(os.environ, env), patch('urllib.request.urlopen', return_value=FakeResponse()) as urlopen:
        tg = Telegram('123:abcd')
        tg.call('sendMessage', {'chat_id': 1, 'text': 'Задача'})
        req = urlopen.call_args.args[0]
        assert req.full_url == 'https://example.workers.dev/sendMessage'
        assert req.get_header('X-moi-dela-bot-token') == '123:abcd'
        assert req.get_header('X-moi-dela-proxy-key') == 'super-secret'
        assert b'\\xd0' in req.data
        tg.document(1, b'PKfake', 'tasks.xlsx')
        req = urlopen.call_args.args[0]
        assert req.full_url == 'https://example.workers.dev/sendDocument'
        assert b'PKfake' in req.data
        assert req.get_header('Content-type').startswith('multipart/form-data; boundary=')


def test_telegram_relay_requires_key():
    with patch.dict(os.environ, {'TELEGRAM_API_PROXY_URL': 'https://example.workers.dev'}, clear=True):
        try:
            Telegram('123:abcd').call('sendMessage')
        except ValueError as e:
            assert 'TELEGRAM_PROXY_KEY' in str(e)
        else:
            assert False, 'Missing key was accepted'
