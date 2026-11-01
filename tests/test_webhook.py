"""No network or cloud credentials needed for webhook verification tests."""
import base64
import json
import os
from unittest.mock import patch
import main


def event(body, token='test-secret', method='POST', encoded=False):
    raw = json.dumps(body)
    return {
        'httpMethod': method,
        'headers': {'X-Telegram-Bot-Api-Secret-Token': token},
        'body': base64.b64encode(raw.encode()).decode() if encoded else raw,
        'isBase64Encoded': encoded,
    }


def test_http_rejects_no_secret():
    with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'abc'}, clear=False):
        assert main.handler(event({'message': {}}, ''), None)['statusCode'] == 403


def test_http_rejects_method():
    with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'abc'}, clear=False):
        assert main.handler(event({}, method='GET'), None)['statusCode'] == 405


def test_http_accepts_telegram_payload():
    with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'abc'}, clear=False):
        class Dummy:
            called = []
            def update(self, data):
                self.called.append(data)
        dummy = Dummy()
        secret = main.webhook_secret()
        with patch.object(main, 'get_bot', return_value=dummy):
            r = main.handler(event({'message': {'text': '/start'}}, token=secret, encoded=True), None)
        assert r['statusCode'] == 200
        assert dummy.called == [{'message': {'text': '/start'}}]


def test_http_rejects_invalid_json():
    with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'abc'}, clear=False):
        r = main.handler({'httpMethod': 'POST','headers': {'x-telegram-bot-api-secret-token': main.webhook_secret()},'body': 'not-json'}, None)
        assert r['statusCode'] == 400


def test_test_action_installs_webhook_securely():
    with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'abc', 'TELEGRAM_WEBHOOK_URL': 'https://functions.yandexcloud.net/abc'}, clear=False):
        class FakeTelegram:
            def call(self, method, args):
                assert method == 'setWebhook'
                assert args['secret_token'] == main.webhook_secret()
                assert args['allowed_updates'] == ['message','callback_query']
                assert args['url'].endswith('/abc')
                return True
        with patch.object(main, 'Telegram', FakeTelegram):
            assert main.handler({'action': 'install_telegram_webhook'}, None)['statusCode'] == 200
