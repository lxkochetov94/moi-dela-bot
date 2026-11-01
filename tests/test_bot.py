from datetime import datetime
from zoneinfo import ZoneInfo
from io import BytesIO
from openpyxl import load_workbook
from bot import Bot
from storage import MemoryStore
from dates import parse,fmt
from exporter import excel, safe


class FakeTG:
    def __init__(self):
        self.sent=[];self.docs=[];self.acks=[]
    def send(self,chat,text,keyboard=None,edit=None,menu=False):
        self.sent.append({"chat":chat,"text":text,"keyboard":keyboard,"edit":edit,"menu":menu})
    def document(self,chat,content,name="Мои_дела.xlsx"):
        self.docs.append((chat,content,name))
    def ack(self,key):self.acks.append(key)


def make_bot():
    s=MemoryStore();tg=FakeTG();b=Bot(s,tg)
    return b,s,tg


def cb(bot,data,owner=101):bot.callback(owner,owner,data)


def flow(bot,store,owner=101,kind="work",reminders=("15.12.2099 11:00",),deadline="16.12.2099 17:00"):
    bot.create(owner,owner)
    cb(bot,"new:"+kind,owner)
    bot.text(owner,owner,"Подготовить КП" if kind=="work" else "Забрать ребёнка")
    assert store.get_state(owner)["stage"]=="deadline"
    bot.text(owner,owner,deadline)
    for i,date in enumerate(reminders):
        if i: cb(bot,"rem:more",owner)
        bot.text(owner,owner,date)
    cb(bot,"rem:done",owner)
    cb(bot,"priority:red",owner)
    return store.list_tasks(owner)[-1]


def test_flow_multiple_reminders_and_stages():
    bot,s,tg=make_bot()
    t=flow(bot,s,reminders=("14.12.2099 11:00","15.12.2099 11:00"))
    assert t["kind"]=="work"
    assert t["priority"]=="red"
    assert len(t["reminders"])==2
    assert len(s.reminders)==2
    assert s.get_state(101)=={}
    assert "Задача сохранена" in " ".join(x["text"] for x in tg.sent)


def test_no_deadline_allows_no_reminder():
    b,s,tg=make_bot()
    b.create(101,101);cb(b,"new:personal")
    b.text(101,101,"Купить хлеб")
    cb(b,"date:none");cb(b,"rem:skip");cb(b,"priority:green")
    t=s.list_tasks(101)[0]
    assert t["deadline"] is None and not t["reminders"]


def test_reminder_cannot_be_after_deadline():
    b,s,tg=make_bot()
    b.create(101,101);cb(b,"new:work")
    b.text(101,101,"Важное дело");b.text(101,101,"15.12.2099 10:00")
    b.text(101,101,"16.12.2099 10:00")
    assert s.get_state(101)["stage"]=="reminder"
    assert "не позже срока" in tg.sent[-1]["text"]


def test_edit_notes_priority_kind_status_and_excel():
    b,s,tg=make_bot();t=flow(b,s)
    tid=t["id"]
    cb(b,f"info:{tid}")
    b.text(101,101,"Добавить два бюджета")
    cb(b,f"prio:{tid}:yellow")
    cb(b,f"kind:{tid}:personal")
    cb(b,f"st:{tid}:in_progress")
    assert s.get_task(101,tid)["notes"][0]["text"]=="Добавить два бюджета"
    assert s.get_task(101,tid)["priority"]=="yellow"
    assert s.get_task(101,tid)["kind"]=="personal"
    b.menu(101,101,"📊 Скачать Excel")
    assert tg.docs
    x=load_workbook(BytesIO(tg.docs[0][1]))
    assert x.sheetnames==["Работа","Личное"]
    assert x["Работа"].max_row==1
    assert x["Личное"]["B2"].value=="Подготовить КП"
    assert x["Личное"]["C2"].value=="Важно"
    assert "Добавить два бюджета" in x["Личное"]["G2"].value


def test_completion_cancels_scheduled_reminders():
    b,s,tg=make_bot();t=flow(b,s)
    cb(b,f"done:{t['id']}")
    assert s.get_task(101,t["id"])["status"]=="done"
    assert len(s.reminders)==0
    cb(b,f"st:{t['id']}:in_progress")
    assert s.get_task(101,t["id"])["status"]=="in_progress"


def test_due_reminder_sent_by_scheduler():
    b,s,tg=make_bot()
    t=flow(b,s)
    due=t["reminders"][0]["at"]
    b.clock=lambda:due
    b.tick()
    assert len(s.reminders)==0
    assert "🔔 Подготовить КП" in tg.sent[-1]["text"]
    assert any("Позже" in x["text"] for row in tg.sent[-1]["keyboard"] for x in row)


def test_snooze_works_and_doesnt_change_deadline():
    b,s,tg=make_bot();t=flow(b,s)
    before=t["deadline"]
    b.clock=lambda:t["reminders"][0]["at"]
    cb(b,f"snooze:{t['id']}:10")
    newer=s.get_task(101,t["id"])
    assert newer["deadline"]==before
    assert len(newer["reminders"])==2
    assert len(s.reminders)==2


def test_delete_confirmation_and_hidden_in_excel():
    b,s,tg=make_bot();t=flow(b,s)
    cb(b,f"delete:{t['id']}")
    assert not s.get_task(101,t["id"])["deleted"]
    cb(b,f"del:{t['id']}")
    assert s.get_task(101,t["id"])["deleted"]
    x=load_workbook(BytesIO(excel(s.list_tasks(101))))
    assert x["Работа"].max_row==1


def test_user_data_isolation():
    b,s,tg=make_bot();t=flow(b,s)
    assert not s.list_tasks(102)
    assert s.get_task(102,t["id"]) is None


def test_dates_and_formula_injection():
    d=parse("31.12.2099 в 17")
    assert fmt(d).endswith("17:00")
    assert safe("=1+1")=="'=1+1"
    assert safe("Обычная задача")=="Обычная задача"


def test_unknown_group_not_processed():
    b,s,tg=make_bot()
    b.update({"message":{"chat":{"id":101,"type":"group"},"from":{"id":101},"text":"/start"}})
    assert not tg.sent
