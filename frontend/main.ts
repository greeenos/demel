import './style.css';
import { metricDetail } from './insights';
import { type Obj, esc, fmt, icon, button, input, number, select, toggle, wordmark } from './ui';
import { nav, meals, activities, todayView, healthView, nutritionView, workoutsView, coachView, settingsView, chatMeta } from './views';
import { demoState } from './demo';
import { launch, settle } from './water';

const app=document.querySelector<HTMLDivElement>('#app')!;
let state:Obj|null=null, demo=false, offline=false, busy=false, healthTab='vitals';
const todayStr=()=>new Intl.DateTimeFormat('en-CA').format(new Date());
let selectedDay=todayStr(),lastToday=selectedDay;
let route=location.hash.slice(1)||'today';
let activeImage:string|null=null;
let historyEntries:Obj[]=[];
let pendingWater:number|null=null;
let enter:''|'up'|'next'|'prev'='up';
const pillPrev:Record<string,{x:number,y:number,w:number,h:number}>={};
const reducedMotion=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
const sheet=document.createElement('dialog');sheet.className='sheet';document.body.append(sheet);
const metricLabels:Obj={rhr:['Resting heart rate','bpm',20,200],hrv:['HRV (RMSSD)','ms',1,500],steps:['Steps','',0,200000],active_kcal:['Active energy','kcal',0,20000],weight:['Weight','kg',20,400],spo2:['SpO₂','%',50,100],respiratory_rate:['Breathing rate','/min',3,60],temperature:['Skin temperature','°C',20,45],vo2max:['VO₂ max','ml/kg/min',5,100],systolic:['Systolic pressure','mmHg',60,260],diastolic:['Diastolic pressure','mmHg',30,160]};
const labLabels:Obj={albumin:['Albumin','g/L',100],creatinine:['Creatinine','µmol/L',3000],glucose:['Glucose','mmol/L',60],crp:['CRP','mg/L',1000],lymphocytes:['Lymphocytes','%',100],mcv:['MCV','fL',200],rdw:['RDW','%',60],alp:['ALP','U/L',3000],wbc:['White blood cells','10⁹/L',300]};
const navColor:Obj={today:'var(--orange)',health:'var(--coral)',nutrition:'var(--green)',workouts:'var(--pink)',coach:'var(--purple)'};
const titleMap:Obj={today:['Your health, in context.','Today'],health:['Every measurement has its context.','Health'],nutrition:['Good food. Good feeling.','Nutrition'],workouts:['Movement that suits you.','Training'],coach:['Ask. Get to know yourself.','Demel AI'],settings:['Everything your way.','Settings']};
const foodBasics:Obj[]=[
 {name:'Rolled oats',calories:370,protein:13,carbs:60,fat:7,fiber:10,grams:100},
 {name:'Greek yogurt 0%',calories:59,protein:10,carbs:3.6,fat:.4,fiber:0,grams:100},
 {name:'Banana',calories:89,protein:1.1,carbs:23,fat:.3,fiber:2.6,grams:100},
 {name:'Eggs',calories:143,protein:12.6,carbs:.7,fat:9.5,fiber:0,grams:100},
 {name:'Chicken breast, cooked',calories:165,protein:31,carbs:0,fat:3.6,fiber:0,grams:100},
 {name:'Rice, cooked',calories:130,protein:2.7,carbs:28,fat:.3,fiber:.4,grams:100},
 {name:'Salmon, cooked',calories:206,protein:22,carbs:0,fat:12,fiber:0,grams:100},
 {name:'Apple',calories:52,protein:.3,carbs:14,fat:.2,fiber:2.4,grams:100},
 {name:'Olive oil',calories:884,protein:0,carbs:0,fat:100,fiber:0,grams:100},
 {name:'Broccoli',calories:34,protein:2.8,carbs:6.6,fat:.4,fiber:2.6,grams:100}
];

