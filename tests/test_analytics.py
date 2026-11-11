from datetime import date,timedelta
import json
import pytest

from backend.analytics import analyze,fitness_age
from backend.models import Profile
from backend import db,google_data

TODAY=date.today()


def row(kind,day,data,source='manual'):
    return {'kind':kind,'day':day.isoformat(),'data':data,'source':source}


def test_fitness_age_reproduces_reference_medians_and_does_not_extrapolate():
    assert fitness_age(39.7,'male')['age']==34
    assert fitness_age(25.7,'female')['age']==44
    assert fitness_age(80,'male')['age'] is None
    assert fitness_age(80,'male')['label']=='≤29'
    assert fitness_age(10,'female')['label']=='≥80'
    assert fitness_age(40,'unspecified') is None


def test_lifestyle_never_fabricates_missing_data_or_age():
    a=analyze([],[],Profile(),TODAY.isoformat())
    assert a['fitness_age'] is None and a['index'] is None
    assert a['sleep']['debt_hours'] is None
    assert a['activity']['equivalent_minutes'] is None
    assert a['nutrition']['protein'] is None
    assert a['body']['bmi'] is None
    assert len(a['fitness_requirements'])==3


def test_fitness_age_requires_both_profile_and_recent_vo2_and_excludes_future():
    p=Profile(birthdate=date(1986,1,1),sex='male')
    entries=[row('vitals',TODAY,{'vo2max':39.7}),row('vitals',TODAY+timedelta(days=1),{'vo2max':10})]
    a=analyze(entries,[],p,TODAY.isoformat())
    assert a['fitness_age']['age']==34 and a['fitness_age']['days']==1
    assert analyze(entries,[],Profile(sex='unspecified'),TODAY.isoformat())['fitness_age'] is None


def test_sleep_circular_regularness_does_not_treat_midnight_as_24h_gap():
    p=Profile()
    entries=[row('sleep',TODAY-timedelta(days=i),{'minutes':420,'in_bed_minutes':450,
              'bedtime':f'2026-10-01T{time}:00','stages':[]}) for i,time in enumerate(['23:55','00:05','00:00'])]
    a=analyze(entries,[],p,TODAY.isoformat())
    assert a['sleep']['regularity_minutes']<=5
    assert a['sleep']['debt_hours']==3
    assert a['sleep']['days']==3
    assert a['sleep']['efficiency']==pytest.approx(93.3)


def test_incomplete_food_log_is_not_treated_as_poor_nutrition():
    p=Profile()
    entries=[row('meal',TODAY,{'calories':500,'protein':40,'carbs':50,'fat':10,'fiber':10}),
             row('vitals',TODAY,{'weight':80})]
    assert analyze(entries,[],p,TODAY.isoformat())['nutrition']['complete_days']==0
    entries.append(row('nutrition_day',TODAY,{'complete':True}))
    a=analyze(entries,[],p,TODAY.isoformat())
    assert a['nutrition']['protein_per_kg']==.5
    assert a['nutrition']['complete_days']==1


def test_weight_fat_and_height_combine_only_when_measurement_dates_are_close():
    p=Profile(height_cm=180)
    entries=[row('vitals',TODAY,{'weight':81})]
    measure={'type':'body-fat','day':TODAY.isoformat(),'fields':[{'field':'bodyFatPercentageAvg','value':20}]}
    a=analyze(entries,[measure],p,TODAY.isoformat())
    assert a['body']['bmi']==25 and a['body']['lean_kg']==64.8
    measure['day']=(TODAY-timedelta(days=4)).isoformat()
    assert analyze(entries,[measure],p,TODAY.isoformat())['body']['lean_kg'] is None


def test_google_archive_keeps_original_points_and_numeric_summary(logged):
    day=TODAY.isoformat();stop=(TODAY+timedelta(days=1)).isoformat()
    point={'dailyHeartRateVariability':{'date':{'year':TODAY.year,'month':TODAY.month,'day':TODAY.day},
           'averageHeartRateVariabilityMilliseconds':51.5,'entropy':2.1,'nonRemHeartRateBeatsPerMinute':'55'}}
    assert google_data.store('daily-heart-rate-variability',[point],day,stop,'Europe/Prague')==1
    detail=google_data.details('daily-heart-rate-variability',day)
    assert detail['records']==[point]
    assert len(detail['fields'])==3
    assert next(f for f in detail['fields'] if f['field']=='entropy')['value']==2.1
    google_data.store('daily-heart-rate-variability',[point],day,stop,'Europe/Prague')
    assert google_data.details('daily-heart-rate-variability',day)['count']==1
    assert logged.get('/api/google/data',params={'typ':'daily-heart-rate-variability','day':day}).status_code==200


def test_empty_rollup_does_not_become_observed_zero(logged):
    point={'civilStartTime':{'date':{'year':TODAY.year,'month':TODAY.month,'day':TODAY.day}}}
    assert google_data.store('steps',[point],TODAY.isoformat(),(TODAY+timedelta(days=1)).isoformat(),'Europe/Prague')==0
    assert google_data.summaries()==[]


def test_descriptive_values_keep_flags_and_categories_without_ids():
    values=dict(google_data.attributes({'name':'users/private-id','estimated':True,'cardioFitnessLevel':'GOOD',
                'vo2Max':40,'date':{'year':2026},'sampleTime':{'physicalTime':'2026-11-10T00:00:00Z'}}))
    assert values=={'estimated':'Ano','cardioFitnessLevel':'GOOD'}


def test_activity_equivalent_and_google_food_use_sums_without_double_counting():
    p=Profile()
    fields=[{'field':'activeMinutesRollupByActivityLevel.MODERATE.activeMinutesSum','value':40},
            {'field':'activeMinutesRollupByActivityLevel.VIGOROUS.activeMinutesSum','value':10}]
    rows=[{'type':'active-minutes','day':TODAY.isoformat(),'fields':fields}]
    a=analyze([],rows,p,TODAY.isoformat())
    assert a['activity']['equivalent_minutes']==60 and a['activity']['days']==1
