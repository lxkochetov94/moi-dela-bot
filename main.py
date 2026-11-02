"""Yandex Cloud Function: Telegram webhook and administrative setup.

HTTPS requests must carry Telegram's secret-token header. The header value is
SHA-256 of the BotFather token, so no second secret needs to be stored.

To register the HTTPS webhook from the authenticated Yandex Cloud testing
console, invoke this function with {"action":"install_telegram_webhook"}.
Do not expose the raw install action over HTTPS: HTTP input has an envelope.
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
from bot import Bot
from storage import YDBStore
from telegram_api import Telegram

log = logging.getLogger(__name__)
_bot = None


def get_bot():
    global _bot
    if _bot is None:
        _bot = Bot(YDBStore(), Telegram())
    return _bot


def webhook_secret():
    # Only the hash is sent to Telegram; the BotFather token is never logged.
    return hashlib.sha256(os.environ["TELEGRAM_BOT_TOKEN"].encode("utf-8")).hexdigest()


def install_telegram_webhook():
    """Authenticated cloud-console test action, not a public HTTP endpoint."""
    url = os.environ.get("TELEGRAM_WEBHOOK_URL", "").strip()
    if not (url.startswith("https://functions.yandexcloud.net/") and
            "/" not in url.removeprefix("https://functions.yandexcloud.net/").rstrip("/")):
        raise ValueError("Set TELEGRAM_WEBHOOK_URL to this function's public HTTPS address")
    result = Telegram().call("setWebhook", {
        "url": url,
        "allowed_updates": ["message", "callback_query"],
        "secret_token": webhook_secret(),
        "max_connections": 2,
        "drop_pending_updates": True,
    })
    if result is not True:
        raise RuntimeError("Telegram did not confirm webhook installation")
    return {"statusCode": 200, "body": "Telegram webhook installed"}


def healthcheck():
    """Cloud Shell-only diagnostic; never exposes personal data or secrets."""
    from uuid import uuid4
    db=YDBStore()
    owner="probe:"+uuid4().hex
    sample={"stage":"probe","draft":{"kind":"work"}}
    try:
        db.put_state(owner,sample)
        found=db.get_state(owner)
        if found != sample:
            raise RuntimeError("YDB state roundtrip mismatch")
        rows=db.query("SELECT state FROM users LIMIT 30;")
        stages={}
        for row in rows:
            try:
                stage=json.loads(row["state"] or "{}").get("stage","none")
                stages[stage]=stages.get(stage,0)+1
            except Exception:
                stages["unreadable"]=stages.get("unreadable",0)+1
        diagnostic = db.get_state("diagnostics:telegram_error")
        safe_error = {k: diagnostic[k] for k in ("category", "http_status", "timestamp")
                      if k in diagnostic}
        return {"statusCode":200, "body":json.dumps({
            "ydb_roundtrip":"ok", "sample_dialog_stages":stages,
            "last_transport_error":safe_error or None,
            "notice":"No messages, tokens, user IDs, or task text returned"
        })}
    finally:
        db.put_state(owner,{})


def transportcheck():
    """Read-only Telegram API probe using exactly the deployed proxy settings."""
    started = time.monotonic()
    try:
        result = Telegram().call("getMe", {})
        return {"statusCode": 200, "body": json.dumps({
            "telegram_via_cloudflare":"ok" if result and result.get("is_bot") else "unexpected",
            "elapsed_ms": round((time.monotonic()-started)*1000)
        })}
    except Exception as exc:
        # Do not include URL, token, headers, usernames, request or response text.
        status = exc.code if isinstance(exc, urllib.error.HTTPError) else None
        return {"statusCode": 200, "body": json.dumps({
            "telegram_via_cloudflare":"failed",
            "error_category":type(exc).__name__,
            "http_status": status,
            "elapsed_ms": round((time.monotonic()-started)*1000)
        })}


def store_safe_error(exc):
    """Record only a broad error class/status so locked-down logging isn't required."""
    try:
        diagnostic={"stage":"transport_error","category":type(exc).__name__,
                    "timestamp":int(time.time())}
        if isinstance(exc, urllib.error.HTTPError):
            diagnostic["http_status"]=exc.code
        get_bot().db.put_state("diagnostics:telegram_error",diagnostic)
    except Exception:
        log.warning("Unable to persist sanitized transport diagnostics")


def handle_http(event):
    if event.get("httpMethod") != "POST":
        return {"statusCode": 405, "body": "Method Not Allowed"}
    headers = {str(k).lower(): str(v) for k, v in (event.get("headers") or {}).items()}
    received = headers.get("x-telegram-bot-api-secret-token", "")
    if not hmac.compare_digest(received, webhook_secret()):
        return {"statusCode": 403, "body": "Forbidden"}
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw, validate=True)
        except (ValueError, base64.binascii.Error):
            return {"statusCode": 400, "body": "Bad Request"}
    if len(raw) > 128 * 1024:
        return {"statusCode": 413, "body": "Too Large"}
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError, UnicodeDecodeError):
        return {"statusCode": 400, "body": "Invalid JSON"}
    if not isinstance(payload, dict):
        return {"statusCode": 400, "body": "Invalid update"}
    if "message" in payload or "callback_query" in payload:
        get_bot().update(payload)
    return {"statusCode": 200, "body": "OK"}


def handler(event, context):
    try:
        if not isinstance(event, dict):
            return {"statusCode": 400, "body": "Bad Request"}
        if "httpMethod" in event:
            return handle_http(event)
        if event.get("action") == "install_telegram_webhook":
            return install_telegram_webhook()
        if event.get("action") == "healthcheck":
            return healthcheck()
        if event.get("action") == "transportcheck":
            return transportcheck()
        if event.get("messages") and any(
            item.get("event_metadata", {}).get("event_type", "").endswith("TimerMessage")
            for item in event["messages"]
        ):
            get_bot().tick()
        elif "message" in event or "callback_query" in event:
            get_bot().update(event)
        elif event.get("payload") == "reminders" or event.get("action") == "reminders":
            get_bot().tick()  # Cloud Console test / timer compatibility
        else:
            log.info("Ignoring unsupported event")
    except Exception as exc:
        log.exception("Bot event failed")
        store_safe_error(exc)
        raise
    return {"statusCode": 200, "body": "OK"}
