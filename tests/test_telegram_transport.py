"""Outgoing Telegram API relay: bounded retry and explicit permanent failures."""
import io
import json
import urllib.error

import pytest
from telegram_api import Telegram


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.close()


@pytest.fixture
def proxy_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "12345:abcdefghijklmnopqrstuvwxyz_123456")
    monkeypatch.setenv("TELEGRAM_API_PROXY_URL", "https://example.workers.dev")
    monkeypatch.setenv("TELEGRAM_PROXY_KEY", "test-only")
    monkeypatch.setattr("time.sleep", lambda _: None)


def test_transient_timeout_is_retried_once(monkeypatch, proxy_env):
    calls = []
    def urlopen(request, timeout):
        calls.append((request, timeout))
        if len(calls) == 1:
            raise urllib.error.URLError("temporary timeout")
        return FakeResponse(json.dumps({"ok":True,"result":{"message_id":1}}).encode())
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    result = Telegram().call("sendMessage", {"chat_id":1,"text":"test"})
    assert result["message_id"]==1
    assert len(calls)==2
    assert all(timeout == 10 for _,timeout in calls)


def test_permanent_403_not_retried(monkeypatch, proxy_env):
    calls = []
    def urlopen(request,timeout):
        calls.append(1)
        raise urllib.error.HTTPError(request.full_url,403,"Forbidden",None,None)
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    with pytest.raises(urllib.error.HTTPError):
        Telegram().call("sendMessage", {"chat_id":1,"text":"test"})
    assert len(calls)==1


def test_two_transient_failures_are_reported(monkeypatch, proxy_env):
    calls = []
    def urlopen(request,timeout):
        calls.append(1)
        raise urllib.error.HTTPError(request.full_url,502,"Bad Gateway",None,None)
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    with pytest.raises(urllib.error.HTTPError):
        Telegram().call("sendMessage", {"chat_id":1,"text":"test"})
    assert len(calls)==2
