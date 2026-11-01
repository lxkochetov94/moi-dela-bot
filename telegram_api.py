"""Small Telegram Bot API client without long-polling, frameworks or servers."""
import json
import os
import urllib.parse
import urllib.request
import uuid


class Telegram:
    def __init__(self, token=None):
        self.token = token or os.environ["TELEGRAM_BOT_TOKEN"]

    def call(self, method, data=None, file_bytes=None, filename=None):
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        if file_bytes is None:
            body = json.dumps(data or {}, ensure_ascii=False).encode("utf-8")
            request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        else:
            boundary = "----moi-dela-" + uuid.uuid4().hex
            parts = []
            for key, value in (data or {}).items():
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
            parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{filename}"\r\n'
                          'Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n').encode())
            parts.append(file_bytes)
            parts.append(f'\r\n--{boundary}--\r\n'.encode())
            request = urllib.request.Request(url, data=b''.join(parts), headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.load(response)
        if not payload.get("ok"):
            raise RuntimeError("Telegram API returned an error")
        return payload.get("result")

    def send(self, chat, text, keyboard=None, menu=False, edit=None):
        args = {"chat_id": chat, "text": text, "disable_web_page_preview": True}
        if keyboard is not None:
            args["reply_markup"] = {"inline_keyboard": keyboard}
        if menu:
            args["reply_markup"] = {"keyboard": [[{"text":"➕ Добавить задачу"}],
                                                  [{"text":"📋 Мои задачи"}, {"text":"📊 Скачать Excel"}]],
                                    "resize_keyboard": True, "is_persistent": True}
        if edit is not None and not menu:
            try:
                return self.call("editMessageText", {**args, "message_id": edit})
            except Exception:
                pass
        return self.call("sendMessage", args)

    def ack(self, callback_id):
        return self.call("answerCallbackQuery", {"callback_query_id": callback_id})

    def document(self, chat, content, name="Мои_дела.xlsx"):
        return self.call("sendDocument", {"chat_id": chat}, file_bytes=content, filename=name)


def buttons(*rows):
    """Rows of (label, data) pairs; compact callback payloads (< 64 bytes)."""
    return [[{"text": label, "callback_data": code} for label, code in row] for row in rows]
