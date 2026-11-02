"""Run a real Telegram bot locally: no Yandex, Cloudflare, server or YDB.

Python 3.11+, openpyxl. The local computer must remain on to deliver reminders.
Bot token is never written to a file. Tasks stay in local SQLite.
"""
import getpass
import os
import sys
import time
import urllib.error
from pathlib import Path

from bot import Bot
from local_sqlite import SQLiteStore
from telegram_api import Telegram


def private_owner_id(update):
    message = update.get("message") or {}
    callback = update.get("callback_query") or {}
    if callback:
        chat = callback.get("message", {}).get("chat", {})
        sender = callback.get("from", {})
    else:
        chat = message.get("chat", {})
        sender = message.get("from", {})
    if chat.get("type") != "private" or not isinstance(sender.get("id"), int):
        return None
    return sender["id"]


def accepted_for_owner(store, update, api):
    sender_id = private_owner_id(update)
    if sender_id is None:
        return False
    owner_id = store.get_owner_id()
    if owner_id is None:
        message = update.get("message") or {}
        text = str(message.get("text") or "").strip()
        if text.split(" ", 1)[0].split("@", 1)[0] != "/start":
            # The bot must be started by its owner before it is used.
            return False
        owner_id = store.bind_owner_id(sender_id)
        if owner_id == sender_id:
            print("Владелец привязан. Второй аккаунт к этому боту не подключится.")
    if owner_id != sender_id:
        return False
    return True


def run(db_path=None, token=None, poll_timeout=5, check_input=True):
    os.environ.setdefault("BOT_TIMEZONE", "Europe/Moscow")
    # In local mode call Telegram directly: no proxy keys or cloud variables.
    os.environ.pop("TELEGRAM_API_PROXY_URL", None)
    os.environ.pop("TELEGRAM_PROXY_KEY", None)
    token = (token or os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        token = getpass.getpass("Вставь токен бота из BotFather (ввод скрыт): ").strip()
    if not token or ":" not in token:
        raise ValueError("Токен Telegram должен содержать двоеточие. Получи его в BotFather.")
    api = Telegram(token=token)
    profile = api.call("getMe", {})
    if not profile or not profile.get("is_bot"):
        raise RuntimeError("Telegram не подтвердил токен бота")
    db_file = Path(db_path or Path.home() / ".moi-dela" / "tasks.sqlite3")
    db = SQLiteStore(db_file)
    try:
        print("Подключён Telegram: @" + str(profile.get("username", "bot")))
        print("Задачи хранятся на этом компьютере: " + str(db_file))
        print("Этот локальный тест отключит текущий Telegram webhook.")
        if check_input:
            answer = input("Запустить локальную версию? [д/н]: ").strip().lower()
            if answer not in ("д", "да", "y", "yes"):
                print("Запуск отменён. Вебхук не менялся.")
                return
        # You cannot use Telegram getUpdates while a webhook is configured.
        # Clear ONLY on the first local run; subsequent starts preserve the queue.
        db_has_offset = db.get_offset() > 0
        api.call("deleteWebhook", {"drop_pending_updates": not db_has_offset})
        print("Готово. Открой Telegram, напиши боту /start и используй кнопки.")
        print("Напоминания приходят, пока это окно открыто. Остановить: Ctrl+C.")
        bot = Bot(db, api)
        errors = 0
        while True:
            # Poll for up to five seconds so due reminders are dispatched promptly.
            try:
                updates = api.call("getUpdates", {
                    "offset": db.get_offset(),
                    "timeout": min(int(poll_timeout), 5),
                    "limit": 50,
                    "allowed_updates": ["message", "callback_query"],
                })
                errors = 0
                for update in updates or []:
                    update_id = update.get("update_id")
                    if not isinstance(update_id, int):
                        continue
                    if update_id < db.get_offset():
                        continue
                    if accepted_for_owner(db, update, api):
                        bot.update(update)
                    db.set_offset(update_id + 1)
            except (urllib.error.HTTPError, urllib.error.URLError, OSError, TimeoutError) as exc:
                errors += 1
                code = getattr(exc, "code", None)
                label = "HTTP " + str(code) if code else type(exc).__name__
                print("Сбой связи с Telegram (" + label + "); повторное подключение.")
                if code == 409:
                    print("Telegram сообщает о втором получателе обновлений. "
                          "Закрой другую запущенную копию бота.")
                    raise RuntimeError("Conflict: another Telegram poller is running") from None
                if code in (401, 403):
                    raise RuntimeError("Telegram отклонил токен или доступ") from None
                time.sleep(min(2 * errors, 10))
            # Reminder failures do not delete queued notifications, so retry later.
            try:
                bot.tick()
            except (urllib.error.HTTPError, urllib.error.URLError, OSError, TimeoutError):
                print("Отправка напоминания не удалась; оно осталось в очереди.")
                time.sleep(3)
    finally:
        db.close()


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nБот остановлен. Задачи сохранены. Напоминания возобновятся после запуска.")
    except Exception as exc:
        # Never print request URLs, headers, BotFather tokens, task text or tracebacks.
        print("Не удалось запустить бот: " + type(exc).__name__)
        print("Проверь токен, интернет и наличие запущенной второй копии бота.")
        sys.exit(1)
