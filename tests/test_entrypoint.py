import main


class Fake:
    def __init__(self):self.calls=[]
    def tick(self):self.calls.append("tick")
    def update(self,e):self.calls.append(("update",e))


def test_yandex_timer_event():
    fake=Fake();main._bot=fake
    event={"messages":[{"event_metadata":{"event_type":"yandex.cloud.events.serverless.triggers.TimerMessage"},
                        "details":{"payload":"reminders"}}]}
    assert main.handler(event,None)=={"statusCode":200,"body":"OK"}
    assert fake.calls==["tick"]


def test_telegram_update():
    fake=Fake();main._bot=fake
    event={"message":{"chat":{"id":1},"from":{"id":1},"text":"/start"}}
    main.handler(event,None)
    assert fake.calls==[("update",event)]
