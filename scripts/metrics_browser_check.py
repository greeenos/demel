import os
"""Synthetic fixtures only, against the dedicated localhost browser-test database."""
import sys
from pathlib import Path
from datetime import date, timedelta
from playwright.sync_api import sync_playwright, expect

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from backend import db,google_data
from backend.models import Entry,Profile
db.DATA_DIR=root/'data-browser'
db.init()
today=date.today();day=today.isoformat();stop=(today+timedelta(days=1)).isoformat()
p=Profile(name='Test',birthdate=date(1986,11,10),sex='male',height_cm=180)
db.put('profile',p.model_dump(mode='json'))
point={'dailyHeartRateVariability':{'date':{'year':today.year,'month':today.month,'day':today.day},'averageHeartRateVariabilityMilliseconds':55,'entropy':2.5,'nonRemHeartRateBeatsPerMinute':'57'}}
google_data.store('daily-heart-rate-variability',[point],day,stop,'Europe/Prague')
db.save(Entry(id='test-vo2',kind='vitals',day=today,data={'vo2max':39.7,'weight':81}))
db.save(Entry(id=f'manual-nutrition_day-{day}',kind='nutrition_day',day=today,data={'complete':False}))
password = os.environ['VITAL_TEST_PASSWORD']  # password of the isolated test backend
errors=[]
with sync_playwright() as p:
 b=p.chromium.launch(headless=True)
 context=b.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,locale='cs-CZ')
 page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(os.environ.get('VITAL_TEST_URL','http://127.0.0.1:8208'))
 page.locator('#login-form [name=password]').fill(password)
 page.locator('#login-form button[type=submit]').click()
 page.locator('.bottom-nav [data-action="nav:health"]').click()
 page.locator('[data-action="tab:metrics"]').click()
 expect(page.locator('.metric-tile')).to_have_count(42)
 page.locator('#metric-search').fill('HRV')
 expect(page.locator('.metric-tile:visible')).to_have_count(2)
 page.locator('#metric-search').fill('')
 page.locator('[data-action^="metric:daily-heart-rate-variability:"]').click()
 expect(page.locator('.metric-table tbody tr')).to_have_count(3)
 page.locator('#metric-field').select_option('entropy')
 expect(page.locator('#metric-field')).to_have_value('entropy')
 page.locator('dialog [data-action="close"]').click()
 page.screenshot(path=str(root/'review/mobile-all-metrics.png'),full_page=True)
 page.locator('[data-action="tab:age"]').click()
 expect(page.locator('.wearable-age .age-result>strong')).to_have_text('34 yrs')
 expect(page.locator('.wearable-age')).to_contain_text('Fitness age')
 page.screenshot(path=str(root/'review/mobile-lifestyle.png'),full_page=True)
 for width in (320,390,430,1280):
  page.set_viewport_size({'width':width,'height':900})
  assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),width
 page.set_viewport_size({'width':390,'height':844})
 page.locator('.bottom-nav [data-action="nav:nutrition"]').click()
 page.locator('[data-action="nutrition-complete"]').click()
 expect(page.locator('[data-action="nutrition-complete"]')).to_contain_text('complete ✓')
 page.locator('.avatar').click()
 page.locator('[data-action="recommended-model"]').click()
 expect(page.locator('#ai-form [name=ai_model]')).to_have_value('anthropic/claude-haiku-5.5')
 assert not errors,errors
 print({'status':'passed','catalog_types':42,'flows':['metric search','all numeric values','metric history selection','wearable fitness age','nutrition completeness','recommended model'],'errors':errors})
 b.close()
