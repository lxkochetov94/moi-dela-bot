"""Full local pilot scenarios: actual SQLite, real bot logic, fake network boundary."""
import os
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook

import local_run
from bot import Bot
from local_sqlite import SQLiteStore


def update(i, text, owner=4321):
    return {
        "update_id": i,
        "message": {
            "from": {"id": owner},
            "chat": {"id": owner, "type": "private"},
            "text": text,
        },
    }


class FakeTelegram:
    def __init__(self, token=None, updates=None):
        self.token = token
        self.updates = list(updates or [])
        self.sent = []
        self.files = []
        self.calls = []
        self.done_poll = False

    def call(self, method, data=None, **_):
        self.calls.append((method, data))
        if method == "getMe":
            return {"is_bot": True, "username": "moi_dela_test"}
        if method == "deleteWebhook":
            return True
        if method == "getUpdates":
            if not self.done_poll:
                self.done_poll = True
                return list(self.updates)
            raise KeyboardInterrupt()
        if method == "answerCallbackQuery":
            return True
        return True

    def send(self, chat, text, keyboard=None, edit=None, menu=False):
        self.sent.append((str(chat), text, keyboard, edit, menu))

    def document(self, chat, content, name="Мои_дела.xlsx"):
        self.files.append((chat, content, name))

    def ack(self, callback_id):
        return None


def test_full_real_shaped_updates_persist_export_and_deliver_reminder(tmp_path, monkeypatch):
    messages = [
        "/start", "/add", "💼 Работа", "Подготовить КП",
        "6.11.2099 17:00", "4.11.2099 11:00", "➕ Ещё",
        "5.11.2099 11:00", "✅ Готово", "🔴 Срочно",
        "📋 Мои задачи", "📊 Скачать Excel",
    ]
    api = FakeTelegram(updates=[update(i + 1, msg) for i, msg in enumerate(messages)])
    monkeypatch.setattr(local_run, "Telegram", lambda token: api)
    monkeypatch.delenv("ALLOWED_USER_ID", raising=False)
    path = tmp_path / "pilot" / "tasks.sqlite3"

    with pytest.raises(KeyboardInterrupt):
        local_run.run(path, token="1234:valid_dummy", check_input=False, poll_timeout=1)

    assert [m[1] for m in api.sent if m[1] == "Что нужно сделать?"]
    assert any(m[1].startswith("✅ Задача сохранена!") for m in api.sent)
    assert any(m[1].startswith("📋 Мои задачи · 1") for m in api.sent)
    assert len(api.files) == 1
    book = load_workbook(BytesIO(api.files[0][1]))
    assert book.sheetnames == ["Работа", "Личное"]
    assert book["Работа"]["B2"].value == "Подготовить КП"
    assert book["Работа"]["C2"].value == "Срочно"
    assert "04.11.2099" in book["Работа"]["F2"].value
    assert "05.11.2099" in book["Работа"]["F2"].value
    assert book["Работа"].auto_filter.ref is not None

    db = SQLiteStore(path)
    assert db.get_offset() == len(messages) + 1
    assert db.get_owner_id() == 4321
    assert db.get_state("tg:4321") == {}
    task = db.list_tasks("tg:4321")[0]
    assert len(task["reminders"]) == 2
    assert len(db.due_reminders(9999999999)) == 2
    assert db.list_tasks("tg:9999") == []

    after = FakeTelegram()
    # Due reminders are sent and removed only after Telegram returns success.
    Bot(db, after, clock=lambda: task["reminders"][0]["at"]).tick()
    assert len(after.sent) == 1
    assert "Подготовить КП" in after.sent[0][1]
    assert len(db.due_reminders(9999999999)) == 1

    # Mark done via real inline callback (after restart); future reminders cancelled.
    callback = {"callback_query": {
        "id": "cb1", "from": {"id": 4321},
        "message": {"chat": {"id": 4321, "type": "private"}, "message_id": 8},
        "data": "done:" + task["id"],
    }}
    Bot(db, after).update(callback)
    assert db.get_task("tg:4321", task["id"])["status"] == "done"
    assert db.due_reminders(9999999999) == []
    db.close()

    reopened = SQLiteStore(path)
    assert reopened.get_task("tg:4321", task["id"])["status"] == "done"
    reopened.close()


