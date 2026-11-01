"""Convert platform webhook events into one minimal Telegram-shaped Bot.update event."""
import base64
import json


def body_from_http(event):
    body = event.get('body', event)
    if isinstance(body, str):
        if event.get('isBase64Encoded'):
            body = base64.b64decode(body).decode('utf-8')
        return json.loads(body)
    return body


def headers_from_http(event):
    return {str(k).lower():str(v) for k,v in (event.get('headers') or {}).items()}


def vk_normalize(event):
    kind = event.get('type')
    data = event.get('object') or {}
    if kind == 'message_new':
        message = data.get('message') or {}
        uid, peer = message.get('from_id'), message.get('peer_id')
        if not uid or peer != uid: return None
        return {'message': {'chat': {'id': uid,'type':'private'},
                            'from': {'id':uid}, 'text': message.get('text','')}}
    if kind == 'message_event':
        uid, peer = data.get('user_id'), data.get('peer_id')
        if not uid or uid != peer: return None
        raw = data.get('payload') or {}
        if isinstance(raw, str):
            try: raw=json.loads(raw)
            except ValueError: return None
        cmd = raw.get('cmd') if isinstance(raw, dict) else None
        if not cmd: return None
        return {'callback_query': {'id':(data.get('event_id'),uid,peer),
            'from':{'id':uid}, 'data':cmd,
            'message':{'chat':{'id':uid,'type':'private'}}}}
    return None


def max_normalize(event):
    kind=event.get('update_type')
    if kind == 'bot_started':
        uid = (event.get('user') or {}).get('user_id')
        if not uid: return None
        return {'message': {'chat':{'id':uid,'type':'private'}, 'from':{'id':uid},'text':'/start'}}
    if kind == 'message_created':
        msg=event.get('message') or {}
        uid=(msg.get('sender') or {}).get('user_id')
        recipient=msg.get('recipient') or {}
        if not uid or recipient.get('chat_type') not in ('dialog','private'): return None
        return {'message':{'chat':{'id':uid,'type':'private'},'from':{'id':uid},
                'text':(msg.get('body') or {}).get('text','')}}
    if kind == 'message_callback':
        data=event.get('callback') or {}
        uid=(data.get('user') or {}).get('user_id')
        msg=event.get('message') or {}
        if not uid or (msg.get('recipient') or {}).get('chat_type') not in ('dialog','private'):
            return None
        if not data.get('payload'): return None
        return {'callback_query':{'id':data.get('callback_id'),'from':{'id':uid},
                'data':data['payload'], 'message':{'chat':{'id':uid,'type':'private'},
                                                   'message_id':(msg.get('body') or {}).get('mid')}}}
    return None
