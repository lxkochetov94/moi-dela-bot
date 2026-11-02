"""Regression tests for silent bot after Telegram /add and reply keyboard."""
from bot import Bot
from storage import MemoryStore


class API:
    def __init__(self):
        self.sent = []
    def send(self, chat, text, keyboard=None, edit=None, menu=False):
        self.sent.append((chat, text, keyboard, edit, menu))
    def ack(self, callback_id):
        return None


def update(bot, message):
    bot.update({"message": {
        "from": {"id": 42},
        "chat": {"id": 42, "type": "private"},
        "text": message,
    }})


def test_add_is_not_swallowed_in_existing_draft():
    db, api = MemoryStore(), API()
    bot = Bot(db, api)
    update(bot, "/start")
    update(bot, "➕ Добавить задачу")
    assert db.get_state("tg:42")["stage"] == "kind"
    assert "по работе" in api.sent[-1][1]
    update(bot, "/add")
    assert "по работе" in api.sent[-1][1]
    update(bot, "/add@moi_dela_notes_bot")
    assert "по работе" in api.sent[-1][1]


def test_button_variant_and_unexpected_input_respond():
    db, api = MemoryStore(), API()
    bot = Bot(db, api)
    update(bot, "➕️ Добавить задачу")
    assert db.get_state("tg:42")["stage"] == "kind"
    update(bot, "неожиданный текст")
    assert "по работе" in api.sent[-1][1]
    bot.update({"callback_query": {
        "id": "cb", "from": {"id": 42},
        "message": {"chat": {"id": 42, "type": "private"}, "message_id": 1},
        "data": "new:work",
    }})
    assert db.get_state("tg:42")["stage"] == "title"
    assert api.sent[-1][1] == "Что нужно сделать?"


def test_cancel_and_global_task_command():
    db, api = MemoryStore(), API()
    bot = Bot(db, api)
    update(bot, "/add")
    update(bot, "/tasks")
    assert "Мои задачи" in api.sent[-1][1]
    update(bot, "/cancel")
    assert db.get_state("tg:42") == {}
    update(bot, "/add")
    assert db.get_state("tg:42")["stage"] == "kind"
