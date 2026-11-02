"""Telegram reply-keyboard conversation across independent serverless invocations.

These tests use the actual event shape and real XLSX serialization, but a
fake Telegram transport and in-memory DB. They do not claim cloud readiness.
"""
from io import BytesIO
from openpyxl import load_workbook
from bot import Bot
from storage import MemoryStore


class TelegramSpy:
    def __init__(self):
        self.messages = []
        self.files = []

    def send(self, chat, text, keyboard=None, edit=None, menu=False):
        self.messages.append({"chat": chat, "text": text, "keyboard": keyboard, "menu": menu})

    def document(self, chat, content, name="Мои_дела.xlsx"):
        self.files.append((chat, content, name))

    def ack(self, callback_id):
        return None


def say(store, telegram, text):
    # Recreate the Bot on each event, just as a new Yandex Cloud Function worker could.
    Bot(store, telegram).update({
        "message": {
            "from": {"id": 5252},
            "chat": {"id": 5252, "type": "private"},
            "text": text,
        }
    })


def test_telegram_text_only_personal_task_to_excel():
    db, api = MemoryStore(), TelegramSpy()
    for text in (
        "/start", "/add", "🏠 Личное", "Купить хлеб",
        "Без срока", "Без напоминания", "🟢 Не горит",
    ):
        say(db, api, text)

    assert any(x["text"] == "Что нужно сделать?" for x in api.messages)
    assert any(x["text"].startswith("✅ Задача сохранена!") for x in api.messages)
    assert db.get_state("tg:5252") == {}
    tasks = db.list_tasks("tg:5252")
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Купить хлеб"
    assert tasks[0]["kind"] == "personal"
    assert tasks[0]["status"] == "not_started"

    say(db, api, "📋 Мои задачи")
    assert "📋 Мои задачи · 1" in api.messages[-1]["text"]
    say(db, api, "📊 Скачать Excel")
    assert len(api.files) == 1
    workbook = load_workbook(BytesIO(api.files[0][1]))
    assert workbook.sheetnames == ["Работа", "Личное"]
    assert workbook["Личное"]["B2"].value == "Купить хлеб"


def test_telegram_text_only_work_task_to_reminder():
    db, api = MemoryStore(), TelegramSpy()
    for text in (
        "/add", "💼 Работа", "Подготовить письмо",
        "16.12.2099 17:00", "15.12.2099 11:00",
        "✅ Готово", "🔴 Срочно",
    ):
        say(db, api, text)

    tasks = db.list_tasks("tg:5252")
    assert len(tasks) == 1
    task = tasks[0]
    assert task["kind"] == "work"
    assert task["priority"] == "red"
    assert len(task["reminders"]) == 1

    api.messages.clear()
    tick = Bot(db, api, clock=lambda: task["reminders"][0]["at"])
    tick.tick(platform="tg")
    assert len(api.messages) == 1
    assert api.messages[0]["text"].startswith("🔔 Пора: Подготовить письмо")
    assert db.due_reminders(task["reminders"][0]["at"]) == []
