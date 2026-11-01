"""Offline adapter and channel routing tests, no real cloud credentials required."""
import json
from io import BytesIO
from openpyxl import load_workbook
import pytest
from bot import Bot
from storage import MemoryStore
from platform_events import max_normalize, vk_normalize, body_from_http
from messengers import MAX, VK
import channel_entry

class FakeChannel:
    def __init__(self): self.sent=[]; self.files=[]; self.acks=[]
    def send(self,chat,text,keyboard=None,menu=False,edit=None):
        self.sent.append((chat,text,keyboard,menu,edit))
    def document(self,chat,content,name='Мои_дела.xlsx'):
        self.files.append((chat,content,name))
    def ack(self,x): self.acks.append(x)


def tg_update(uid,text):
    return {'message':{'chat':{'id':uid,'type':'private'},'from':{'id':uid},'text':text}}


def test_vk_event_normalization():
    event={'type':'message_new','object':{'message':{'from_id':345,'peer_id':345,'text':'/start'}}}
    assert vk_normalize(event)==tg_update(345,'/start')
    event['object']['message']['peer_id']=2000000001
    assert vk_normalize(event) is None
    click={'type':'message_event','object':{'user_id':345,'peer_id':345,'event_id':'event1',
          'payload':json.dumps({'cmd':'menu:tasks'})}}
    assert vk_normalize(click)['callback_query']['data']=='menu:tasks'
    assert vk_normalize(click)['callback_query']['id']==('event1',345,345)


def test_max_event_normalization():
    msg={'sender':{'user_id':445},'recipient':{'chat_type':'dialog'},'body':{'text':'/start','mid':'abc'}}
    assert max_normalize({'update_type':'message_created','message':msg})==tg_update(445,'/start')
    msg['recipient']['chat_type']='chat'
    assert max_normalize({'update_type':'message_created','message':msg}) is None
    msg['recipient']['chat_type']='dialog'
    click={'update_type':'message_callback','callback':{'callback_id':'q1',
         'payload':'menu:excel','user':{'user_id':445}},'message':msg}
    assert max_normalize(click)['callback_query']['data']=='menu:excel'
    assert max_normalize(click)['callback_query']['message']['message_id']=='abc'
    assert max_normalize({'update_type':'bot_started','user':{'user_id':445}})==tg_update(445,'/start')


def test_channel_separation_with_same_numeric_id():
    db=MemoryStore()
    for code in ('tg','vk','max'):
        channel=FakeChannel(); bot=Bot(db,channel)
        bot.update(tg_update(10,'/start'),platform=code)
        bot.update(tg_update(10,'/add'),platform=code)
        owner=code+':10'
        assert db.get_state(owner)['stage']=='kind'
        bot.update({'callback_query':{'id':'x', 'from':{'id':10},'data':'new:work',
                    'message':{'chat':{'id':10,'type':'private'}}}},platform=code)
        bot.update(tg_update(10,'Уточнить бюджет'),platform=code)
        assert db.get_state(owner)['stage']=='deadline'
    assert len(db.states)==3
    assert all(db.get_state(p+':10')['draft']['title']=='Уточнить бюджет' for p in ('tg','vk','max'))
    assert not db.get_state('tg:10').get('draft',{}).get('reminders')


def test_scheduler_filters_reminders_by_platform():
    db=MemoryStore(); now=2000000000
    channel_a,channel_b,channel_c=FakeChannel(),FakeChannel(),FakeChannel()
    for platform in ('tg','vk','max'):
        owner=platform+':17'
        task={'id':'test','kind':'work','title':'Дело','deadline':now+200,
              'priority':'red','status':'not_started','reminders':[{'at':now,'id':platform}],
              'notes':[],'created':now-100,'updated':now-100,'completed':None,'deleted':False}
        db.put_task(owner,task)
        db.put_reminder({'at':now,'id':platform,'owner':owner,'task_id':'test'})
    for platform,channel in [('tg',channel_a),('vk',channel_b),('max',channel_c)]:
        Bot(db,channel,clock=lambda:now).tick(platform=platform)
        assert len(channel.sent)==1
        assert channel.sent[0][0]=='17'
    assert len(db.reminders)==0


def test_vk_keyboard_and_max_payload_shape():
    v=VK(token='fake')
    got=[]
    v.api=lambda m,**kw:got.append((m,kw)) or 1
    v.send(9,'Привет',menu=True)
    obj=json.loads(got[-1][1]['keyboard'])
    assert obj['inline'] is True
    assert json.loads(obj['buttons'][0][0]['action']['payload'])['cmd']=='menu:add'
    m=MAX(token='fake')
    m.api=lambda method,path,data: got.append((method,path,data)) or {}
    m.send(9,'Привет',menu=True)
    assert got[-1][2]['attachments'][0]['payload']['buttons'][0][0]['payload']=='menu:add'


def test_vk_secret_and_max_secret_rejected_without_contacting_db(monkeypatch):
    monkeypatch.setenv('VK_CALLBACK_SECRET','secret-one')
    monkeypatch.setenv('VK_GROUP_ID','123')
    monkeypatch.setenv('MAX_WEBHOOK_SECRET','secret-two')
    vk_ev={'body':json.dumps({'type':'message_new','secret':'wrong','group_id':123})}
    max_ev={'headers':{'X-Max-Bot-Api-Secret':'wrong'},'body':json.dumps({'update_type':'bot_started'})}
    assert channel_entry.vk_handler(vk_ev,None)['statusCode']==403
    assert channel_entry.max_handler(max_ev,None)['statusCode']==403


def test_export_both_sheets_across_channels():
    db=MemoryStore(); f=FakeChannel(); b=Bot(db,f)
    for kind,owner in [('work','vk:10'),('personal','max:10')]:
        db.put_task(owner,{'id':'tid','kind':kind,'title':'Задача','deadline':None,
              'priority':'green','status':'not_started','notes':[],'reminders':[],
              'created':10,'completed':None,'deleted':False})
        b.menu(owner,10,'/excel')
    assert len(f.files)==2
    assert load_workbook(BytesIO(f.files[0][1])).sheetnames==['Работа','Личное']
    assert load_workbook(BytesIO(f.files[1][1])).sheetnames==['Работа','Личное']
    assert load_workbook(BytesIO(f.files[0][1]))['Личное'].max_row==1
    assert load_workbook(BytesIO(f.files[1][1]))['Работа'].max_row==1