function toast(message:string,error=false){const el=document.querySelector<HTMLElement>('#toast')!;el.textContent=message;el.className='visible'+(error?' error':'');setTimeout(()=>el.className='',5000);}
async function api(path:string,method='GET',body?:unknown):Promise<any>{
 if(demo)throw new Error('This is the demo. Log in to your own account to save.');
 const r=await fetch('/api'+path,{method,headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
 const data=await r.json().catch(()=>({detail:'The server returned an invalid response.'}));
 if(!r.ok){let message=data.detail;if(Array.isArray(message))message=message.map((e:Obj)=>`${e.loc?.slice(1).join('.')}: ${e.msg}`).join('; ');throw new Error(message||'Request failed.');}return data;
}
async function load(before?:Promise<unknown>){
 state=await api('/state?day='+selectedDay);offline=false;
 if(state!.profile.offline_cache)localStorage.setItem('vital-snapshot',JSON.stringify(state));else localStorage.removeItem('vital-snapshot');
 if(before)await before.catch(()=>{});
 render();
}
function render(){
 if(!state)return;
 const labsOpen=!!app.querySelector<HTMLDetailsElement>('.optional-labs')?.open;
 document.documentElement.dataset.theme=state.profile.theme||'system';
 const current=titleMap[route]?route:'today',title=titleMap[current];
 document.body.dataset.route=current;
 const activeNav=current==='settings'?'':current;
 const content=current==='today'?todayView(state,selectedDay):current==='health'?healthView(state,selectedDay,healthTab):current==='nutrition'?nutritionView(state,selectedDay):current==='workouts'?workoutsView(state,selectedDay):current==='coach'?coachView(state,busy):settingsView(state);
 app.innerHTML=`<aside class="sidebar"><a class="brand" href="#today"><img class="brand-mark" src="/icon.svg?v=2" alt="" width="32" height="32">${wordmark}</a><nav aria-label="Main navigation">${nav.map(([k,l,i])=>`<button class="nav-item ${activeNav===k?'active':''}" style="--c:${navColor[k]}" data-action="nav:${k}">${icon(i)}<span>${l}</span></button>`).join('')}</nav><div class="sidebar-bottom">${syncStatus(state)}<button class="nav-item ${current==='settings'?'active':''}" data-action="nav:settings">${icon('settings')} Settings</button></div></aside>
 <div class="app-body">${demo?'<div class="demo-banner">Demo data · nothing is saved <button data-action="exit-demo">Leave demo</button></div>':''}${offline?'<div class="offline-banner">Offline copy · last loaded '+esc(new Date(state.server_time).toLocaleString('en-GB'))+'. Logging needs a connection.</div>':''}<header class="topbar"><a class="mobile-brand" href="#today"><img class="brand-mark" src="/icon.svg?v=2" alt="" width="32" height="32">${wordmark}</a><div class="welcome">${state.profile.name?'Hi, '+esc(state.profile.name):'Welcome to your space'} <span>${icon('sun')}</span></div><div class="top-actions">${syncStatus(state,true)}<button class="avatar" data-action="nav:settings" aria-label="Open settings">${esc((state.profile.name||'V').charAt(0).toUpperCase())}</button></div></header>
 <main><div class="page-heading"><div><h1>${title[1]}</h1><p>${title[0]}</p></div>${current!=='settings'&&current!=='coach'?`<div class="day-control"><button class="icon-btn" data-action="day:-1" aria-label="Previous day">${icon('back')}</button><label><span class="sr-only">Selected day</span><input type="date" id="day-picker" value="${selectedDay}" max="${todayStr()}"></label><button class="icon-btn" data-action="day:1" aria-label="Next day">${icon('chevron')}</button></div>`:''}</div><div class="view-content">${content}</div><footer class="page-footer"><span>${icon('shield')} Your data stays on your server. AI is only used when you ask.</span><a href="https://www.streamlinehq.com" target="_blank" rel="noopener noreferrer">Icons by Streamline · CC BY 4.0</a></footer></main></div>
 <nav class="bottom-nav" aria-label="Mobile navigation">${nav.map(([k,l,i])=>`<button class="${activeNav===k?'active':''}" style="--c:${navColor[k]}" data-action="nav:${k}" aria-label="${l}" ${activeNav===k?'aria-current="page"':''}>${icon(i)}<span>${l}</span></button>`).join('')}</nav>`;
 if(labsOpen)app.querySelector('.optional-labs')?.setAttribute('open','');
 if(current==='coach')app.querySelector('.chat-messages')?.scrollTo({top:100000});
 if(pendingWater!==null){const from=pendingWater;pendingWater=null;settle(from);}
 const anim=enter;enter='';motion(anim);
}
/* ---------- Motion ---------- */
function pill(sel:string){
 const box=app.querySelector<HTMLElement>(sel);if(!box)return;
 const ind=document.createElement('i');ind.className='pill-ind';ind.setAttribute('aria-hidden','true');box.prepend(ind);
 const act=box.querySelector<HTMLElement>(':scope > .active');
 if(!act||!act.offsetWidth){ind.style.opacity='0';delete pillPrev[sel];return;}
 const b=box.getBoundingClientRect(),r=act.getBoundingClientRect();
 const to={x:r.left-b.left+box.scrollLeft-box.clientLeft,y:r.top-b.top+box.scrollTop-box.clientTop,w:r.width,h:r.height},from=pillPrev[sel];
 Object.assign(ind.style,{width:to.w+'px',height:to.h+'px',transform:`translate(${to.x}px,${to.y}px)`});
 pillPrev[sel]=to;
 if(from&&(Math.abs(from.x-to.x)>1||Math.abs(from.y-to.y)>1)&&!reducedMotion()){
  ind.animate([{transform:`translate(${from.x}px,${from.y}px)`,width:from.w+'px',height:from.h+'px'},{transform:`translate(${to.x}px,${to.y}px)`,width:to.w+'px',height:to.h+'px'}],{duration:460,easing:'cubic-bezier(.3,1.35,.45,1)'});
  act.querySelector('.icon')?.animate([{transform:'scale(1)'},{transform:'scale(.78)',offset:.3},{transform:'scale(1.14)',offset:.65},{transform:'scale(1)'}],{duration:480,easing:'ease-out'});
 }
}
function countUp(el:HTMLElement,delay:number){
 const node=Array.from(el.childNodes).find(n=>n.nodeType===3&&/\d/.test(n.textContent||''));if(!node)return;
 const raw=node.textContent!,m=raw.match(/-?\d[\d,]*(?:\.\d+)?/);if(!m)return;
 const txt=m[0].trim(),target=Number(txt.replace(/,/g,''));if(!Number.isFinite(target)||target===0)return;
 const dec=(txt.split('.')[1]||'').length,f=new Intl.NumberFormat('en-US',{minimumFractionDigits:dec,maximumFractionDigits:dec});
 const before=raw.slice(0,m.index),after=raw.slice(m.index!+m[0].length)+(m[0].endsWith(' ')?' ':'');
 node.textContent=before+f.format(0)+after;const start=performance.now()+delay,dur=900;
 const step=(now:number)=>{const k=Math.max(0,Math.min(1,(now-start)/dur)),e=k===1?1:1-Math.pow(2,-10*k);node.textContent=before+f.format(target*e)+after;if(k<1)requestAnimationFrame(step);else node.textContent=raw;};
 requestAnimationFrame(step);
}
function motion(anim:''|'up'|'next'|'prev'){
 for(const sel of ['.sidebar nav','.bottom-nav','.tabs'])pill(sel);
 if(!anim||reducedMotion())return;
 const vc=app.querySelector<HTMLElement>('.view-content');if(!vc)return;
 vc.dataset.dir=anim;vc.classList.add('enter');
 app.querySelector('.page-heading')?.classList.add('enter-head');
 const cards=Array.from(vc.querySelectorAll<HTMLElement>('.card, :scope > .tabs, .chat-workspace'));
 cards.forEach((c,i)=>{const n=Math.min(i,9);c.style.setProperty('--i',String(n));
  c.querySelectorAll<HTMLElement>('.score-text strong, .big-number, .vital-stat strong, .inline-stats strong, .macro-mini strong, .calorie-total strong, .metric-tile > strong, .habit-index > strong, .feeling-grid strong, .derived-card > strong, .water-num, .sleep-hero strong, .age-result > strong').forEach(el=>countUp(el,n*55+180));});
 setTimeout(()=>{vc.classList.remove('enter');delete vc.dataset.dir;app.querySelector('.page-heading')?.classList.remove('enter-head');cards.forEach(c=>c.style.removeProperty('--i'));},1900);
}
function syncStatus(s:Obj,compact=false):string{
 const c=s.connections||{},last=c.google_last_sync?new Date(c.google_last_sync):null;
 let when='Not connected',tone='off';
 if(last&&!isNaN(+last)){const now=new Date(),day=(d:Date)=>new Intl.DateTimeFormat('en-CA').format(d),y=new Date(now);y.setDate(now.getDate()-1);
  const time=last.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});
  when=day(last)===day(now)?'today '+time:day(last)===day(y)?'yesterday '+time:last.toLocaleDateString('en-GB',{day:'numeric',month:'short'})+' '+time;
  tone=now.getTime()-last.getTime()<2*3600e3?'fresh':'stale';}
 else if(c.google_connected){when='Not synced yet';tone='stale';}
 const title=c.google_connected?'Last Google Health sync · tap to sync now':'Google Health is not connected';
 return `<button class="sync-status ${tone} ${compact?'compact':''}" data-action="${c.google_connected?'google-sync':'nav:settings'}" title="${title}" aria-label="${title}: ${esc(when)}"><span class="sync-dot"></span><span class="sync-text">${compact?'':'<small>Google Health</small>'}<b>${esc(when)}</b></span>${icon('sync')}</button>`;
}
function navigate(next:string){if(location.hash!=='#'+next)history.pushState(null,'','#'+next);route=next;enter='up';render();window.scrollTo({top:0});}
window.addEventListener('hashchange',()=>{route=location.hash.slice(1)||'today';enter='up';render();});
let closeTimer=0;
const closeNow=sheet.close.bind(sheet);
sheet.close=()=>{if(!sheet.open||closeTimer)return;if(reducedMotion()){closeNow();return;}sheet.classList.add('closing');closeTimer=window.setTimeout(()=>{closeTimer=0;sheet.classList.remove('closing');closeNow();},190);};
function modal(title:string,html:string){if(closeTimer){clearTimeout(closeTimer);closeTimer=0;sheet.classList.remove('closing');}sheet.innerHTML=`<div class="sheet-head"><h2>${esc(title)}</h2><button class="icon-btn" data-action="close" aria-label="Close">${icon('close')}</button></div><div class="sheet-body">${html}</div>`;if(!sheet.open)sheet.showModal();}
sheet.addEventListener('click',e=>{if(e.target===sheet)sheet.close();});
const textArea=(name:string,label:string,value='')=>`<label class="field"><span>${label}</span><textarea name="${name}" rows="3" maxlength="5000">${esc(value)}</textarea></label>`;
const fieldsNumeric=(data:Obj,names:string[])=>{for(const k of names)data[k]=data[k]===''?null:Number(data[k]);return data;};

