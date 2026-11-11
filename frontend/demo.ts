import type { Obj } from './ui';
// Synthetic, in-memory demo data. Nothing here comes from a real person.
export function demoState(day: string): Obj {
 const history = Array.from({length:30},(_,i)=>{const d=new Date(day+'T12:00:00');d.setDate(d.getDate()-(29-i));return {day:d.toISOString().slice(0,10),hrv:48+Math.sin(i*.7)*9+i*.25,rhr:57+Math.cos(i*.8)*3,sleep_hours:7.3+Math.sin(i)*.6,steps:Math.round(7500+Math.sin(i*.5)*2400),weight:76.8-i*.02,vo2max:46+i*.03,calories:2050,protein:125,water:2000+Math.round(Math.sin(i*.9)*400),workout_minutes:45};});
 const sleep={minutes:466,in_bed_minutes:501,bedtime:day+'T22:54:00',wake_time:day+'T07:15:00',stages:Array.from({length:22},(_,i)=>({stage:['LIGHT','DEEP','LIGHT','REM','AWAKE'][i%5],minutes:[32,24,35,23,4][i%5]}))};
 const entries=[{id:'demo-meal',kind:'meal',day,source:'manual',data:{name:'Overnight oats with blueberries',meal:'breakfast',calories:438,protein:24,carbs:58,fat:13,fiber:8,grams:300}}, {id:'demo-meal2',kind:'meal',day,source:'manual',data:{name:'Chicken rice bowl',meal:'lunch',calories:612,protein:48,carbs:72,fat:14,fiber:5,grams:450}}, {id:'demo-workout',kind:'workout',day,source:'google',data:{name:'Morning run',activity:'running',minutes:32,calories:318,distance_km:5.2,avg_hr:142,sets:[]}}];
 const meta=(logged:Obj[],tokens:number)=>JSON.stringify({model:'anthropic/claude-haiku-5.5',tokens,logged});
 const chat=[
  {role:'user',content:'I just had a big glass of water and a banana.'},
  {role:'assistant',content:'Logged both: 250 ml of water and a medium banana (about 105 kcal, 1 g protein, 27 g carbs).\n\nYou are at 1.5 l of your 2.5 l goal, so another glass or two before dinner keeps you on track.',cost:0.00042,meta:meta([{kind:'water',label:'Water 250 ml'},{kind:'meal',label:'Banana · 105 kcal'}],3120)},
  {role:'user',content:'How are my sleep and recovery connected this week?'},
  {role:'assistant',content:'Your HRV was highest on the three nights you slept more than 7.5 hours, and your resting heart rate dropped by about 3 bpm on those mornings.\n\nThat is a pattern in your own data, not proof of cause, but it suggests protecting your bedtime before hard training days.',cost:0.00061,meta:meta([],4210)},
 ];
 const tz=Intl.DateTimeFormat().resolvedOptions().timeZone;
 return {profile:{name:'Alex',birthdate:'1994-05-16',sleep_goal:8,calorie_goal:2200,protein_goal:130,carb_goal:250,fat_goal:75,water_goal:2500,steps_goal:8000,theme:'dark',ai_model:'anthropic/claude-haiku-5.5',ai_consent:true,timezone:tz},today:{day,hrv:62,rhr:55,steps:6832,active_kcal:426,spo2:98,respiratory_rate:14.2,vo2max:46.9,weight:76.2,sleep,calories:1050,protein:72,carbs:130,fat:27,fiber:13,water:1500,workout_minutes:32},scores:{sleep:97,recovery:86,strain:42,baseline_days:28,drivers:[{name:'HRV',value:62,baseline:54},{name:'Resting HR',value:55,baseline:58}]},history,entries,ages:[],studies:[],chat,server_time:new Date().toISOString(),connections:{openrouter:true,google_connected:true,google_configured:true,google_last_sync:new Date(Date.now()-18*60000).toISOString(),push_devices:0},correlations:[]};
}
