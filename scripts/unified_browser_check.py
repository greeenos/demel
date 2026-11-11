import os
"""Synthetic unified-app flows against the isolated local database only."""
from pathlib import Path
import sys
from datetime import date,datetime
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright,expect
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from backend import db
from backend.models import Entry

db.DATA_DIR=root/'data-browser';db.init()
day=date.today().isoformat()
for i in range(35):
 db.save(Entry(id='unified-workout-'+str(i).zfill(2),kind='workout',day=day,data={'name':'Synthetic '+str(i),'minutes':30,'sets':[{'name':'Test press','weight':20,'reps':10,'done':True,'seconds':30,'rpe':8,'failure':True}]}))
db.save(Entry(id='unified-exercise',kind='exercise',day=day,data={'name':'Test press','muscle':'Chest','equipment':'Dumbbell','instructions':'Synthetic instructions'}))
db.put('hydration_settings',{'enabled':True,'sip_ml':50,'start':0,'end':1440,'days':list(range(7))})
db.put('hydration_schedule',{'day':day,'next_at':datetime.now(ZoneInfo('Europe/Prague')).timestamp()-60})
password = os.environ['VITAL_TEST_PASSWORD']  # password of the isolated test backend
errors=[]
with sync_playwright() as p:
 b=p.chromium.launch();page=b.new_page(viewport={'width':390,'height':844},is_mobile=True,has_touch=True);page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(os.environ.get('VITAL_TEST_URL','http://127.0.0.1:8208'));page.locator('[name=password]').fill(password);page.locator('#login-form button').click()
 expect(page.locator('.sip-reminder')).to_be_visible();page.locator('[data-action="hydrate:snooze"]').click();expect(page.locator('.sip-reminder')).to_have_count(0)
 page.locator('[data-action="hydration-settings"]').click();page.locator('[name=sip_ml]').fill('75');page.locator('#hydration-form button[type=submit]').click();expect(page.locator('[data-action="water:75"]')).to_be_visible()
 page.locator('.bottom-nav [data-action="nav:workouts"]').click();page.locator('[data-action="training-history"]').click();expect(page.locator('.history-workout')).to_have_count(30)
 page.locator('[data-action="training-page:30"]').click();expect(page.locator('.history-workout')).not_to_have_count(0)
 page.locator('[data-action="training-page:0"]').click();page.locator('.history-workout').first.click();expect(page.locator('.set-context')).to_contain_text('30 s')
 page.locator('[data-action="rest:60"]').click();expect(page.locator('#rest-label')).to_contain_text('Rest ')
 page.locator('[data-action="choose-exercise"]').click();page.locator('#exercise-search').fill('Test press');page.locator('[data-action="pick-exercise:unified-exercise"]').click();expect(page.locator('.set-row')).to_have_count(2)
 page.locator('dialog [data-action="close"]').click();page.locator('[data-action="exercise-library"]').click();page.locator('#exercise-search').fill('Test press');expect(page.locator('.exercise-item:visible')).to_have_count(1);page.locator('.exercise-item summary').click();expect(page.locator('.exercise-item p')).to_contain_text('Synthetic instructions');page.locator('dialog [data-action="close"]').click()
 page.locator('.bottom-nav [data-action="nav:coach"]').click();page.locator('#chat-message').fill('Synthetic question');page.locator('.send-btn').click();expect(page.locator('#toast')).to_contain_text('OpenRouter API key');expect(page.locator('#chat-message')).to_have_value('Synthetic question')
 page.locator('#chat-message').blur();page.screenshot(path=str(root/'review/forma-chat-mobile.png'))
 for width in (320,390,430,768,1280):
  page.set_viewport_size({'width':width,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
  box=page.locator('.send-btn').bounding_box();assert box and box['y']+box['height']<844,width
 assert not errors,errors
 print({'status':'passed','flows':['sip snooze','schedule edit','history pagination','timed series','rest timer','exercise picker','exercise library','chat retry draft','responsive composer'],'errors':errors})
 b.close()
