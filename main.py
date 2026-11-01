"""Yandex Cloud Functions entry point: main.handler.

Bind a service account with the ydb.editor role. Create two triggers:
Telegram (updates: message, callback_query) and timer (payload: reminders).
"""
import logging
from bot import Bot
from storage import YDBStore
from telegram_api import Telegram

log=logging.getLogger(__name__)
_bot=None


def get_bot():
    global _bot
    if _bot is None:
        _bot=Bot(YDBStore(),Telegram())
    return _bot


def handler(event, context):
    try:
        if event.get("messages") and any(item.get("event_metadata",{}).get("event_type","").endswith("TimerMessage")
                                         for item in event["messages"]):
            get_bot().tick()
        elif "message" in event or "callback_query" in event:
            get_bot().update(event)
        elif event.get("payload")=="reminders" or event.get("action")=="reminders":
            get_bot().tick()  # local testing / manual invocation
        else:
            log.info("Ignoring unsupported event")
    except Exception:
        log.exception("Bot event failed")
        raise  # allows Yandex triggers to retry temporary failures
    return {"statusCode":200,"body":"OK"}
