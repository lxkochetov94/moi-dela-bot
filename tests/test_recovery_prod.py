"""Regression tests for missing dialog state on serverless invocations."""
from bot import Bot
from storage import MemoryStore

class FakeTelegram:
    def __init__(self): self.responses=[]
    def send(self,chat,text,keyboard=None,edit=None,menu=False):
        self.responses.append((chat,text,keyboard))
    def ack(self,*a): return None
    def document(self,*a,**kw): return None

def send(bot,text):
    bot.update({"message":{"from":{"id":123},"chat":{"id":123,"type":"private"},"text":text}})

def test_work_choice_recovers_when_state_missing():
    db,tg=MemoryStore(),FakeTelegram()
    send(Bot(db,tg),"💼 Работа")
    assert db.get_state("tg:123")["stage"]=="title"
    assert db.get_state("tg:123")["draft"]["kind"]=="work"
    assert tg.responses[-1][1]=="Что нужно сделать?"

def test_personal_choice_on_separate_serverless_invocation():
    db,tg=MemoryStore(),FakeTelegram()
    send(Bot(db,tg),"/add")
    send(Bot(db,tg),"🏠 Личное")
    assert db.get_state("tg:123")["stage"]=="title"
    assert db.get_state("tg:123")["draft"]["kind"]=="personal"
    assert tg.responses[-1][2]=={"remove_keyboard":True}

def test_change_choice_after_older_button():
    db,tg=MemoryStore(),FakeTelegram()
    send(Bot(db,tg),"/add")
    send(Bot(db,tg),"🏠 Личное")
    send(Bot(db,tg),"💼 Работа")
    assert db.get_state("tg:123")["draft"]["kind"]=="work"
    assert tg.responses[-1][1]=="Что нужно сделать?"
