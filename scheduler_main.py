"""Yandex timer entry: dispatch due reminder in its ORIGINAL messenger."""
from bot import Bot
from storage import YDBStore
from telegram_api import Telegram
from messengers import VK, MAX


def handler(event, context):
    db = YDBStore()
    # Each pass processes only reminders for its own platform, sharing one DB.
    # Avoid reading a token if that platform is not enabled for this deployment.
    import os
    channels=[('tg','TELEGRAM_BOT_TOKEN',Telegram),
              ('vk','VK_COMMUNITY_TOKEN',VK),
              ('max','MAX_BOT_TOKEN',MAX)]
    for platform,env_name,cls in channels:
        if os.getenv(env_name):
            Bot(db, cls()).tick(platform=platform)
    return {'statusCode':200,'body':'OK'}