function entryForm(kind:string,entry?:Obj,preset?:Obj){
 if(!state)return;
 const old=entry||(['vitals','sleep','journal'].includes(kind)?state.entries.find((e:Obj)=>e.kind===kind&&e.day===selectedDay&&e.source==='manual'):null);
 const d=preset||old?.data||{},day=old?.day||selectedDay;
 const titles:Obj={meal:'Log meal',food:'My food',vitals:'Log measurements',sleep:'Log sleep',workout:'Log workout',plan:'Training plan',journal:'Today’s check-in',exercise:'Custom exercise',water:'Add water',lab:'Blood test',clock:'Lab result'};
 let fields='';
 if(kind==='meal'||kind==='food')fields=`${input('name','Meal name',d.name||'','required maxlength="180"')}${select('meal','Meal',meals,d.meal||'snack')}<div class="form-grid">${number('grams','Whole portion weight (g)',d.grams??100,'min="1" max="10000" required')}${number('calories','Whole portion energy (kcal)',d.calories??'','min="0" max="10000" required')}${number('protein','Protein, whole portion (g)',d.protein??0,'min="0" max="1000" required')}${number('carbs','Carbs, whole portion (g)',d.carbs??0,'min="0" max="2000" required')}${number('fat','Fat, whole portion (g)',d.fat??0,'min="0" max="1000" required')}${number('fiber','Fiber, whole portion (g)',d.fiber??0,'min="0" max="300" required')}</div><p class="field-hint">Enter all nutrition values for the whole portion above.</p>${textArea('notes','Note',d.notes)}${kind==='meal'?toggle('save_food','Also save to my foods',false):''}`;
 if(kind==='vitals')fields=`<div class="form-grid">${Object.entries(metricLabels).map(([key,[label,unit,min,max]])=>number(key,`${label}${unit?' ('+unit+')':''}`,d[key]??'',`min="${min}" max="${max}"`)).join('')}</div><p class="field-hint">Only fill in values you actually measured. A manual entry overrides Google data for this day.</p>`;
 if(kind==='sleep')fields=`<div class="form-grid">${number('sleep_hours','Sleep duration (hours)',d.minutes==null?'':d.minutes/60,'min="0" max="24" required')}${number('bed_hours','Time in bed (hours)',d.in_bed_minutes==null?'':d.in_bed_minutes/60,'min="0" max="24"')}${input('bedtime','Fell asleep',d.bedtime||'','type="datetime-local"')}${input('wake_time','Woke up',d.wake_time||'','type="datetime-local"')}</div>${select('quality','How did you sleep?',[['','Not specified'],['1','Very badly'],['2','Rather badly'],['3','Average'],['4','Well'],['5','Excellent']],String(d.quality||''))}${textArea('notes','Note',d.notes)}`;
 if(kind==='workout'||kind==='plan')fields=`${input('name',kind==='plan'?'Plan name':'Workout name',d.name||'','required maxlength="160"')}${select('activity','Activity type',activities,activities.some(([k])=>k===d.activity)?d.activity:'other')}<div class="form-grid">${number('minutes','Duration (min)',d.minutes??45,'min="0.1" max="1440" required')}${kind==='workout'?`${number('rpe','Effort RPE (1–10)',d.rpe??'','min="1" max="10" step="1"')}${number('calories','Energy burned (kcal)',d.calories??'','min="0" max="15000"')}${number('distance_km','Distance (km)',d.distance_km??'','min="0" max="1500"')}${number('avg_hr','Average heart rate (bpm)',d.avg_hr??'','min="20" max="250"')}`:''}</div>${kind==='workout'?'<p class="field-hint">RPE: 1 = very easy, 10 = maximum. Without RPE this workout does not count towards the strain score.</p>':''}<div class="sets-header"><h3>Exercises and sets</h3>${button('Choose exercise','choose-exercise','subtle','workout')}${button('Add set','add-set','subtle','plus')}</div><div id="sets-list">${(d.sets||[]).map((set:Obj)=>setRow(set)).join('')}</div>${kind==='workout'?`<div class="workout-timer"><span id="timer-label">Stopwatch: 00:00</span>${button('Start','timer-start','secondary','clock')}${button('Pause','timer-pause','subtle')}${button('Use time','timer-apply','subtle')}</div>`:''}<div class="rest-timer"><span id="rest-label" aria-live="polite">Rest between sets</span>${button('60 s','rest:60','secondary')}${button('90 s','rest:90','secondary')}${button('Cancel','rest:0','subtle')}</div>${textArea('notes','Note',d.notes)}`;
 if(kind==='journal')fields=`<div class="form-grid">${select('mood','Mood',[['1','1 · Very low'],['2','2 · Low'],['3','3 · Neutral'],['4','4 · Good'],['5','5 · Great']],String(d.mood||3))}${select('energy','Energy',[['1','1 · Exhausted'],['2','2 · Low'],['3','3 · Medium'],['4','4 · Good'],['5','5 · Full of energy']],String(d.energy||3))}${select('stress','Stress',[['1','1 · Calm'],['2','2 · Low'],['3','3 · Medium'],['4','4 · High'],['5','5 · Very high']],String(d.stress||3))}${number('caffeine','Caffeine (mg)',d.caffeine||0,'min="0" max="1500" required')}${number('meditation','Meditation (min)',d.meditation||0,'min="0" max="300" required')}</div>${toggle('alcohol','Alcohol',!!d.alcohol)}${toggle('illness','Illness / cold',!!d.illness)}${textArea('notes','What shaped your day?',d.notes)}`;
 if(kind==='exercise')fields=`${input('name','Exercise name',d.name||'','required maxlength="180"')}${input('equipment','Equipment',d.equipment||'')}${input('muscle','Muscle group',d.muscle||'')}${textArea('instructions','How to do it',d.instructions)}`;
 if(kind==='water')fields=number('ml','Water (ml)',d.ml||250,'min="1" max="3000" required step="1"');
 if(kind==='lab')fields=`<div class="notice">All 9 values must come from a single blood draw. Check the units carefully against your lab report. CRP below the detection limit cannot be entered as zero.</div><div class="form-grid">${Object.entries(labLabels).map(([key,[label,unit,max]])=>number(key,`${label} (${unit})`,d[key]??'',`min="0.001" max="${max}" required`)).join('')}</div><p class="field-hint">Convert ALP in µkat/L to U/L by multiplying by 60, and albumin in g/dL by multiplying by 10. Enter RDW in %, not RDW-SD in fL. Enter CRP in mg/L; the app converts it to mg/dL.</p>${textArea('notes','Lab / note',d.notes)}`;
 if(kind==='clock')fields=`${select('method','Method',['Horvath','Hannum','DNAm PhenoAge','GrimAge','GrimAge2','DunedinPACE','KDM','Other'].map(x=>[x,x]),d.method||'DunedinPACE')}${number('value','Result (years; a ratio for DunedinPACE)',d.value??'','min="0.1" max="150" required')}${input('lab','Lab / provider',d.lab||'','required maxlength="160"')}<p class="field-hint">DunedinPACE is not an age: enter e.g. 0.90. For other methods enter the age in years from the report.</p>${textArea('notes','Note on the result',d.notes)}`;
 modal(titles[kind],`<form id="entry-form" data-kind="${kind}" data-id="${esc(old?.id||'')}">${input('day',kind==='lab'?'Draw date':'Date',day,'type="date" required max="'+todayStr()+'"')}${fields}<div class="sheet-actions"><button class="btn primary" type="submit">${icon('check')}Save ${kind==='plan'?'plan':'entry'}</button>${old?button('Delete','delete:'+old.id,'subtle danger','trash'):button('Cancel','close','subtle')}</div><p class="form-error" role="alert"></p></form>`);
 timerSeconds=0;timerStart=null;
}
function setRow(d:Obj={}):string{return `<div class="set-row" data-original="${esc(JSON.stringify(d))}"><input name="set_name" aria-label="Exercise" placeholder="Exercise" required maxlength="100" value="${esc(d.name||'')}"><input name="set_reps" aria-label="Reps" type="number" min="0" max="1000" value="${d.reps??10}" required><span>×</span><input name="set_weight" aria-label="Weight in kg" type="number" min="0" max="1000" step="0.5" value="${d.weight??0}" required><span>kg</span><label class="set-done"><input name="set_done" type="checkbox" ${d.done?'checked':''} aria-label="Set done"></label><button class="icon-btn" type="button" data-action="remove-set" aria-label="Remove set">${icon('close')}</button>${d.seconds!=null||d.minutes!=null||d.rpe!=null||d.failure?`<span class="set-context">${d.seconds!=null?fmt(d.seconds)+' s · ':''}${d.minutes!=null?fmt(d.minutes)+' min · ':''}${d.rpe!=null?'RPE '+fmt(d.rpe)+' · ':''}${d.failure?'To failure':''}</span>`:''}</div>`;}
let timerSeconds=0,timerStart:number|null=null,restUntil=0;
setInterval(()=>{const el=document.querySelector('#rest-label');if(el&&restUntil){const sec=Math.max(0,Math.ceil((restUntil-Date.now())/1000));el.textContent=sec?'Rest '+Math.floor(sec/60)+':'+String(sec%60).padStart(2,'0'):'Rest over';if(!sec)restUntil=0;}},250);
setInterval(()=>{const label=document.querySelector('#timer-label');if(label){const seconds=Math.floor(timerSeconds+(timerStart?(Date.now()-timerStart)/1000:0));label.textContent=`Stopwatch: ${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;}},1000);

function library(){const foods=[...foodBasics,...state!.entries.filter((e:Obj)=>e.kind==='food').map((e:Obj)=>({...e.data,entry_id:e.id}))];modal('Foods and saved meals',`<p class="muted">Basic items show approximate values per 100 g. Your own items use your saved portions.</p>${number('portion','Portion size (g)',100,'id="food-portion" min="1" max="10000"')}<div class="food-library">${foods.map((f:Obj,i:number)=>`<div class="library-item"><button data-action="use-food:${i}"><strong>${esc(f.name)}</strong><span>${fmt(f.calories)} kcal / ${fmt(f.grams)} g</span>${icon('plus')}</button>${f.entry_id?`<button class="icon-btn" data-action="delete:${esc(f.entry_id)}" aria-label="Delete food">${icon('trash')}</button>`:''}</div>`).join('')}</div>`);}

async function action(value:string,target?:HTMLElement){
 if(value.startsWith('rest:')){restUntil=Number(value.slice(5))?Date.now()+Number(value.slice(5))*1000:0;const label=document.querySelector('#rest-label');if(label&&!restUntil)label.textContent='Rest between sets';return;}
 if(value==='hydration-settings'){const h=state!.hydration?.settings||{enabled:true,sip_ml:50,start:540,end:1260,days:[0,1,2,3,4,5,6]};const time=(m:number)=>String(Math.floor(Math.min(m,1439)/60)).padStart(2,'0')+':'+String(Math.min(m,1439)%60).padStart(2,'0');modal('Hydration schedule',`<form id="hydration-form">${toggle('enabled','Reminders through the day',h.enabled)}${number('sip_ml','Sip size (ml)',h.sip_ml,'min="1" max="1000" required')}${number('water_goal','Daily goal (ml)',state!.profile.water_goal,'min="250" max="8000" required')}<div class="form-grid">${input('start','From',time(h.start),'type="time" required')}${input('end','Until',time(h.end),'type="time" required')}</div><fieldset class="weekdays"><legend>Reminder days</legend>${['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].map((label,i)=>`<label><input type="checkbox" name="weekday" value="${i}" ${h.days.includes(i)?'checked':''}>${label}</label>`).join('')}</fieldset><p class="field-hint">The interval adapts to your remaining goal and time. For alerts outside the app, enable push and turn on notifications in settings.</p><button type="submit" class="btn primary">Save schedule</button><p class="form-error" role="alert"></p></form>`);return;}
 if(value.startsWith('hydrate:')){await api('/hydration/'+value.slice(8),'POST');await load();return;}
 if(value==='exercise-library'){const exercises=state!.entries.filter((e:Obj)=>e.kind==='exercise');modal('Exercise library',`${button('Add your own exercise','add:exercise','secondary','plus')}${input('search','Search exercises','','id="exercise-search" type="search"')}<div class="exercise-list">${exercises.map((e:Obj)=>`<details class="exercise-item"><summary>${esc(e.data.name)}<small>${esc(e.data.muscle)} · ${esc(e.data.equipment)}</small></summary><p>${esc(e.data.instructions)}</p>${button('Edit','edit:'+e.id,'subtle')}</details>`).join('')}</div>`);return;}
 if(value==='choose-exercise'){let list=sheet.querySelector('#exercise-picker');if(list){list.remove();return;}sheet.querySelector('#sets-list')!.insertAdjacentHTML('beforebegin',`<div id="exercise-picker">${input('search','Search exercises','','id="exercise-search" type="search"')}<div class="exercise-list">${state!.entries.filter((e:Obj)=>e.kind==='exercise').map((e:Obj)=>`<button type="button" class="exercise-item" data-action="pick-exercise:${esc(e.id)}">${esc(e.data.name)}</button>`).join('')}</div></div>`);return;}
 if(value.startsWith('pick-exercise:')){const e=state!.entries.find((e:Obj)=>e.id===value.slice(14));if(e)sheet.querySelector('#sets-list')!.insertAdjacentHTML('beforeend',setRow({name:e.data.name,exercise_id:e.id.replace('opengym-ex-','')}));sheet.querySelector('#exercise-picker')?.remove();return;}
 if(value==='training-history'||value.startsWith('training-page:')){const offset=value==='training-history'?0:Number(value.slice(14));const r=await api('/training/history?offset='+offset);modal('Full training history',`<p class="muted">${fmt(r.total)} saved activities</p>${r.entries.map((e:Obj)=>`<button class="history-workout" data-action="history-edit:${e.id}"><span><strong>${esc(e.data.name)}</strong><small>${esc(e.day)} · ${fmt(e.data.minutes)} min · ${e.data.sets.length} sets</small></span>${icon('chevron')}</button>`).join('')}<div class="button-row">${offset?button('Previous','training-page:'+Math.max(0,offset-30),'secondary'):''}${offset+r.entries.length<r.total?button('Next','training-page:'+(offset+30),'secondary'):''}</div>`);historyEntries=r.entries;return;}
 if(value.startsWith('history-edit:')){const e=historyEntries.find(e=>e.id===value.slice(13));if(e){if(e.source==='google'){modal(e.data.name,`<p>${esc(e.day)} · ${fmt(e.data.minutes)} minutes</p><p class="muted">Fitbit activity. Edit it in the source app and run a sync.</p>`);}else{if(!state!.entries.some((x:Obj)=>x.id===e.id))state!.entries.push(e);entryForm('workout',e);}}return;}
 if(value==='close'){sheet.close();return;}
 if(value.startsWith('nav:')){navigate(value.slice(4));return;}
 if(value.startsWith('tab:')){healthTab=value.slice(4);navigate('health');return;}
 if(value.startsWith('add:')){entryForm(value.slice(4));return;}
 if(value.startsWith('edit:')){const e=state!.entries.find((e:Obj)=>e.id===value.slice(5));if(e)entryForm(e.kind,e);return;}
 if(value.startsWith('meal:')){entryForm('meal',undefined,{meal:value.slice(5)});return;}
 if(value.startsWith('day:')){const d=new Date(selectedDay+'T12:00:00');d.setDate(d.getDate()+Number(value.slice(4)));const next=new Intl.DateTimeFormat('en-CA').format(d);if(next>todayStr())return;selectedDay=next;enter=Number(value.slice(4))>0?'next':'prev';if(demo){state=demoState(selectedDay);render();}else await load();return;}
 if(value==='exit-demo'){demo=false;state=null;loginView();return;}
 if(value==='demo'){demo=true;enter='up';state=demoState(selectedDay);route='today';render();return;}
 if(value.startsWith('water:')){await addWater(Number(value.slice(6)),target);return;}
 if(value.startsWith('delete:')){if(!confirm('Delete this entry?'))return;await api('/entries/'+encodeURIComponent(value.slice(7)),'DELETE');sheet.close();await load();toast('Entry deleted.');return;}
 if(value==='add-set'){sheet.querySelector('#sets-list')!.insertAdjacentHTML('beforeend',setRow());return;}
 if(value==='remove-set'){target?.closest('.set-row')?.remove();return;}
 if(value==='timer-start'){if(!timerStart)timerStart=Date.now();return;}
 if(value==='timer-pause'){if(timerStart)timerSeconds+=(Date.now()-timerStart)/1000;timerStart=null;return;}
 if(value==='timer-apply'){const minutes=(timerSeconds+(timerStart?(Date.now()-timerStart)/1000:0))/60;(sheet.querySelector('[name="minutes"]') as HTMLInputElement).value=Math.max(.1,Math.round(minutes*10)/10).toString();return;}
 if(value.startsWith('start-plan:')){const e=state!.entries.find((e:Obj)=>e.id===value.slice(11));entryForm('workout',undefined,e.data);timerStart=Date.now();return;}
 if(value.startsWith('template:')){const run=value.endsWith('run');entryForm('plan',undefined,{name:run?'Easy run':'Full body',activity:run?'running':'strength',minutes:run?30:45,sets:run?[]:['Squat','Squat','Squat','Bench press','Bench press','Pull-up','Pull-up'].map(name=>({name,reps:10,weight:0,done:false})),notes:run?'Pace by feel. Adjust the plan to your fitness.':''});return;}
 if(value==='food-library'){library();return;}
 if(value==='nutrition-complete'){const old=state!.entries.find((e:Obj)=>e.kind==='nutrition_day'&&e.day===selectedDay);await api('/entries','POST',{kind:'nutrition_day',day:selectedDay,data:{complete:!old?.data.complete}});await load();toast('Food log status saved.');return;}
 if(value.startsWith('metric:')||value.startsWith('metric-page:')){const parts=value.split(':');const typ=parts[1],day=parts[2],offset=Number(parts[3]||0);const result=await api('/google/data?typ='+encodeURIComponent(typ)+'&day='+day+'&offset='+offset);const spec=state!.google_metrics.find((m:Obj)=>m.type===typ);modal(spec.label,metricDetail(result,spec));return;}
 if(value.startsWith('use-food:')){const foods=[...foodBasics,...state!.entries.filter((e:Obj)=>e.kind==='food').map((e:Obj)=>e.data)],f=foods[Number(value.slice(9))];const grams=Number((sheet.querySelector('#food-portion') as HTMLInputElement).value);if(!(grams>0&&grams<=10000))throw new Error('Enter a portion between 1 and 10,000 g.');const scaled={...f,grams};for(const k of ['calories','protein','carbs','fat','fiber'])scaled[k]=Math.round((f[k]||0)*grams/f.grams*10)/10;entryForm('meal',undefined,scaled);return;}
 if(value==='food-ai'){activeImage=null;modal('Meal with AI',`<p class="muted">Describe the portion or add a photo. The result is a rough estimate you can edit before saving. For photos, pick a model with image support in settings.</p><form id="food-ai-form">${textArea('description','What did you eat, and roughly how much?')}<label class="photo-upload">${icon('camera')}Take or choose a photo<input id="food-image" type="file" accept="image/*" capture="environment" hidden></label><div id="photo-preview"></div><button class="btn primary" type="submit">${icon('spark')}Estimate values</button><p class="form-error" role="alert"></p></form>`);return;}
 if(value==='methodology'){let methods=state?.studies||[];let formulas:Obj={};if(!demo){const m=await api('/methodology');methods=m.studies;formulas=m.scores;}modal('Methods and scientific sources',`<p>A selection of the main methods for biological ageing. Each needs different input data; results from different methods are never combined.</p>${methods.map((m:Obj)=>`<article class="study"><div><h3>${esc(m.method)}</h3><span class="pill ${m.status==='computed'?'green':''}">${m.status==='computed'?'Computed in the app':'Stores a lab result'}</span></div><p>${esc(m.input)}. ${esc(m.note)}</p><a href="${esc(m.url)}" target="_blank" rel="noopener noreferrer">${esc(m.authors)} (${m.year}) ${icon('arrow')}</a></article>`).join('')}<h3>Daily wellness scores</h3><p>These scores are the app’s own transparent heuristics, not clinically validated algorithms.</p>${Object.entries(formulas).map(([k,v])=>`<p><strong>${{recovery:'Recovery',sleep:'Sleep',strain:'Strain'}[k]}:</strong> ${esc(v)}</p>`).join('')}<p class="field-hint">Clinical PhenoAge uses the Levine 2018 coefficients (supplement S1, γ = 0.0076927). CRP is converted from mg/L to mg/dL before the natural log. Age at the blood draw is used. No missing markers are imputed. The result is neither a diagnosis nor an epigenetic measurement.</p>`);return;}
 if(value==='google-connect'){const r=await api('/google/connect');location.assign(r.url);return;}
 if(value==='google-sync'||value==='google-history'){toast('Loading data from Google Health…');const r=await api('/google/sync','POST',{days:value==='google-history'?90:30});await load();toast(r.errors.length?`Saved ${r.saved} records; some data could not be loaded. Details are in settings.`:`Synced ${r.saved} records.`,!!r.errors.length);return;}
 if(value==='google-disconnect'){if(!confirm('Disconnect your Google account? Data already loaded stays saved.'))return;await api('/google/connection','DELETE');await load();return;}
 if(value==='remove-ai-key'){if(!confirm('Remove the saved OpenRouter key?'))return;await api('/connections','PUT',{openrouter:''});await load();return;}
 if(value==='recommended-model'){(document.querySelector('#ai-form [name=ai_model]') as HTMLInputElement).value='anthropic/claude-haiku-5.5';toast('Model selected. Save the AI settings to confirm.');return;}
 if(value==='load-models'){const r=await api('/ai/models');document.querySelector('#ai-models')!.innerHTML=r.models.map((m:Obj)=>`<option value="${esc(m.id)}">${esc(m.name)}${m.vision?' · images':''}</option>`).join('');toast('Models loaded. Start typing in the model ID field.');return;}
 if(value==='enable-push'){await enablePush();return;}
 if(value==='test-push'){await api('/push/test','POST');toast('Test notification sent.');return;}
 if(value==='export'){if(demo)throw new Error('The demo contains none of your data.');location.assign('/api/export');return;}
 if(value==='logout'){await api('/auth/logout','POST');localStorage.removeItem('vital-snapshot');state=null;loginView();return;}
 if(value.startsWith('ask:')){await sendChat(value.slice(4));return;}
 if(value==='clear-chat'){if(!confirm('Clear the AI chat history?'))return;await api('/ai/chat','DELETE');await load();return;}
}

document.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&(e.target as HTMLElement)?.id==='chat-message'){e.preventDefault();(e.target as HTMLElement).closest<HTMLFormElement>('form')?.requestSubmit();}});
document.addEventListener('click',e=>{const target=(e.target as HTMLElement).closest<HTMLElement>('[data-action]');if(!target)return;e.preventDefault();if(target instanceof HTMLButtonElement&&target.disabled)return;const value=target.dataset.action!;action(value,target).catch(e=>toast(e.message,true));});
document.addEventListener('input',e=>{const el=e.target as HTMLInputElement;if(el.id==='exercise-search'){const q=el.value.toLocaleLowerCase();sheet.querySelectorAll<HTMLElement>('.exercise-item').forEach(item=>item.hidden=!item.textContent!.toLocaleLowerCase().includes(q));}if(el.id==='metric-search'){const query=el.value.toLocaleLowerCase();document.querySelectorAll<HTMLElement>('.metric-tile').forEach(tile=>tile.hidden=!tile.textContent!.toLocaleLowerCase().includes(query));const extra=document.querySelector<HTMLDetailsElement>('.other-metrics');if(extra)extra.open=!!query;}});
document.addEventListener('change',async e=>{const target=e.target as HTMLInputElement;try{
 if(target.id==='metric-field'){const typ=target.dataset.type!,day=target.dataset.day!;const result=await api('/google/data?typ='+encodeURIComponent(typ)+'&day='+day);const spec=state!.google_metrics.find((m:Obj)=>m.type===typ);modal(spec.label,metricDetail(result,spec,target.value));}
 if(target.id==='day-picker'){selectedDay=target.value;if(demo){state=demoState(selectedDay);render();}else await load();}
 if(target.id==='import-file'&&target.files?.[0]){const f=target.files[0];if(f.size>8000000)throw new Error('The file is too large.');const data=JSON.parse(await f.text());if(!confirm(`Restore ${data.entries?.length||0} entries? Matching IDs will be overwritten.`))return;const r=await api('/import','POST',{format:data.format,entries:data.entries});await load();toast(`Imported ${r.saved} entries.`);}
 if(target.id==='food-image'&&target.files?.[0]){const f=target.files[0];if(f.size>20000000)throw new Error('Choose a photo smaller than 20 MB.');const bitmap=await createImageBitmap(f);const canvas=document.createElement('canvas'),scale=Math.min(1,1200/Math.max(bitmap.width,bitmap.height));canvas.width=Math.round(bitmap.width*scale);canvas.height=Math.round(bitmap.height*scale);canvas.getContext('2d')!.drawImage(bitmap,0,0,canvas.width,canvas.height);bitmap.close();activeImage=canvas.toDataURL('image/jpeg',.82);document.querySelector('#photo-preview')!.innerHTML=`<img src="${activeImage}" alt="Selected meal photo"><small>The photo is ready. It is sent when you tap Estimate values.</small>`;}
 }catch(err){toast((err as Error).message,true);}});

document.addEventListener('submit',async e=>{
 const form=e.target as HTMLFormElement;if(!form.id)return;e.preventDefault();
 const submit=form.querySelector<HTMLButtonElement>('button[type="submit"]');if(submit?.disabled)return;if(submit)submit.disabled=true;
 const data=Object.fromEntries(new FormData(form).entries()) as Obj;
 const checked=(k:string)=>!!form.querySelector<HTMLInputElement>(`[name="${k}"]`)?.checked;
 const error=form.querySelector('.form-error');if(error)error.textContent='';
 try{
 if(form.id==='login-form'){await api('/auth/login','POST',data);await load();}
 if(form.id==='entry-form'){
  const kind=form.dataset.kind!,entryId=form.dataset.id;const day=data.day;delete data.day;
  const saveFood=checked('save_food');delete data.save_food;delete data.search;
  if(kind==='vitals'){fieldsNumeric(data,Object.keys(metricLabels));if(Object.values(data).every(v=>v===null))throw new Error('Fill in at least one measured value.');}
  if(kind==='meal'||kind==='food')fieldsNumeric(data,['calories','protein','carbs','fat','fiber','grams']);
  if(kind==='lab')fieldsNumeric(data,Object.keys(labLabels));
  if(kind==='clock')fieldsNumeric(data,['value']);
  if(kind==='water')fieldsNumeric(data,['ml']);
  if(kind==='sleep'){data.minutes=Number(data.sleep_hours)*60;data.in_bed_minutes=data.bed_hours===''?null:Number(data.bed_hours)*60;data.quality=data.quality?Number(data.quality):null;data.stages=[];delete data.sleep_hours;delete data.bed_hours;}
  if(kind==='journal'){fieldsNumeric(data,['mood','energy','stress','caffeine','meditation']);data.alcohol=checked('alcohol');data.illness=checked('illness');}
  if(kind==='workout'||kind==='plan'){
   fieldsNumeric(data,kind==='workout'?['minutes','rpe','calories','distance_km','avg_hr']:['minutes']);
   data.sets=Array.from(form.querySelectorAll<HTMLElement>('.set-row')).map(row=>({...JSON.parse(row.dataset.original||'{}'),name:(row.querySelector('[name="set_name"]') as HTMLInputElement).value,reps:Number((row.querySelector('[name="set_reps"]') as HTMLInputElement).value),weight:Number((row.querySelector('[name="set_weight"]') as HTMLInputElement).value),done:(row.querySelector('[name="set_done"]') as HTMLInputElement).checked}));
   for(const k of ['set_name','set_reps','set_weight','set_done'])delete data[k];
  }
  if(kind==='water'&&!entryId&&day===selectedDay){sheet.close();await addWater(Number(data.ml),null);return;}
  await api('/entries','POST',{kind,day,data,...(entryId?{id:entryId}:{})});
  if(saveFood)await api('/entries','POST',{kind:'food',day,data});
  sheet.close();await load();if(kind==='lab'||kind==='clock')document.querySelector('.optional-labs')?.setAttribute('open','');toast('Entry saved.');
 }
 if(form.id==='hydration-form'){const time=(v:string)=>{const [h,m]=v.split(':').map(Number);return h*60+m;};const settings={enabled:checked('enabled'),sip_ml:Number(data.sip_ml),start:time(data.start),end:data.end==='23:59'?1440:time(data.end),days:Array.from(form.querySelectorAll<HTMLInputElement>('[name=weekday]:checked')).map(el=>Number(el.value))};if(settings.end<=settings.start)throw new Error('The end must be later than the start.');await api('/hydration','PUT',settings);await api('/profile','PUT',{...state!.profile,water_goal:Number(data.water_goal)});sheet.close();await load();toast('Hydration schedule saved.');}
 if(form.id==='profile-form'){fieldsNumeric(data,['height_cm','sleep_goal','steps_goal','calorie_goal','protein_goal','fiber_goal','carb_goal','fat_goal','water_goal']);data.birthdate=data.birthdate||null;data.offline_cache=checked('offline_cache');await api('/profile','PUT',{...state!.profile,...data});await load();toast('Profile and goals saved.');}
 if(form.id==='google-form'){const values=Object.fromEntries(Object.entries(data).filter(([,v])=>String(v).trim()));if(!Object.keys(values).length)throw new Error('Fill in the OAuth details.');await api('/connections','PUT',values);await load();toast('Google OAuth details saved.');}
 if(form.id==='ai-form'){if(data.openrouter)await api('/connections','PUT',{openrouter:data.openrouter});await api('/profile','PUT',{...state!.profile,ai_model:data.ai_model.trim(),ai_consent:checked('ai_consent')});await load();toast('AI settings saved.');}
 if(form.id==='notify-form'){await api('/profile','PUT',{...state!.profile,morning_time:data.morning_time,evening_time:data.evening_time,notify_enabled:checked('notify_enabled'),water_reminders:checked('water_reminders'),workout_reminders:checked('workout_reminders')});await load();toast('Notifications saved.');}
 if(form.id==='password-form'){await api('/auth/password','POST',data);form.reset();toast('Password changed. Other sessions were logged out.');}
 if(form.id==='chat-form')await sendChat(String(data.message));
 if(form.id==='food-ai-form'){if(submit)submit.textContent='Estimating portion…';const r=await api('/ai/food','POST',{description:data.description,image:activeImage});entryForm('meal',undefined,r.food);toast(r.note);}
 }catch(err){const message=(err as Error).message;if(error)error.textContent=message;else toast(message,true);}finally{if(submit){submit.disabled=false;if(form.id==='food-ai-form')submit.textContent='Estimate values';}}
});

/* Follow the calendar: if today was selected and midnight passed while the PWA stayed in memory, move to the new day. */
function rollDay(){const t=todayStr();if(t===lastToday)return false;const follow=selectedDay===lastToday;lastToday=t;if(follow)selectedDay=t;return follow;}
async function addWater(ml:number,origin:HTMLElement|null|undefined){
 if(!(ml>0))throw new Error('Enter an amount of water.');
 const rolled=rollDay(),card=document.querySelector<HTMLElement>('.water-card'),from=card&&!rolled?Number(card.dataset.total||0):null;
 const flight=launch(ml,origin,card);
 if(demo){state!.today.water=(state!.today.water||0)+ml;if(state!.hydration)state!.hydration.total=(state!.hydration.total||0)+ml;await flight;pendingWater=from;render();return;}
 try{await api('/entries','POST',{kind:'water',day:selectedDay,data:{ml}});}catch(e){await flight;throw e;}
 pendingWater=from;await load(flight);
}
async function sendChat(message:string){if(busy||!message.trim())return;const previous=state!.chat.length;state!.chat.push({role:'user',content:message});busy=true;render();try{await api('/ai/chat','POST',{message});await load();const logged=chatMeta(state!.chat.at(-1)||{}).logged||[];if(logged.length)toast('Coach logged: '+logged.map((l:Obj)=>l.label).join(', '));}catch(error){state!.chat.splice(previous);throw error;}finally{busy=false;render();const field=document.querySelector<HTMLTextAreaElement>('#chat-message');if(field&&!state!.chat.some((m:Obj)=>m.role==='user'&&m.content===message))field.value=message;}}
async function enablePush(){if(!('serviceWorker' in navigator)||!('PushManager' in window))throw new Error('On iPhone, open the app from your Home Screen. This environment does not support push notifications.');const permission=await Notification.requestPermission();if(permission!=='granted')throw new Error('Notifications are not allowed. Change the permission in your iPhone settings.');const registration=await navigator.serviceWorker.ready;const key=state!.connections.vapid_public;const raw=atob(key.replace(/-/g,'+').replace(/_/g,'/'));const bytes=Uint8Array.from(raw,c=>c.charCodeAt(0));const old=await registration.pushManager.getSubscription();if(old){await api('/push/unsubscribe','POST',{endpoint:old.endpoint}).catch(()=>{});await old.unsubscribe().catch(()=>{});}const subscription=await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:bytes});await api('/push/subscribe','POST',subscription.toJSON());await load();toast('This device will now receive notifications.');}

