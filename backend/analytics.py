"""Descriptive wearable analytics. Fitness-equivalent age is not a biological clock."""
import math
import statistics
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .age import chronological_age
from .scores import daily

FRIEND_URL = "https://doi.org/10.1016/j.mayocp.2021.08.020"
# Kaminsky et al. 2022, Table 3: treadmill CPX, RER >= 1.0, median by decade.
FRIEND_MEDIANS = {"male": [46.5,39.7,35.3,29.2,24.6,20.6,17.6],
                  "female": [36.6,28.3,25.7,22.9,19.6,17.2,15.4]}


def fitness_age(vo2, sex):
    if sex not in FRIEND_MEDIANS or not math.isfinite(vo2) or vo2 <= 0:
        return None
    medians = FRIEND_MEDIANS[sex]
    if vo2 >= medians[0]:
        return {"age": None, "label": "≤29", "boundary": "young", "source": FRIEND_URL}
    if vo2 <= medians[-1]:
        return {"age": None, "label": "≥80", "boundary": "old", "source": FRIEND_URL}
    for i in range(6):
        if medians[i] >= vo2 >= medians[i+1]:
            value = 24.5 + i*10 + 10*(medians[i]-vo2)/(medians[i]-medians[i+1])
            return {"age": round(value), "label": str(round(value)), "boundary": None, "source": FRIEND_URL}


def metric(rows, typ, field, day=None):
    for row in reversed(rows):
        if row["type"] == typ and (day is None or row["day"] == day):
            found = next((f for f in row["fields"] if f["field"] == field), None)
            if found:
                return found["value"], row["day"]
    return None, None