def test_private_owner_binding_and_second_user_ignored(tmp_path):
    db = SQLiteStore(tmp_path / "db.sqlite3")
    api = FakeTelegram()
    assert local_run.accepted_for_owner(db, update(1, "💼 Работа"), api) is False
    assert db.get_owner_id() is None
    assert local_run.accepted_for_owner(db, update(2, "/start"), api) is True
    assert db.get_owner_id() == 4321
    assert local_run.accepted_for_owner(db, update(3, "/start", owner=7654), api) is False
    db.close()


def test_append_notes_and_change_category_reflected_in_excel(tmp_path):
    db = SQLiteStore(tmp_path / "db.sqlite3")
    api = FakeTelegram()
    bot = Bot(db, api)

    def say(text):
        bot.update(update(1, text))

    for text in ("/start", "/add", "🏠 Личное", "Забрать посылку",
                 "Без срока", "Без напоминания", "🟡 Важно"):
        say(text)
    task = db.list_tasks("tg:4321")[0]
    tid = task["id"]
    bot.callback("tg:4321", 4321, "info:" + tid)
    say("Посылка №123")
    bot.callback("tg:4321", 4321, "info:" + tid)
    say("Забрать паспорт")
    t = db.get_task("tg:4321", tid)
    assert [n["text"] for n in t["notes"]] == ["Посылка №123", "Забрать паспорт"]
    bot.callback("tg:4321", 4321, f"kind:{tid}:work")
    assert db.get_task("tg:4321", tid)["kind"] == "work"
    say("/excel")
    book = load_workbook(BytesIO(api.files[-1][1]))
    assert book["Работа"]["B2"].value == "Забрать посылку"
    assert "Забрать паспорт" in book["Работа"]["G2"].value
    assert book["Личное"].max_row == 1
    db.close()


def test_cancel_and_no_spurious_task_after_restart(tmp_path):
    path = tmp_path / "db.sqlite3"
    db = SQLiteStore(path)
    api = FakeTelegram()
    for value in ("/add", "💼 Работа", "Записать", "/cancel"):
        Bot(db, api).update(update(1, value))
    assert db.get_state("tg:4321") == {}
    assert db.list_tasks("tg:4321") == []
    db.close()
    again = SQLiteStore(path)
    assert again.list_tasks("tg:4321") == []
    again.close()


def test_deadline_edit_does_not_silently_discard_reminders(tmp_path):
    db = SQLiteStore(tmp_path / "db.sqlite3")
    api = FakeTelegram()
    bot = Bot(db, api)
    def say(text):
        bot.update(update(1, text))
    for text in ("/add", "💼 Работа", "Сдать отчёт",
                 "6.11.2099 17:00", "5.11.2099 11:00",
                 "✅ Готово", "🔴 Срочно"):
        say(text)
    task = db.list_tasks("tg:4321")[0]
    tid = task["id"]
    original_deadline = task["deadline"]
    reminder_id = task["reminders"][0]["id"]

    bot.callback("tg:4321", 4321, f"pd:{tid}")
    say("4.11.2099 16:00")  # Earlier than the existing reminder.
    task = db.get_task("tg:4321", tid)
    assert task["deadline"] == original_deadline
    assert task["reminders"][0]["id"] == reminder_id
    assert any("Срок не изменён" in r[1] for r in api.sent)

    bot.callback("tg:4321", 4321, f"dr:{tid}:{reminder_id}")
    assert len(db.get_task("tg:4321", tid)["reminders"]) == 1
    assert len(db.due_reminders(9999999999)) == 1

    bot.callback("tg:4321", 4321, f"done:{tid}")
    assert db.due_reminders(9999999999) == []
    bot.callback("tg:4321", 4321, f"st:{tid}:in_progress")
    # Since these are future reminders, reopening restores the pending queue.
    assert len(db.due_reminders(9999999999)) == 1
    db.close()
