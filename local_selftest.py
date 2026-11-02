"""Offline smoke test for the packaged Windows executable itself."""
import os
import tempfile
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook
from bot import Bot
from local_sqlite import SQLiteStore


class FakeTelegram:
    def __init__(self):
        self.messages=[]
        self.documents=[]

    def send(self, chat, text, keyboard=None, edit=None, menu=False):
        self.messages.append(text)

    def document(self, chat, content, name="Мои_дела.xlsx"):
        self.documents.append(content)

    def ack(self, callback_id):
        return None


def run_self_test():
    os.environ["BOT_TIMEZONE"]="Europe/Moscow"
    from dates import parse,fmt
    future=parse("16.12.2099 17:00")
    assert fmt(future)=="16.12.2099 17:00"
    with tempfile.TemporaryDirectory() as folder:
        db=SQLiteStore(Path(folder)/"pilot.db")
        tg=FakeTelegram()
        def send(text):
            Bot(db,tg).update({"message":{"from":{"id":11},
                                          "chat":{"id":11,"type":"private"},
                                          "text":text}})
        for text in ("/start","/add","💼 Работа","Проверка задач",
                     "16.12.2099 17:00","15.12.2099 11:00",
                     "✅ Готово","🟡 Важно","📋 Мои задачи","📊 Скачать Excel"):
            send(text)
        task=db.list_tasks("tg:11")[0]
        assert task["title"]=="Проверка задач"
        assert len(task["reminders"])==1
        assert len(tg.documents)==1
        wb=load_workbook(BytesIO(tg.documents[0]))
        assert wb.sheetnames==["Работа","Личное"]
        assert wb["Работа"]["B2"].value=="Проверка задач"
        assert wb["Работа"]["E1"].value=="Дедлайн"
        Bot(db,tg,clock=lambda:task["reminders"][0]["at"]).tick()
        assert any("🔔 Пора: Проверка задач" in x for x in tg.messages)
        db.close()
    print("SELF-TEST PASSED: date/time, SQLite, Telegram dialog, reminders, Excel.")