def analyze(entries, measurements, profile, on):
    end = date.fromisoformat(on)
    days = daily([e for e in entries if e["day"] <= on])
    week = [(end-timedelta(days=i)).isoformat() for i in range(7)]
    month = [(end-timedelta(days=i)).isoformat() for i in range(30)]
    rows = [r for r in measurements if month[-1] <= r["day"] <= on]
    sleeps = [(d, days[d]["sleep"]) for d in week if days.get(d, {}).get("sleep")]
    month_sleeps = [(d, days[d]["sleep"]) for d in month if days.get(d, {}).get("sleep")]
    goal = profile.sleep_goal*60
    debt = sum(max(0,goal-s["minutes"]) for _,s in sleeps)/60 if sleeps else None
    duration = statistics.mean(s["minutes"] for _,s in sleeps)/60 if sleeps else None
    bedtimes = []
    for _,s in month_sleeps:
        if s.get("bedtime"):
            try:
                dt=datetime.fromisoformat(s["bedtime"].replace("Z","+00:00"))
                if dt.tzinfo:dt=dt.astimezone(ZoneInfo(profile.timezone))
                bedtimes.append((dt.hour*60+dt.minute)*2*math.pi/1440)
            except ValueError:
                pass
    regularity = None
    if len(bedtimes)>=3:
        r=math.hypot(statistics.mean(math.cos(t) for t in bedtimes),statistics.mean(math.sin(t) for t in bedtimes))
        regularity=round(math.sqrt(max(0,-2*math.log(max(r,1e-10))))*1440/(2*math.pi))
    efficiencies=[100*s["minutes"]/s["in_bed_minutes"] for _,s in sleeps if s.get("in_bed_minutes")]
    vo2_samples=[(d,days[d]["vo2max"]) for d in month if days.get(d,{}).get("vo2max") is not None]
    vo2=statistics.median(v for _,v in vo2_samples) if vo2_samples else None
    age=chronological_age(str(profile.birthdate) if profile.birthdate else None,on)
    if age is None:
        age,_=metric(rows,'account-profile','age')
    fit=fitness_age(vo2,profile.sex) if vo2 is not None and age is not None and 20<=age<=89 else None
    if fit:
        fit.update({"vo2max":round(vo2,1),"days":len(vo2_samples),"last_day":vo2_samples[0][0],
                    "chronological":round(age,1),"difference":round(fit["age"]-age,1) if fit["age"] is not None else None,
                    "method":"FRIEND 2022 · fitness equivalent", "note":"A rough comparison of VO₂ max with US reference medians. The conversion to an age is the app's own interpolation, not a validated biological age. A wearable estimate is not a lab CPET."})
    requirements=[]
    if age is None:requirements.append("a date of birth or an age from your Google profile")
    elif age is not None and not 20<=age<=89:requirements.append("an age within the 20–89 reference range")
    if profile.sex not in FRIEND_MEDIANS:requirements.append("sex for the reference table")
    if vo2 is None:requirements.append("VO₂ max from the last 30 days")
    moderate=vigorous=0;active_days=set()
    for row in rows:
        if row["day"] in week and row["type"]=="active-minutes":
            for f in row["fields"]:
                if '.MODERATE.' in f['field']:
                    moderate+=f['value'];active_days.add(row['day'])
                if '.VIGOROUS.' in f['field']:
                    vigorous+=f['value'];active_days.add(row['day'])
    workouts=[e for e in entries if e['kind']=='workout' and e['day'] in week]
    previous=[e for e in entries if e['kind']=='workout' and (end-timedelta(days=13)).isoformat()<=e['day']<(end-timedelta(days=6)).isoformat()]
    volume=sum(e['data']['minutes'] for e in workouts)
    previous_volume=sum(e['data']['minutes'] for e in previous)
    complete={e['day'] for e in entries if e['kind']=='nutrition_day' and e['data']['complete'] and e['day'] in week}
    nutrition=[]
    for d in complete:
        if any(e['kind']=='meal' and e['day']==d for e in entries):
            if days.get(d,{}).get('calories',0)>0:
                nutrition.append(days[d])
            continue
        google_day=next((r for r in rows if r['type']=='nutrition-log' and r['day']==d),None)
        if google_day:
            def nutrient(keys):
                found=next((f for f in google_day['fields'] if f['field'] in keys),None)
                return found['sum'] if found else None
            calories=nutrient(['energy.kcalSum','energy.kcal'])
            protein=nutrient(['nutrients.PROTEIN.quantity.grams','nutrients.PROTEIN.quantity.gramsSum'])
            fiber=nutrient(['nutrients.DIETARY_FIBER.quantity.grams','nutrients.DIETARY_FIBER.quantity.gramsSum'])
            if calories and protein is not None and fiber is not None:
                nutrition.append({'calories':calories,'protein':protein,'fiber':fiber})
    weight=next(((days[d]['weight'],d) for d in month if days.get(d,{}).get('weight') is not None),(None,None))
    height=profile.height_cm
    if not height:
        value,_=metric(rows,'height','heightMillimeters')
        if value:height=value/10
    bmi=round(weight[0]/(height/100)**2,1) if weight[0] and height else None
    body_fat,fat_day=metric(rows,'body-fat','bodyFatPercentageAvg')
    lean=None
    if body_fat is not None and weight[0] and abs((date.fromisoformat(fat_day)-date.fromisoformat(weight[1])).days)<=3:
        lean=round(weight[0]*(1-body_fat/100),1)
    balance=[]
    for d in complete:
        total,_=metric(rows,'total-calories','kcalSum',d)
        if total is not None and d<on and days.get(d,{}).get('calories',0)>0:
            balance.append(days[d]['calories']-total)
    trends={}
    for key in ('hrv','rhr'):
        recent=[days[d][key] for d in week if days.get(d,{}).get(key) is not None]
        older=[v[key] for d,v in days.items() if (end-timedelta(days=27)).isoformat()<=d<week[-1] and v.get(key) is not None]
        if len(recent)>=3 and len(older)>=7:
            a,b=statistics.mean(recent),statistics.mean(older)
            trends[key]={"recent":round(a,1),"baseline":round(b,1),"difference":round(a-b,1),"percent":round(100*(a-b)/b,1) if b else None,"days":len(recent),"baseline_days":len(older)}
    correlations=[]
    for x,y,shift,label in [('workout_minutes','sleep_hours',1,'Activity and the following night'),('sleep_hours','hrv',0,'Sleep duration and morning HRV'),('sleep_hours','rhr',0,'Sleep duration and resting heart rate'),('steps','sleep_hours',1,'Steps and the following night')]:
        pairs=[]
        for d,values in days.items():
            if d<month[-1]:continue
            other=days.get((date.fromisoformat(d)+timedelta(days=shift)).isoformat(),{})
            a=values.get('sleep',{}).get('minutes',None) if x=='sleep_hours' else values.get(x)
            b=other.get('sleep',{}).get('minutes',None) if y=='sleep_hours' else other.get(y)
            # Activity zero is unknown unless an actual device day or workout exists.
            observed_activity=values.get('steps') is not None or values.get('rhr') is not None or values.get('workout_minutes',0)>0
            if x=='workout_minutes' and not observed_activity:continue
            if a is not None and b is not None:pairs.append((a,b))
        if len(pairs)>=14:
            xs,ys=zip(*pairs)
            if statistics.pstdev(xs)>0 and statistics.pstdev(ys)>0:
                correlations.append({'label':label,'r':round(statistics.correlation(xs,ys),2),'n':len(pairs), 'note':'An exploratory pattern in your records. It does not prove cause or effect and may reflect a shared trend or other factors.'})
    components=[]
    if sleeps:components.append({'name':'Sleep duration','score':round(min(100,100*duration/profile.sleep_goal)), 'days':len(sleeps), 'detail':f'{duration:.1f} h on average against your {profile.sleep_goal} h goal'})
    if active_days:components.append({'name':'Pohyb','score':round(min(100,100*(moderate+2*vigorous)/150)), 'days':len(active_days),'detail':f'{round(moderate+2*vigorous)} moderate-equivalent minutes on recorded days'})
    if nutrition:
        protein=statistics.mean(d['protein'] for d in nutrition);fiber=statistics.mean(d['fiber'] for d in nutrition)
        components.append({'name':'Nutrition against your goals','score':round(50*min(1,protein/profile.protein_goal)+50*min(1,fiber/profile.fiber_goal)), 'days':len(nutrition),'detail':f'Protein {protein:.0f} g, fiber {fiber:.0f} g. Only days marked complete.'})
    return {'fitness_age':fit,'fitness_requirements':requirements,'index':round(statistics.mean(c['score'] for c in components)) if len(components)>=2 else None,
            'components':components,'index_note':'The app\'s own descriptive habit index 0–100, the average of the available areas. Not a biological age and not the official Life’s Essential 8. A missing area does not count as zero.',
            'sleep':{'days':len(sleeps),'mean_hours':round(duration,2) if duration is not None else None,'debt_hours':round(debt,2) if debt is not None else None,'regularity_minutes':regularity,'regularity_days':len(bedtimes),'efficiency':round(statistics.mean(efficiencies),1) if efficiencies else None},
            'activity':{'moderate':round(moderate),'vigorous':round(vigorous),'equivalent_minutes':round(moderate+2*vigorous) if active_days else None,'days':len(active_days),'workout_minutes':round(volume),'previous_minutes':round(previous_volume),'change_percent':round(100*(volume-previous_volume)/previous_volume) if previous_volume else None},
            'nutrition':{'complete_days':len(nutrition),'protein':round(statistics.mean(d['protein'] for d in nutrition)) if nutrition else None,'fiber':round(statistics.mean(d['fiber'] for d in nutrition),1) if nutrition else None,'protein_per_kg':round(statistics.mean(d['protein'] for d in nutrition)/weight[0],2) if nutrition and weight[0] else None,'energy_balance':round(statistics.mean(balance)) if balance else None,'balance_days':len(balance)},
            'body':{'bmi':bmi,'weight':weight[0],'weight_day':weight[1],'height_cm':height,'body_fat':body_fat,'fat_day':fat_day,'lean_kg':lean},'trends':trends,'correlations':correlations,'window':{'from':week[-1],'to':on}}
