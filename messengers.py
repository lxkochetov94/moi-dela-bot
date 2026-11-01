"""Adapters for VK community messages and MAX bots. The task logic lives in bot.py."""
import json
import os
import urllib.parse
import urllib.request
import uuid

MAIN_ACTIONS = [[("➕ Добавить задачу", "menu:add")],
                [("📋 Мои задачи", "menu:tasks"), ("📊 Скачать Excel", "menu:excel")]]


def _load(url, data=None, headers=None, method=None, timeout=20):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _multipart(field, name, content):
    boundary = '----moi-dela-' + uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{name}"\r\n'
            'Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n').encode()
    body += content + f'\r\n--{boundary}--\r\n'.encode()
    return body, f'multipart/form-data; boundary={boundary}'


class VK:
    """VK community Callback API. Works only with private community messages."""
    def __init__(self, token=None, version=None):
        self.token = token or os.environ['VK_COMMUNITY_TOKEN']
        self.version = version or os.getenv('VK_API_VERSION', '5.199')

    def api(self, method, **fields):
        params = {'access_token': self.token, 'v': self.version, **fields}
        payload = urllib.parse.urlencode(params).encode()
        result = _load('https://api.vk.com/method/' + method, data=payload)
        if 'error' in result:
            raise RuntimeError(f"VK API {method}: {result['error'].get('error_code')}")
        return result['response']

    def send(self, chat, text, keyboard=None, edit=None, menu=False):
        # Editing older message_event callback messages is less portable; send a fresh message.
        items = MAIN_ACTIONS if menu else keyboard
        params = {'peer_id': int(chat), 'random_id': uuid.uuid4().int % 2147483647,
                  'message': text[:3800]}
        if items:
            params['keyboard'] = json.dumps({'inline': True, 'buttons': [[{
                'action': {'type': 'callback', 'label': item['text'] if isinstance(item, dict) else item[0],
                           'payload': json.dumps({'cmd': item['callback_data'] if isinstance(item, dict) else item[1]})},
                'color': 'primary'} for item in row] for row in items]}, ensure_ascii=False)
        return self.api('messages.send', **params)

    def ack(self, callback_id):
        # event_id, user_id and peer_id are all required by VK.
        if isinstance(callback_id, tuple) and len(callback_id) == 3:
            event, user, peer = callback_id
            return self.api('messages.sendMessageEventAnswer', event_id=event, user_id=user, peer_id=peer)

    def document(self, chat, content, name='Мои_дела.xlsx'):
        server = self.api('docs.getMessagesUploadServer', peer_id=int(chat), type='doc')
        body, mime = _multipart('file', name, content)
        result = _load(server['upload_url'], data=body, headers={'Content-Type': mime})
        saved = self.api('docs.save', file=result['file'], title=name)
        doc = saved['doc'] if isinstance(saved, dict) else saved[0]
        attachment = f"doc{doc['owner_id']}_{doc['id']}"
        return self.api('messages.send', peer_id=int(chat), random_id=uuid.uuid4().int % 2147483647,
                        attachment=attachment, message='📊 Твои дела в Excel')


class MAX:
    """MAX Bot API; new 2026 platform-api2.max.ru endpoint."""
    endpoint = 'https://platform-api2.max.ru'

    def __init__(self, token=None):
        self.token = token or os.environ['MAX_BOT_TOKEN']

    def api(self, method, path, data=None):
        uri = self.endpoint + path
        encoded = json.dumps(data or {}, ensure_ascii=False).encode() if data is not None else None
        result = _load(uri, data=encoded, method=method,
                       headers={'Authorization': self.token, 'Content-Type': 'application/json'})
        if isinstance(result, dict) and result.get('success') is False:
            raise RuntimeError('MAX Bot API request failed')
        return result

    @staticmethod
    def payload(text, keyboard=None):
        data = {'text': text[:3900]}
        if keyboard:
            data['attachments'] = [{'type': 'inline_keyboard', 'payload': {'buttons': [[{
                'type': 'callback', 'text': item['text'] if isinstance(item, dict) else item[0],
                'payload': item['callback_data'] if isinstance(item, dict) else item[1]}
                for item in row] for row in keyboard]}}]
        return data

    def send(self, chat, text, keyboard=None, edit=None, menu=False):
        data = self.payload(text, MAIN_ACTIONS if menu else keyboard)
        if edit:
            try:
                return self.api('PUT', '/messages?' + urllib.parse.urlencode({'message_id': edit}), data)
            except Exception:
                pass  # Callback source may have been deleted; deliver a fresh message.
        return self.api('POST', '/messages?' + urllib.parse.urlencode({'user_id': str(chat)}), data)

    def ack(self, callback_id):
        if callback_id:
            return self.api('POST', '/answers?' + urllib.parse.urlencode({'callback_id': callback_id}), {})

    def document(self, chat, content, name='Мои_дела.xlsx'):
        upload = self.api('POST', '/uploads?type=file')
        body, mime = _multipart('data', name, content)
        result = _load(upload['url'], data=body, headers={'Content-Type':mime}, method='POST')
        token = result.get('token') or result.get('file',{}).get('token') or upload.get('token')
        if not token:
            raise RuntimeError('MAX upload did not return a file token')
        return self.api('POST', '/messages?' + urllib.parse.urlencode({'user_id':str(chat)}),
                        {'text':'📊 Твои дела в Excel','attachments':[{'type':'file','payload':{'token':token}}]})
