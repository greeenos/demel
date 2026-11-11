from datetime import date, datetime
from zoneinfo import ZoneInfo
from backend import db, hydration
from backend.models import Entry, Profile


def test_sip_schedule_shared_log_and_snooze(logged):
    p=Profile(water_goal=2000)
    now=datetime(2026,11,10,10,0,tzinfo=ZoneInfo('Europe/Prague'))
    s=hydration.status(p,now)
    assert not s['due'] and s['next_at']>=now.timestamp()+300
    db.put('hydration_schedule',{'day':'2026-11-10','next_at':now.timestamp()-1})
    assert hydration.status(p,now)['due']
    s=hydration.postpone(p,'snooze',now)
    assert s['next_at']==now.timestamp()+300 and not s['due']
    db.save(Entry(kind='water',day=now.date(),data={'ml':2000}))
    assert hydration.status(p,now)['total']==2000
    assert hydration.status(p,now)['next_at'] is None
    assert logged.put('/api/hydration',json={'start':1200,'end':600}).status_code==422
    assert logged.put('/api/hydration',json={'days':[7]}).status_code==422
    assert logged.post('/api/hydration/oops').status_code==400


def test_training_history_pages_and_keeps_sets(logged):
    db.save(Entry(id='w1',kind='workout',day=date(2024,1,1),data={'name':'Test','minutes':10,'sets':[
        {'name':'Test press','reps':8,'weight':20,'done':True,'failure':True,'phase':'work','seconds':30,'rpe':8}]}))
    r=logged.get('/api/training/history?limit=1').json()
    assert r['total']==1 and r['entries'][0]['id']=='w1'
    assert r['entries'][0]['data']['sets'][0]['seconds']==30 and r['entries'][0]['data']['sets'][0]['failure']
    assert logged.get('/api/training/history?offset=1').json()['entries']==[]
