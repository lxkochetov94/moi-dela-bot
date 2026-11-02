"""Shared task bot: identical dialog on Telegram, VK and MAX."""
import os
import time
import uuid
from datetime import datetime
from dates import fmt,parse
from exporter import excel
from telegram_api import buttons

KIND={"work":"💼 Работа","personal":"🏠 Личное"}
PRIO={"red":"🔴 Срочно","yellow":"🟡 Важно","green":"🟢 Не горит"}
STATUS={"not_started":"Не начато","in_progress":"В работе","done":"Сделано"}


def make_id():
    return uuid.uuid4().hex[:12]


class Bot:
    def __init__(self, store, telegram, clock=None):
        self.db=store
        self.tg=telegram
        self.clock=clock or (lambda:int(time.time()))

    def send(self, chat, text, keyboard=None, edit=None, menu=False):
        return self.tg.send(chat,text,keyboard=keyboard,edit=edit,menu=menu)

    def task_text(self, t):
        memo="\n".join("• "+fmt(x["at"]) for x in sorted(t.get("reminders",[]),key=lambda r:r["at"])) or "Нет"
        info="\n".join("• "+x["text"] for x in t.get("notes",[]))
        if len(info)>900: info=info[:895]+"…"
        return (f"{KIND[t['kind']]}  {t['title']}\n\n"
                f"{PRIO[t['priority']]}\n"
                f"📋 {STATUS[t['status']]}\n"
                f"📅 Срок: {fmt(t.get('deadline'))}\n"
                f"🔔 Напоминания:\n{memo}"+
                (f"\n\n📝 {info}" if info else ""))

    def view(self, chat, t, edit=None):
        key=buttons([("✅ Сделано",f"done:{t['id']}"),("✏️ Изменить",f"edit:{t['id']}")],
                    [("↩️ К задачам","list:active:0")]) if t["status"]!="done" else buttons(
                    [("✏️ Изменить",f"edit:{t['id']}")],[("↩️ К задачам","list:active:0")])
        self.send(chat,self.task_text(t),key,edit)

    def start(self, chat):
        self.send(chat,"Привет! 👋\n\nЯ помогу записывать дела, не забывать о сроках и отмечать выполненное.\n\nА ещё можно скачать задачи в Excel.\n\nДавай начнём!",menu=True)

    def create(self, owner, chat):
        self.db.put_state(owner,{"stage":"kind","draft":{"reminders":[],"notes":[]}})
        self.send(chat,"Это по работе или для себя?",buttons([("💼 Работа","new:work"),("🏠 Личное","new:personal")]))

    def save_draft(self, owner, chat, state):
        draft=state["draft"]
        now=self.clock()
        task={"id":make_id(),"kind":draft["kind"],"title":draft["title"],
              "deadline":draft.get("deadline"),"reminders":draft["reminders"],
              "notes":[],"priority":draft["priority"],"status":"not_started",
              "created":now,"updated":now,"completed":None,"deleted":False}
        self.db.put_task(owner,task)
        for rem in task["reminders"]:
            self.db.put_reminder({"at":rem["at"],"id":rem["id"],"owner":owner,"task_id":task["id"]})
        self.db.put_state(owner,{})
        self.send(chat,"✅ Задача сохранена!")
        self.view(chat,task)

    def list_view(self, owner, chat, kind="active", page=0, edit=None):
        all_tasks=[t for t in self.db.list_tasks(owner) if not t.get("deleted")]
        filtered=[t for t in all_tasks if kind=="all" or (t["status"]=="done")==(kind=="done")]
        filtered.sort(key=lambda t:( {"red":0,"yellow":1,"green":2}[t["priority"]],
                                   t.get("deadline") or 2**40,t.get("created",0)))
        total=len(filtered)
        page=max(0,min(page,max(0,(total-1)//8)))
        chunk=filtered[page*8:(page+1)*8]
        row_buttons=[[ (f"{'💼' if t['kind']=='work' else '🏠'} {PRIO[t['priority']].split()[0]} {t['title'][:36]}",f"view:{t['id']}") ] for t in chunk]
        filters=[("Активные","list:active:0"),("Готовые","list:done:0"),("Все","list:all:0")]
        row_buttons.append(filters)
        pages=[]
        if page>0: pages.append(("◀ Назад",f"list:{kind}:{page-1}"))
        if (page+1)*8<total: pages.append(("Дальше ▶",f"list:{kind}:{page+1}"))
        if pages:row_buttons.append(pages)
        self.send(chat,f"📋 Мои задачи · {total}\n\n"+("Нажми на нужную задачу." if chunk else "Здесь пока пусто."),
                  buttons(*row_buttons),edit)

    def menu(self, owner, chat, text):
        if text.startswith("/start"):
            self.db.put_state(owner,{})
            self.start(chat)
        elif text in ("➕ Добавить задачу","/add"):
            self.create(owner,chat)
        elif text in ("📋 Мои задачи","/tasks"):
            self.list_view(owner,chat)
        elif text in ("📊 Скачать Excel","/excel"):
            self.tg.document(chat,excel(self.db.list_tasks(owner),os.getenv("BOT_TIMEZONE","Europe/Moscow")))
        elif text=="/cancel":
            self.db.put_state(owner,{})
            self.send(chat,"Отменено. Выбери действие в меню.",menu=True)
        elif text=="/myid":
            self.send(chat,f"Твой ID: {owner}")
        else:
            self.send(chat,"Выбери действие в меню 👇",menu=True)

    def text(self, owner, chat, text):
        # Global commands work even with an unfinished draft.
        # Emoji variation selectors and extra whitespace in menu labels are ignored.
        text = " ".join(str(text).strip().split())
        command = text.split(" ", 1)[0].split("@", 1)[0].lower() if text.startswith("/") else ""
        if command in ("/start", "/add", "/tasks", "/excel", "/cancel", "/myid"):
            self.menu(owner, chat, command)
            return
        normalized = text.replace("\ufe0f", "")
        if normalized in ("➕ Добавить задачу", "Добавить задачу"):
            self.menu(owner,chat,"/add");return
        if normalized in ("📋 Мои задачи", "Мои задачи"):
            self.menu(owner,chat,"/tasks");return
        if normalized in ("📊 Скачать Excel", "Скачать Excel"):
            self.menu(owner,chat,"/excel");return
        state=self.db.get_state(owner)
        stage=state.get("stage")
        if not stage:
            self.menu(owner,chat,text);return
        if stage=="kind":
            self.send(chat,"Это по работе или для себя?",buttons([("💼 Работа","new:work"),("🏠 Личное","new:personal")]))
            return
        if stage=="more":
            self.send(chat,"Ещё одно напоминание?",buttons([("➕ Ещё","rem:more"),("✅ Готово","rem:done")]))
            return
        if stage=="priority":
            self.send(chat,"Насколько важно?",buttons([("🔴 Срочно","priority:red"),("🟡 Важно","priority:yellow"),("🟢 Не горит","priority:green")]))
            return
        if stage=="title":
            if not text.strip(): self.send(chat,"Напиши, что нужно сделать.");return
            state["draft"]["title"]=text.strip()[:240]
            state["stage"]="deadline"
            self.db.put_state(owner,state)
            self.send(chat,"Какой срок?\nНапример: 6.11 17:00",buttons([("Без срока","date:none")]))
        elif stage=="deadline":
            try: date=parse(text)
            except ValueError as e: self.send(chat,f"{e}. Попробуй ещё раз.");return
            state["draft"]["deadline"]=date;state["stage"]="reminder"
            self.db.put_state(owner,state)
            self.send(chat,"🔔 Когда напомнить?\nНапример: 5.11 11:00")
        elif stage in ("reminder","edit_reminder"):
            try: date=parse(text)
            except ValueError as e: self.send(chat,f"{e}. Попробуй ещё раз.");return
            if stage=="reminder":
                draft=state["draft"]
                if draft.get("deadline") and date>draft["deadline"]:
                    self.send(chat,"Напоминание должно быть не позже срока. Укажи другое время.");return
                if any(x["at"]==date for x in draft["reminders"]):
                    self.send(chat,"Это время уже добавлено. Укажи другое.");return
                draft["reminders"].append({"id":make_id(),"at":date})
                state["stage"]="more";self.db.put_state(owner,state)
                self.send(chat,f"🔔 {fmt(date)}\nЕщё напоминание?",buttons([("➕ Ещё","rem:more"),("✅ Готово","rem:done")]))
            else:
                t=self.db.get_task(owner,state["id"])
                if not t or t.get("deleted"):
                    self.db.put_state(owner,{});self.send(chat,"Задача не найдена.");return
                if t.get("deadline") and date>t["deadline"]:
                    self.send(chat,"Напоминание должно быть не позже срока.");return
                if any(x["at"]==date for x in t["reminders"]):
                    self.send(chat,"Это время уже есть в задаче.");return
                rem={"id":make_id(),"at":date}
                t["reminders"].append(rem);t["updated"]=self.clock()
                self.db.put_task(owner,t)
                self.db.put_reminder({"at":date,"id":rem["id"],"owner":owner,"task_id":t["id"]})
                self.db.put_state(owner,{})
                self.view(chat,t)
        elif stage=="edit_info":
            t=self.db.get_task(owner,state["id"])
            if not t or t.get("deleted"):self.db.put_state(owner,{});return
            t["notes"].append({"text":text.strip()[:2500],"at":self.clock()})
            t["updated"]=self.clock()
            self.db.put_task(owner,t);self.db.put_state(owner,{})
            self.send(chat,"Добавлено ✅")
            self.view(chat,t)
        elif stage=="edit_deadline":
            t=self.db.get_task(owner,state["id"])
            if not t or t.get("deleted"):self.db.put_state(owner,{});return
            try:date=parse(text)
            except ValueError as e:self.send(chat,str(e));return
            t["deadline"]=date;t["updated"]=self.clock()
            # Never silently keep a reminder that will fire after the new deadline.
            for rem in list(t["reminders"]):
                if rem["at"]>date:
                    self.db.delete_reminder({"at":rem["at"],"id":rem["id"]})
                    t["reminders"].remove(rem)
            self.db.put_task(owner,t);self.db.put_state(owner,{})
            self.view(chat,t)
            if not t["reminders"]:
                self.send(chat,"У этой задачи теперь нет напоминаний. Добавь хотя бы одно через «Изменить параметры».")
        else:
            # Unknown/old stage: never leave the user stuck with no response.
            self.db.put_state(owner,{})
            self.send(chat,"Продолжим с главного меню 👇",menu=True)

    def callback(self,owner,chat,data,edit=None):
        parts=data.split(":")
        state=self.db.get_state(owner)
        if data.startswith("new:") and state.get("stage")=="kind":
            state["draft"]["kind"]=parts[1];state["stage"]="title"
            self.db.put_state(owner,state)
            self.send(chat,"Что нужно сделать?",edit=edit);return
        if data=="date:none" and state.get("stage")=="deadline":
            state["draft"]["deadline"]=None;state["stage"]="reminder"
            self.db.put_state(owner,state)
            self.send(chat,"🔔 Когда напомнить?\nНапример: сегодня в 18:00",buttons([("Без напоминания","rem:skip")]),edit);return
        if data=="rem:skip" and state.get("stage")=="reminder" and not state["draft"].get("deadline"):
            state["stage"]="priority";self.db.put_state(owner,state)
            self.send(chat,"Насколько важно?",buttons([("🔴 Срочно","priority:red"),("🟡 Важно","priority:yellow"),("🟢 Не горит","priority:green")]),edit);return
        if data=="rem:more" and state.get("stage")=="more":
            state["stage"]="reminder";self.db.put_state(owner,state)
            self.send(chat,"Когда напомнить ещё?\nНапример: 5.11 11:00",edit=edit);return
        if data=="rem:done" and state.get("stage")=="more":
            state["stage"]="priority";self.db.put_state(owner,state)
            self.send(chat,"Насколько важно?",buttons([("🔴 Срочно","priority:red"),("🟡 Важно","priority:yellow"),("🟢 Не горит","priority:green")]),edit);return
        if data.startswith("priority:") and state.get("stage")=="priority":
            state["draft"]["priority"]=parts[1];self.save_draft(owner,chat,state);return
        if data in ("menu:add", "menu:tasks", "menu:excel"):
            self.menu(owner,chat,{"menu:add":"/add","menu:tasks":"/tasks","menu:excel":"/excel"}[data]);return
        if parts[0]=="list":
            self.list_view(owner,chat,parts[1],int(parts[2]),edit);return
        if parts[0]=="view":
            t=self.db.get_task(owner,parts[1]);
            if t and not t.get("deleted"):self.view(chat,t,edit)
            return
        if parts[0]=="done":
            self.set_status(owner,chat,parts[1],"done",edit);return
        if parts[0]=="edit":
            t=self.db.get_task(owner,parts[1]);
            if not t or t.get("deleted"):return
            self.send(chat,"Что хочешь изменить?",buttons(
                [("📝 Добавить информацию",f"info:{t['id']}")],
                [("⚙️ Изменить параметры",f"params:{t['id']}")],
                [("🔄 Изменить статус",f"statuses:{t['id']}")],
                [("🗑 Удалить",f"delete:{t['id']}")],
                [("↩️ Назад",f"view:{t['id']}")]),edit);return
        if parts[0]=="info":
            self.db.put_state(owner,{"stage":"edit_info","id":parts[1]})
            self.send(chat,"Напиши, что добавить к задаче:",edit=edit);return
        if parts[0]=="params":
            t=self.db.get_task(owner,parts[1]);
            if not t or t.get("deleted"):return
            tid=t["id"]
            self.send(chat,"⚙️ Параметры задачи",buttons(
                [(f"🏷 {KIND[t['kind']]}",f"pk:{tid}")],
                [(f"🚦 {PRIO[t['priority']]}",f"pp:{tid}")],
                [(f"📅 Срок: {fmt(t.get('deadline'))}",f"pd:{tid}")],
                [("🔔 Напоминания",f"pr:{tid}")],
                [("↩️ Назад",f"view:{tid}")]),edit);return
        if parts[0]=="pk":
            self.send(chat,"Раздел:",buttons([("💼 Работа",f"kind:{parts[1]}:work"),("🏠 Личное",f"kind:{parts[1]}:personal")]),edit);return
        if parts[0]=="pp":
            self.send(chat,"Насколько важно?",buttons([("🔴 Срочно",f"prio:{parts[1]}:red"),
                ("🟡 Важно",f"prio:{parts[1]}:yellow"),("🟢 Не горит",f"prio:{parts[1]}:green")]),edit);return
        if parts[0] in ("kind","prio"):
            t=self.db.get_task(owner,parts[1]);
            if not t or t.get("deleted"):return
            t["kind" if parts[0]=="kind" else "priority"]=parts[2]
            t["updated"]=self.clock();self.db.put_task(owner,t)
            self.view(chat,t,edit);return
        if parts[0]=="pd":
            self.send(chat,"Какой срок?",buttons([("Без срока",f"nd:{parts[1]}")]),edit)
            self.db.put_state(owner,{"stage":"edit_deadline","id":parts[1]});return
        if parts[0]=="nd":
            t=self.db.get_task(owner,parts[1]);
            if not t or t.get("deleted"):return
            t["deadline"]=None;t["updated"]=self.clock()
            self.db.put_task(owner,t);self.db.put_state(owner,{})
            self.view(chat,t,edit);return
        if parts[0]=="pr":
            t=self.db.get_task(owner,parts[1]);
            if not t or t.get("deleted"):return
            rows=[[ (f"🗑 {fmt(x['at'])}",f"dr:{t['id']}:{x['id']}") ] for x in sorted(t["reminders"],key=lambda x:x["at"])]
            rows.append([("➕ Добавить",f"ar:{t['id']}")])
            rows.append([("↩️ Назад",f"params:{t['id']}")])
            self.send(chat,"🔔 Напоминания\nНажми на дату, чтобы удалить, или добавь новое:",buttons(*rows),edit);return
        if parts[0]=="ar":
            self.db.put_state(owner,{"stage":"edit_reminder","id":parts[1]})
            self.send(chat,"Когда напомнить?\nНапример: завтра в 15:00",edit=edit);return
        if parts[0]=="dr":
            t=self.db.get_task(owner,parts[1]);
            if not t or t.get("deleted"):return
            for reminder in list(t["reminders"]):
                if reminder["id"]==parts[2]:
                    self.db.delete_reminder({"at":reminder["at"],"id":reminder["id"]})
                    t["reminders"].remove(reminder)
            t["updated"]=self.clock();self.db.put_task(owner,t)
            self.callback(owner,chat,f"pr:{parts[1]}",edit);return
        if parts[0]=="later":
            t=self.db.get_task(owner,parts[1]);
            if not t or t.get("deleted") or t["status"]=="done":return
            self.send(chat,"Когда напомнить ещё раз?",buttons(
                [("Через 10 минут",f"snooze:{t['id']}:10")],
                [("Через час",f"snooze:{t['id']}:60")],
                [("Завтра",f"snooze:{t['id']}:1440")]),edit);return
        if parts[0]=="snooze":
            t=self.db.get_task(owner,parts[1]);
            if not t or t.get("deleted") or t["status"]=="done":return
            at=self.clock()+60*int(parts[2])
            if t.get("deadline") and at>t["deadline"]:
                self.send(chat,"Это позже установленного срока. Открой задачу и измени срок или напоминание.",edit=edit);return
            rem={"id":make_id(),"at":at}
            t["reminders"].append(rem);t["updated"]=self.clock()
            self.db.put_task(owner,t)
            self.db.put_reminder({"at":at,"id":rem["id"],"owner":owner,"task_id":t["id"]})
            self.send(chat,"🔔 Напомню: "+fmt(at),edit=edit);return
        if parts[0]=="statuses":
            self.send(chat,"Какой статус?",buttons([("Не начато",f"st:{parts[1]}:not_started")],
                [("В работе",f"st:{parts[1]}:in_progress")],[("Сделано",f"st:{parts[1]}:done")]),edit);return
        if parts[0]=="st":
            self.set_status(owner,chat,parts[1],parts[2],edit);return
        if parts[0]=="delete":
            self.send(chat,"Удалить задачу?",buttons([("🗑 Удалить",f"del:{parts[1]}")],[("Отмена",f"view:{parts[1]}")]),edit);return
        if parts[0]=="del":
            t=self.db.get_task(owner,parts[1]);
            if not t:return
            t["deleted"]=True;t["updated"]=self.clock()
            for rem in t["reminders"]:self.db.delete_reminder({"at":rem["at"],"id":rem["id"]})
            self.db.put_task(owner,t)
            self.send(chat,"Задача удалена.",edit=edit);return
        self.send(chat,"Действие устарело. Открой «Мои задачи». ",edit=edit)

    def set_status(self,owner,chat,task_id,status,edit=None):
        t=self.db.get_task(owner,task_id)
        if not t or t.get("deleted"):return
        t["status"]=status
        t["completed"]=self.clock() if status=="done" else None
        t["updated"]=self.clock()
        self.db.put_task(owner,t)
        if status=="done":
            for rem in t["reminders"]:
                self.db.delete_reminder({"at":rem["at"],"id":rem["id"]})
        self.view(chat,t,edit)

    def update(self, event, platform="tg"):
        if "callback_query" in event:
            q=event["callback_query"]
            owner=f"{platform}:{q['from']['id']}"
            msg=q.get("message",{})
            chat=msg.get("chat",{}).get("id",owner)
            if msg.get("chat",{}).get("type","private")!="private":return
            if not self.allowed(owner,chat):return
            self.tg.ack(q["id"])
            self.callback(owner,chat,q.get("data",""),msg.get("message_id"))
        elif "message" in event:
            q=event["message"]
            if q.get("chat",{}).get("type")!="private":return
            owner=f"{platform}:{q['from']['id']}";chat=int(q["chat"]["id"])
            if not self.allowed(owner,chat):return
            if q.get("text"):self.text(owner,chat,q["text"])

    def allowed(self,owner,chat):
        allow=os.getenv("ALLOWED_USER_ID","").strip()
        if allow and str(owner).split(":")[-1]!=allow:
            self.send(chat,"Это личная тестовая версия бота.")
            return False
        return True

    def tick(self, platform="tg"):
        now=self.clock()
        for e in self.db.due_reminders(now,limit=100):
            if isinstance(e["owner"],str) and not e["owner"].startswith(platform+":"):
                continue
            t=self.db.get_task(e["owner"],e["task_id"])
            active=(t and not t.get("deleted") and t["status"]!="done"
                    and any(x["id"]==e["id"] and x["at"]==e["at"] for x in t["reminders"]))
            if not active:
                self.db.delete_reminder(e)
                continue
            message=f"🔔 {t['title']}\n{PRIO[t['priority']]}\n📅 Срок: {fmt(t.get('deadline'))}"
            self.tg.send(str(e["owner"]).split(":",1)[-1],message,buttons([("✅ Сделано",f"done:{t['id']}"),
                                                      ("⏰ Позже",f"later:{t['id']}")],
                                                     [("Открыть",f"view:{t['id']}")]))
            self.db.delete_reminder(e)