function loginView(){document.body.dataset.route='login';document.documentElement.dataset.theme='dark';app.innerHTML=`<main class="login-layout"><section class="login-story"><a class="brand" href="#"><img class="brand-mark" src="/icon.svg?v=2" alt="" width="32" height="32">${wordmark}</a><div><span class="login-illustration"><img src="/icon.svg?v=2" alt=""></span><h1>Your health.<br>In your hands.</h1><p>Sleep, movement, nutrition and longevity.<br>In one private space.</p></div><span class="login-private">${icon('shield')} Stored on your own server</span></section><section class="login-panel"><div class="login-box"><span class="pill green">Your private space</span><h2>Welcome to Demel.</h2><p>Log in to your health overview.</p><form id="login-form">${input('password','Password','','type="password" autocomplete="current-password" required')}<button class="btn primary wide" type="submit">Open my overview ${icon('arrow')}</button><p class="form-error" role="alert"></p></form><div class="login-divider"><span>or look around first</span></div>${button('Explore the demo','demo','secondary wide','eye')}<p class="login-note">On iPhone, add the app to your Home Screen from the Share menu in Safari.</p></div></section></main>`;}

async function boot(){app.innerHTML=`<div class="boot"><span class="brand"><img class="brand-mark" src="/icon.svg?v=2" alt="" width="32" height="32">${wordmark}</span><p>Loading your space…</p></div>`;try{const auth=await api('/auth/status');if(auth.authenticated)await load();else{localStorage.removeItem('vital-snapshot');loginView();}}catch{const saved=localStorage.getItem('vital-snapshot');if(saved){try{state=JSON.parse(saved);offline=true;render();}catch{loginView();}}else{loginView();toast('Server unreachable. Check your connection (e.g. Tailscale).',true);}}if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});const status=new URLSearchParams(location.search).get('google');if(status){toast(status==='connected'?'Google account connected. Run your first sync.':status==='denied'?'The Google connection was not confirmed.':'Google sign-in failed. Check your OAuth settings.',status!=='connected');history.replaceState(null,'',location.pathname+location.hash);}}
window.addEventListener('online',()=>{if(!demo&&state)load().catch(()=>{});});
window.addEventListener('offline',()=>{offline=true;render();});
boot();

/* Auto-update: reload when a newer build is deployed (checked on return to the app and every 5 min). */
const currentBuild=document.querySelector<HTMLScriptElement>('script[src*="/assets/index-"]')?.getAttribute('src')||'';
async function checkForUpdate(){
 if(!currentBuild||sheet.open||busy||document.visibilityState!=='visible')return;
 try{const html=await (await fetch('/',{cache:'no-store'})).text();const latest=html.match(/\/assets\/index-[^"]+\.js/)?.[0];
  if(latest&&latest!==currentBuild){(await navigator.serviceWorker?.getRegistration())?.update().catch(()=>{});location.reload();}}catch{}
}
document.addEventListener('visibilitychange',()=>{if(document.visibilityState!=='visible')return;if(rollDay()&&state&&!demo&&!busy)load().catch(()=>{});checkForUpdate();});
setInterval(checkForUpdate,300000);

setInterval(()=>{if(state&&!demo&&!offline&&!busy&&!sheet.open&&document.visibilityState==='visible'&&(rollDay()||['today','nutrition'].includes(route)))load().catch(()=>{});},60000);
