"""HTTP webhook entrypoints for MAX and VK, with signed access checks."""
import hmac
import logging
import os
from bot import Bot
from storage import YDBStore
from messengers import VK, MAX
from platform_events import body_from_http, headers_from_http, vk_normalize, max_normalize

log = logging.getLogger(__name__)
_store = None

def get_store():
    global _store
    if _store is None: _store = YDBStore()
    return _store


def reply(body='ok', code=200):
    return {'statusCode': code, 'headers': {'Content-Type': 'text/plain; charset=utf-8'}, 'body': body}


def vk_handler(event, context):
    update=body_from_http(event)
    if update.get('type') == 'confirmation':
        group = os.environ['VK_GROUP_ID']
        if str(update.get('group_id')) != group: return reply('forbidden',403)
        return reply(os.environ['VK_CONFIRMATION_CODE'])
    token=os.environ['VK_CALLBACK_SECRET']
    if not token or not hmac.compare_digest(str(update.get('secret','')),token):
        return reply('forbidden',403)
    if str(update.get('group_id')) != os.environ['VK_GROUP_ID']:
        return reply('forbidden',403)
    normalized=vk_normalize(update)
    if normalized:
        Bot(get_store(),VK()).update(normalized,platform='vk')
    return reply()


def max_handler(event, context):
    header=headers_from_http(event).get('x-max-bot-api-secret','')
    secret=os.environ['MAX_WEBHOOK_SECRET']
    if not secret or not hmac.compare_digest(header,secret):
        return reply('forbidden',403)
    update=body_from_http(event)
    normalized=max_normalize(update)
    if normalized:
        Bot(get_store(),MAX()).update(normalized,platform='max')
    return reply()
