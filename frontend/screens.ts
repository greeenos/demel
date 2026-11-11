// Bevel-style screens: Home, ring details (Strain/Recovery/Sleep), Journal, Fitness, Biology.
// Numbers come from backend/engine.py and backend/bioage.py; this file only draws them.
import { type Obj, esc, fmt, icon, button, empty } from './ui';
import { hydrationView, workoutsView, ageView } from './views';

export type Ring = 'strain' | 'recovery' | 'sleep';
const RING: Record<Ring, { label: string; word: string; icon: string; c1: string; c2: string }> = {
 strain: { label: 'Strain', word: 'Strain', icon: 'flash', c1: '#ffd27a', c2: '#ff5a2c' },
 recovery: { label: 'Recovery', word: 'Recovered', icon: 'leaf', c1: '#e3ef6a', c2: '#3fb54a' },
 sleep: { label: 'Sleep', word: 'Quality', icon: 'moon', c1: '#b9c8ff', c2: '#5b4fd6' },
};
const STATUS: Obj = { above: ['Above normal', 'blue', 'arrow-up'], below: ['Below normal', 'blue', 'arrow-down'], normal: ['Normal range', 'green', 'check'] };
const longDay = (day: string) => new Date(day + 'T12:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'long' });
const isToday = (s: Obj, day: string) => day === new Intl.DateTimeFormat('en-CA', { timeZone: s.profile.timezone }).format(new Date());
const dayTitle = (s: Obj, day: string) => `${isToday(s, day) ? 'Today' : new Date(day + 'T12:00:00').toLocaleDateString('en-GB', { weekday: 'long' })}, ${longDay(day)}`;
const hm = (min: number | null | undefined) => min == null ? '—' : `${Math.floor(min / 60)}h ${String(Math.round(min % 60)).padStart(2, '0')}m`;
const ringValue = (s: Obj, k: Ring): number | null => k === 'strain' ? s.rings?.strain?.score ?? null : k === 'recovery' ? s.rings?.recovery?.score ?? null : s.rings?.sleep?.score ?? null;
const sectionHead = (title: string, sub = '', action = '', label = '') => `<div class="b-head"><div><h2>${esc(title)}</h2>${sub ? `<p>${esc(sub)}</p>` : ''}</div>${action ? `<button class="b-link" data-action="${esc(action)}">${esc(label || 'Edit')}</button>` : ''}</div>`;
const statusLine = (status: string | null, custom?: string) => status ? `<span class="b-status ${STATUS[status][1]}">${icon(status === 'normal' ? 'check' : 'trend')}${esc(custom || STATUS[status][0])}</span>` : `<span class="b-status muted">${icon('info')}Building baseline</span>`;

/* ---------- Rings ---------- */
export function bigRing(value: number | null, k: Ring, size: 'xl' | 'md' = 'md', target?: Obj | null): string {
 const r = RING[k], p = Math.max(0, Math.min(100, value ?? 0));
 const hatch = target ? `<i class="bring-target"><b style="--a:${target.low};--b:${target.high}"></b></i>` : '';
 return `<div class="bring ${size}" style="--p:${p};--c1:${r.c1};--c2:${r.c2}" role="img" aria-label="${r.label} ${value ?? 'not available'}%"><i class="bring-track"></i><i class="bring-fill" ${value == null ? 'hidden' : ''}></i>${hatch}<div class="bring-core"><strong>${value == null ? '—' : value}<small>${value == null ? '' : '%'}</small></strong>${size === 'xl' ? `<span>${r.word}</span>` : ''}</div></div>`;
}

/* ---------- Sparkline with personal normal band ---------- */
export function spark(points: Obj[], color: string, w = 230, h = 78): string {
 const pts = points.filter(p => p.v != null);
 if (pts.length < 2) return `<svg class="spark" viewBox="0 0 ${w} ${h}"><line x1="10" y1="${h / 2}" x2="${w - 14}" y2="${h / 2}" class="spark-empty"/><circle cx="${w - 14}" cy="${h / 2}" r="5" class="spark-dot-empty"/></svg>`;
 const vals = pts.flatMap(p => [p.v, ...(p.band || [])]), lo = Math.min(...vals), hi = Math.max(...vals), span = hi - lo || 1;
 const x = (i: number) => 6 + i / (pts.length - 1) * (w - 22), y = (v: number) => h - 8 - (v - lo) / span * (h - 18);
 const line = pts.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join('');
 const banded = pts.map((p, i) => [i, p.band] as [number, number[] | null]).filter(([, b]) => b);
 const band = banded.length > 1 ? `<path class="spark-band" d="${banded.map(([i, b], j) => `${j ? 'L' : 'M'}${x(i).toFixed(1)},${y(b![1]).toFixed(1)}`).join('')}${banded.slice().reverse().map(([i, b]) => `L${x(i).toFixed(1)},${y(b![0]).toFixed(1)}`).join('')}Z" style="fill:${color}"/>` : '';
 const last = pts.length - 1;
 return `<svg class="spark" viewBox="0 0 ${w} ${h}" aria-hidden="true">${band}<path d="${line}" fill="none" stroke="${color}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/><circle cx="${x(last)}" cy="${y(pts[last].v)}" r="5.5" class="spark-dot" style="stroke:${color};--glow:${color}"/></svg>`;
}

function trendCard(t: Obj, color: string): string {
 const v = t.value, unit = t.unit === 'min' ? '' : t.unit;
 const shown = t.unit === 'min' ? hm(v) : t.key === 'temperature' ? fmt(v, 1) : fmt(v, Math.abs(v) < 200 && !Number.isInteger(v) ? 1 : 0);
 return `<article class="b-card trend"><div class="trend-text"><span class="b-label">${icon(t.icon)}${esc(t.label)}</span><strong class="b-value">${v == null ? '—' : shown}<small>${esc(unit)}</small></strong>${statusLine(t.status)}</div>${spark(t.points, color)}<span class="b-arrow">${icon('arrow')}</span></article>`;
}

/* ---------- Insight card (AI) ---------- */
export function insight(s: Obj, kind: string): string {
 const card = s.insights?.[kind];
 if (card) return `<article class="b-card insight" data-action="insight-open:${kind}"><h3>${esc(card.emoji)} ${esc(card.title)}</h3><p>${esc(card.text)}</p><span class="insight-expand">${icon('arrow')}</span></article>`;
 const ready = s.connections?.openrouter && s.profile.ai_consent && s.profile.ai_model;
 if (!ready) return `<article class="b-card insight muted" data-action="nav:settings"><h3>${icon('spark')} Daily insights</h3><p>Connect an AI model in settings and every screen gets a short, data-based summary.</p></article>`;
 return `<article class="b-card insight loading" data-insight="${kind}" aria-busy="true"><i></i><i></i><i></i><i></i><i class="short"></i></article>`;
}

/* ---------- Health monitor ---------- */
function monitorTile(m: Obj): string {
 const colors: Obj = { normal: 'green', higher: 'orange', lower: 'blue' };
 const c = m.status ? colors[m.status] : 'muted';
 const label = m.status ? { normal: 'Normal', higher: 'Higher', lower: 'Lower' }[m.status as string] : m.value == null ? 'No data' : 'Calibrating';
 const value = m.key === 'sleep_minutes' ? hm(m.value) : fmt(m.value, 1);
 return `<article class="b-card monitor"><div><span class="b-label">${icon(m.icon)}${esc(m.label)}</span><strong class="b-value">${m.value == null ? '—' : value}${m.key === 'sleep_minutes' ? '' : `<small>${esc(m.unit)}</small>`}</strong><span class="b-status ${c}">${icon(m.status === 'normal' ? 'check' : 'trend')}${esc(label)}</span></div><div class="vbar ${c}"><i></i>${m.position != null ? `<b style="--pos:${m.position}"></b>` : ''}</div></article>`;
}

/* ---------- Timeline ---------- */
const activityIcon = (a: string) => /sleep/.test(a) ? 'moon' : /strength|weight/.test(a) ? 'workout' : /walk/.test(a) ? 'target' : 'flash';
function timeline(s: Obj, withSleep = true): string {
 const r = s.rings || {}, items: string[] = [];
 for (const x of (r.sessions || []).slice().reverse()) items.push(`<div class="tl-row" data-action="session:${esc(x.id)}"><span class="tl-icon orange">${icon(activityIcon(x.activity))}</span><div><small>${esc(x.start || '')}</small><strong>${esc(x.name)}</strong><span class="tl-meta">${x.strain != null ? `<span>${icon('gauge')}${x.strain}%</span>` : ''}<span>${icon('clock')}${hm(x.minutes)}</span>${x.kcal ? `<span>${icon('flash')}${fmt(x.kcal)} kcal</span>` : ''}</span></div>${icon('arrow')}</div>`);
 if (withSleep && r.sleep) items.push(`<div class="tl-row" data-action="nav:sleep"><span class="tl-icon purple">${icon('moon')}</span><div><small>${r.sleep.wake_time ? new Date(r.sleep.wake_time).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) : ''}</small><strong>Primary sleep</strong><span class="tl-meta"><span>${icon('target')}${r.sleep.score}%</span><span>${icon('moon')}${hm(r.sleep.asleep)}</span></span></div>${icon('arrow')}</div>`);
 return items.length ? `<div class="b-card list">${items.join('')}</div>` : `<div class="b-card"><p class="muted">No events yet today.</p></div>`;
}

/* ---------- Stress & energy ---------- */
function stressGauge(v: number | null, level: string): string {
 const ticks = 40, filled = v == null ? 0 : Math.round(v / 100 * ticks);
 const lines = Array.from({ length: ticks }, (_, i) => {
  const a = (-225 + i * 270 / (ticks - 1)) * Math.PI / 180, hue = 130 - i / (ticks - 1) * 125;
  return `<line x1="${50 + 38 * Math.cos(a)}" y1="${50 + 38 * Math.sin(a)}" x2="${50 + 45 * Math.cos(a)}" y2="${50 + 45 * Math.sin(a)}" style="stroke:${i < filled ? `hsl(${hue} 75% 58%)` : 'rgba(255,255,255,.12)'}"/>`;
 }).join('');
 return `<div class="gauge"><svg viewBox="0 0 100 100" aria-hidden="true">${lines}</svg><div><strong>${v ?? '—'}</strong><span class="${level === 'High' ? 'orange' : level === 'Low' ? 'green' : 'yellow'}">${esc(level || '')}</span></div></div>`;
}
function stressEnergy(s: Obj): string {
 const st = s.rings?.stress, en = s.rings?.energy;
 if (!st) return `<div class="b-card"><p class="muted">Stress appears after two nights with all-day heart rate.</p></div>`;
 const bars = Array.from({ length: 44 }, (_, i) => `<i class="${en && i < Math.round(en.current / 100 * 44) ? 'on' : ''}"></i>`).join('');
 return `<article class="b-card stress" data-action="stress"><div><span class="b-label strong"><b class="dot green"></b>Today's stress</span><small class="muted">Last updated at ${esc(st.updated)}</small><div class="stress-stats"><div><strong class="coral">${st.high}</strong><span>Highest</span></div><div><strong class="teal">${st.low}</strong><span>Lowest</span></div><div><strong class="yellow">${st.average}</strong><span>Average</span></div></div></div>${stressGauge(st.current, st.level)}</article>
 ${en ? `<article class="b-card energy" data-action="energy"><span class="energy-icon">${icon('flash')}</span><div class="energy-bars">${bars}</div><strong>${en.current}%</strong></article>` : ''}`;
}

/* ---------- Nutrition ---------- */
function dots(value: number, goal: number): string {
 const on = Math.round(Math.min(1, value / (goal || 1)) * 40);
 return `<div class="dotgrid">${Array.from({ length: 40 }, (_, i) => `<i class="${i < on ? 'on' : ''}"></i>`).join('')}</div>`;
}
function nutritionCard(s: Obj): string {
 const t = s.today, p = s.profile, pct = Math.min(100, 100 * (t.calories || 0) / p.calorie_goal);
 return `<article class="b-card foods" data-action="nav:nutrition"><div class="b-head tight"><h3>Today's foods</h3>${icon('arrow')}</div><div class="foods-body"><div class="kcal-dial" style="--p:${pct}"><div><strong>${fmt(t.calories || 0)}</strong><span>kcal</span></div></div><div class="macros">${[['Protein', 'protein', p.protein_goal, 'green'], ['Carbs', 'carbs', p.carb_goal, 'blue'], ['Fat', 'fat', p.fat_goal, 'orange']].map(([l, k, g, c]) => `<div class="${c}"><span>${l} <b>${fmt(t[k as string] || 0)}g</b></span>${dots(t[k as string] || 0, Number(g))}</div>`).join('')}</div></div></article>`;
}

/* ---------- Home ---------- */
export function homeView(s: Obj, day: string): string {
 const r = s.rings || {};
 return `<div class="home-title"><label class="date-title"><span>${esc(dayTitle(s, day))}</span>${icon('chevron')}<input type="date" id="day-picker" value="${day}" max="${new Intl.DateTimeFormat('en-CA').format(new Date())}" aria-label="Pick a day"></label></div>
 <section class="rings-card"><div class="rings-row">${(['strain', 'recovery', 'sleep'] as Ring[]).map(k => `<button class="ring-btn" data-action="nav:${k}">${bigRing(ringValue(s, k), k, 'md', k === 'strain' ? r.target : null)}<span>${RING[k].label}</span></button>`).join('')}</div>${insight(s, 'home')}</section>
 ${sectionHead('Stress & Energy')}${stressEnergy(s)}
 ${sectionHead('Nutrition')}${nutritionCard(s)}
 ${sectionHead('Health Monitor')}<div class="monitor-grid">${(r.monitor || []).map(monitorTile).join('')}</div>
 ${sectionHead('Timeline', `${(r.sessions || []).length + (r.sleep ? 1 : 0)} events`)}${timeline(s)}
 ${hydrationView(s, day)}`;
}

/* ---------- Ring detail pages ---------- */
const tile = (label: string, symbol: string, value: string, unit = '') => `<div class="b-card stat-tile"><span class="b-label">${icon(symbol)}${esc(label)}</span><strong class="b-value">${value}<small>${esc(unit)}</small></strong></div>`;
export function detailTop(title: string, info: string, back = 'today'): string {
 return `<div class="detail-top"><button class="round-btn" data-action="nav:${back}" aria-label="Back">${icon('back')}</button><h1>${esc(title)}</h1><button class="round-btn" data-action="${esc(info)}" aria-label="How it is calculated">${icon('info')}</button></div>`;
}
function zonesList(r: Obj): string {
 if (!r.zones) return '<div class="b-card"><p class="muted">Heart-rate zones need all-day heart rate from your watch.</p></div>';
 const max = Math.max(...r.zones.slice(1), 1), edges = r.zone_ranges, colors = ['', '#9aa0a6', '#5fd6a0', '#f3b34c', '#f04e4e', '#a98bff'];
 return r.zones.map((m: number, i: number) => ({ m, i })).reverse().map(({ m, i }: Obj) => {
  const lo = i === 0 ? 0 : edges[i - 1], hi = i === 5 ? edges[5] : edges[i] - 1;
  return `<div class="b-card zone-row ${m ? '' : 'dim'}"><b>${i}</b>${i && m ? `<i style="width:${Math.max(6, 120 * m / max)}px;background:${colors[i]}"></i>` : ''}<span>${hm(m).replace('h ', ':').replace('m', '')}${i === 0 ? '' : ''}</span><small>${lo} – ${hi} bpm</small></div>`;
 }).join('');
}
function recoveryDrivers(r: Obj): string {
 const c = r.recovery?.components || {};
 if (!c.hrv) return `<div class="b-card"><p class="muted">${r.recovery?.baseline_days ?? 0} of 7 baseline nights with HRV and sleeping heart rate. Recovery appears once the baseline exists.</p></div>`;
 const row = (label: string, v: number, base: number, unit: string, better: number) => `<div class="driver"><span>${esc(label)}</span><strong>${fmt(v, 1)} <small>${unit}</small></strong><small class="${(v - base) * better > 0 ? 'green' : 'orange'}">${v >= base ? '+' : ''}${fmt(v - base, 1)} vs ${fmt(base, 1)} baseline</small></div>`;
 const pen = Object.entries(c.penalties || {}).map(([k, v]) => `<div class="driver"><span>${esc(k.replace('_', ' '))}</span><strong class="orange">−${fmt(Number(v) * 100 / 3, 0)}</strong><small>outside your normal range</small></div>`).join('');
 return `<div class="b-card list">${row('Resting HRV', c.hrv.value, c.hrv.baseline, 'ms', 1)}${row('Sleeping heart rate', c.rhr.value, c.rhr.baseline, 'bpm', -1)}<div class="driver"><span>Sleep score</span><strong>${c.sleep.value}<small>%</small></strong><small>last night</small></div>${pen}</div>`;
}
function sleepDetail(r: Obj, s: Obj): string {
 const sl = r.sleep; if (!sl) return '';
 const stages = s.today.sleep?.stages || [];
 const parts: Obj = { duration: 'Time asleep vs need', efficiency: 'Efficiency', continuity: 'Continuity', deep: 'Deep sleep', rem: 'REM sleep', hr_dip: 'Heart-rate dip' };
 return `${sectionHead('Sleep Need', `Bank ${sl.bank == null ? '—' : (sl.bank >= 0 ? '+' : '−') + hm(Math.abs(sl.bank))} over 7 nights`)}<div class="b-card need"><div><span class="b-label">${icon('target')}Needed tonight</span><strong class="b-value">${hm(sl.need.minutes)}</strong><small class="muted">Goal ${hm(sl.need.goal)} + ${fmt(sl.need.repay)} min debt repayment</small></div><div><span class="b-label">${icon('moon')}Sleep bank</span><strong class="b-value ${sl.bank >= 0 ? 'green' : 'orange'}">${sl.bank == null ? '—' : (sl.bank >= 0 ? '+' : '−') + hm(Math.abs(sl.bank))}</strong><small class="muted">${sl.bank >= 0 ? 'surplus' : 'debt'} vs your goal</small></div></div>
 ${stages.length ? `${sectionHead('Stages')}<div class="b-card"><div class="sleep-stages">${stages.map((st: Obj) => `<i class="stage-${st.stage.toLowerCase()}" style="flex:${st.minutes}" title="${st.stage}: ${fmt(st.minutes)} min"></i>`).join('')}</div><div class="stage-legend">${[['DEEP', 'Deep', sl.deep_pct], ['REM', 'REM', sl.rem_pct], ['LIGHT', 'Light', null], ['AWAKE', 'Awake', null]].map(([k, l, p]) => `<span><i class="stage-${String(k).toLowerCase()}"></i>${l} <b>${fmt(stages.filter((st: Obj) => st.stage === k).reduce((a: number, st: Obj) => a + st.minutes, 0))} min${p != null ? ` · ${p}%` : ''}</b></span>`).join('')}</div><p class="card-note">Deep-sleep target for your age and sex: ${sl.deep_target}% · REM target 20%.</p></div>` : ''}
 ${sectionHead('Score breakdown')}<div class="b-card list">${Object.entries(sl.parts).map(([k, v]) => `<div class="driver"><span>${esc(parts[k] || k)}</span><div class="mini-bar"><i style="width:${v}%"></i></div><strong>${v}<small>%</small></strong></div>`).join('')}</div>`;
}
export function ringDetail(s: Obj, k: Ring, day: string): string {
 const r = s.rings || {}, v = ringValue(s, k), t = r.trends?.[k] || [];
 const color = k === 'strain' ? 'var(--orange)' : k === 'recovery' ? '#7fd858' : 'var(--purple)';
 let tiles = '', extra = '', sub = '';
 if (k === 'strain') {
  const mins = (r.sessions || []).reduce((a: number, x: Obj) => a + x.minutes, 0), kcal = t.find((x: Obj) => x.key === 'total_kcal')?.value;
  tiles = tile('Duration', 'clock', hm(mins)) + tile('Total Energy', 'flash', fmt(kcal), 'kcal');
  sub = r.target ? `<p class="target-line">Target Strain: <b>${r.target.low} – ${r.target.high}%</b></p>` : '';
  extra = `${sectionHead('Strain Timeline', `${(r.sessions || []).length} events`)}${timeline(s, false)}${sectionHead('Heart Rate Zones', `HRmax ${fmt(r.hrmax)} bpm`)}${zonesList(r)}`;
 } else if (k === 'recovery') {
  const c = r.recovery?.components || {};
  tiles = tile('Resting HRV', 'pulse', fmt(c.hrv?.value ?? s.today.hrv, 1), 'ms') + tile('Resting HR', 'heart', fmt(r.rhr, 1), 'bpm');
  sub = r.recovery?.calibrating ? `<p class="target-line">Calibrating · ${r.recovery.baseline_days} baseline nights</p>` : '';
  extra = `${sectionHead('Drivers')}${recoveryDrivers(r)}`;
 } else {
  tiles = tile('Time in Bed', 'moon', hm(r.sleep?.in_bed)) + tile('Time Asleep', 'clock', hm(r.sleep?.asleep));
  sub = r.sleep ? `<p class="target-line">${esc(r.sleep.band)} · efficiency ${r.sleep.efficiency ?? '—'}%</p>` : '';
  extra = sleepDetail(r, s);
 }
 return `<div class="detail ${k}">${detailTop(RING[k].label, 'method:' + k)}<p class="detail-date">${esc(dayTitle(s, day))}</p><div class="detail-hero">${bigRing(v, k, 'xl', k === 'strain' ? r.target : null)}</div>${sub}<div class="tile-row">${tiles}</div>${insight(s, k)}${extra}${sectionHead('Trends')}<div class="trend-list">${t.map((x: Obj) => trendCard(x, color)).join('')}</div></div>`;
}

/* ---------- Journal ---------- */
export const JOURNAL_DAY: [string, string, string][] = [['added_sugar', 'Added sugar', '🍬'], ['keto', 'Keto diet', '🥑'], ['low_carbs', 'Low carbs', '🥖'], ['sunlight', 'Morning sunlight', '🌅'], ['stretching', 'Stretching', '🧘'], ['sauna', 'Sauna', '🧖'], ['cold_exposure', 'Cold exposure', '🧊']];
export const JOURNAL_NIGHT: [string, string, string][] = [['device_in_bed', 'Device in bed', '📱'], ['late_meal', 'Late meal', '🍽️'], ['late_caffeine', 'Late caffeine', '☕'], ['read_in_bed', 'Read in bed', '📖'], ['meditation', 'Meditation', '🧠']];
const tri = (key: string, value: boolean | null | undefined) => `<div class="tri" role="group" aria-label="${esc(key)}">${[['no', 'close', value === false], ['unset', 'minus', value == null], ['yes', 'check', value === true]].map(([v, ic, on]) => `<button class="${on ? 'on ' + v : ''}" data-action="habit:${key}:${v}" aria-pressed="${!!on}" aria-label="${v}">${ic === 'minus' ? '–' : icon(String(ic))}</button>`).join('')}</div>`;
export function journalView(s: Obj, day: string): string {
 const j = s.entries.filter((e: Obj) => e.kind === 'journal' && e.day === day).at(-1)?.data || {};
 const habits = j.habits || {}, d = new Date(day + 'T12:00:00'), monday = new Date(d); monday.setDate(d.getDate() - ((d.getDay() + 6) % 7));
 const week = Array.from({ length: 7 }, (_, i) => { const x = new Date(monday); x.setDate(monday.getDate() + i); return new Intl.DateTimeFormat('en-CA').format(x); });
 const logged = new Set(s.entries.filter((e: Obj) => e.kind === 'journal').map((e: Obj) => e.day)), today = new Intl.DateTimeFormat('en-CA').format(new Date());
 const row = (key: string, label: string, emoji: string) => `<div class="b-card j-row"><span class="j-emoji">${emoji}</span><strong>${esc(label)}</strong>${tri(key, habits[key])}</div>`;
 const numRow = (action: string, label: string, emoji: string, value: string) => `<div class="b-card j-row"><span class="j-emoji">${emoji}</span><strong>${esc(label)}</strong><span class="j-value">${value}</span><button class="square-btn" data-action="${action}" aria-label="Edit ${esc(label)}">${icon('arrow')}</button></div>`;
 const moods = ['😣', '😕', '😐', '🙂', '😊'];
 const ins = s.rings?.journal_insights?.items || [];
 return `<div class="journal-top"><div><h1>Journal</h1><p>${d.toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })}</p></div><button class="pill-btn" data-action="insight-open:journal">${icon('spark')}Insights</button></div>
 <div class="week-strip">${week.map(w => `<button class="${w === day ? 'active' : ''}" data-action="goto-day:${w}" ${w > today ? 'disabled' : ''}><small>${new Date(w + 'T12:00:00').toLocaleDateString('en-GB', { weekday: 'short' })}</small><span>${Number(w.slice(8))}</span><i class="${logged.has(w) ? 'done' : ''}">${logged.has(w) ? icon('check') : ''}</i></button>`).join('')}</div>
 ${sectionHead("Today's Entries", "Your entries feed the 90-day patterns in tomorrow's insights.")}
 <h3 class="j-group">Daytime</h3>
 ${row('added_sugar', 'Added sugar', '🍬')}
 ${numRow('journal-num:alcohol_drinks', 'Alcohol', '🍷', j.alcohol_drinks != null ? `${j.alcohol_drinks} drinks` : '– drinks')}
 ${numRow('journal-num:caffeine', 'Caffeine', '☕', j.caffeine ? `${j.caffeine} mg` : '– mg')}
 ${numRow('journal-mood', 'Daily mood', moods[(j.mood || 3) - 1], j.mood ? `${j.mood}/5` : '–')}
 ${numRow('nav:today', 'Hydration', '💧', `${fmt(s.today.water || 0)} ml`)}
 ${JOURNAL_DAY.slice(1).map(([k, l, e]) => row(k, l, e)).join('')}
 <h3 class="j-group">Nighttime</h3>
 ${JOURNAL_NIGHT.map(([k, l, e]) => row(k, l, e)).join('')}
 <h3 class="j-group">Health</h3>
 ${row('illness', 'Feeling ill', '🤒')}
 ${numRow('add:journal', 'Notes, energy & stress', '📝', j.notes ? 'Saved' : '–')}
 ${sectionHead('Patterns', s.rings?.journal_insights?.note || '')}${ins.length ? `<div class="b-card list">${ins.map((x: Obj) => `<div class="driver"><span>${esc(x.label)}</span><small>Recovery <b>${x.recovery[0] ?? '—'}%</b> with vs <b>${x.recovery[1] ?? '—'}%</b> without · Sleep ${x.sleep[0] ?? '—'} vs ${x.sleep[1] ?? '—'}</small><small class="muted">${x.with} / ${x.without} days</small></div>`).join('')}</div>` : `<div class="b-card"><p class="muted">Patterns appear once a habit has at least 3 days with and 3 without.</p></div>`}
 ${insight(s, 'journal')}`;
}

/* ---------- Fitness ---------- */
function loadGauge(name: string, l: Obj): string {
 const max = Math.max(l.acute, l.optimal[1] * 1.6, 10), ang = (v: number) => -210 + Math.min(1, v / max) * 240;
 const pt = (a: number, rad: number) => [50 + rad * Math.cos(a * Math.PI / 180), 54 + rad * Math.sin(a * Math.PI / 180)];
 const ticks = Array.from({ length: 34 }, (_, i) => { const a = -210 + i * 240 / 33, [x1, y1] = pt(a, 33), [x2, y2] = pt(a, 40); return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`; }).join('');
 const arc = (a1: number, a2: number) => { const [x1, y1] = pt(a1, 44), [x2, y2] = pt(a2, 44); return `M${x1},${y1}A44,44 0 ${a2 - a1 > 180 ? 1 : 0} 1 ${x2},${y2}`; };
 const [kx, ky] = pt(ang(l.acute), 44);
 return `<article class="b-card load"><div class="b-head tight"><div><h3>${esc(name)}</h3><p class="load-status">${esc(l.status)}</p></div>${icon('arrow')}</div><svg viewBox="0 0 100 86" class="load-gauge" aria-hidden="true"><g class="ticks">${ticks}</g><path d="${arc(ang(l.optimal[0]), Math.max(ang(l.optimal[1]), ang(l.optimal[0]) + 2))}" class="optimal"/><circle cx="${kx}" cy="${ky}" r="4.5" class="knob"/><text x="50" y="58" class="big">${l.acute}</text><text x="14" y="84" class="small">0</text><text x="84" y="84" class="small">${Math.round(max)}</text></svg><p class="optimal-line"><i></i>Optimal: <b>${l.optimal[0]} – ${l.optimal[1]}</b></p></article>`;
}
export function fitnessView(s: Obj, day: string): string {
 const r = s.rings || {}, load = r.load, week = r.week || [];
 const hrr = (r.sessions || []).map((x: Obj) => x.hrr).filter((x: number | null) => x != null).at(-1);
 const cum = (rows: number[]) => { let t = 0; return rows.map(x => ({ v: (t += x), band: null })); };
 const durations = week.map((w: Obj) => (w.sessions || []).length), vo2 = s.today.vo2max ?? null;
 return `<div class="fitness-top"><h1>Fitness</h1></div>
 <div class="week-strip fitness">${week.map((w: Obj) => `<button class="${w.day === day ? 'active' : ''}" data-action="goto-day:${w.day}"><small>${new Date(w.day + 'T12:00:00').toLocaleDateString('en-GB', { weekday: 'narrow' })}</small><span>${Number(w.day.slice(8))}</span><i class="act ${w.strain >= 67 ? 'high' : w.strain >= 34 ? 'mid' : ''}">${w.sessions?.length ? icon(activityIcon(w.sessions[0].activity)) : '<em>z<sup>z</sup></em>'}</i></button>`).join('')}</div>
 ${insight(s, 'fitness')}
 ${load ? `${sectionHead('Training Load')}<div class="two-grid">${loadGauge('Cardio', load.cardio)}${loadGauge('Muscular', load.muscular)}</div>` : ''}
 ${sectionHead('Cardio', '', 'method:load', 'Method')}<div class="two-grid">
  <article class="b-card cardio"><h3>All Activities</h3><strong class="b-value">${hm(week.reduce((a: number, w: Obj) => a + 0, 0) + (r.sessions || []).reduce((a: number, x: Obj) => a + x.minutes, 0))}</strong><span>Active today</span>${spark(cum(durations), 'var(--blue)', 180, 64)}</article>
  <article class="b-card cardio"><h3>Strain this week</h3><strong class="b-value">${fmt(week.reduce((a: number, w: Obj) => a + (w.strain || 0), 0) / Math.max(1, week.filter((w: Obj) => w.strain != null).length))}<small>% avg</small></strong><span>7 days</span>${spark(week.map((w: Obj) => ({ v: w.strain, band: null })), 'var(--orange)', 180, 64)}</article>
  <article class="b-card cardio" data-action="method:vo2"><h3>VO₂ Max</h3><strong class="b-value ${vo2 ? '' : 'muted'}">${vo2 ? fmt(vo2, 1) : r.vo2_estimate ? '~' + fmt(r.vo2_estimate, 1) : 'No data'}</strong><span>${vo2 ? 'From your watch' : r.vo2_estimate ? 'Estimate (Uth 2004)' : 'No status'}</span></article>
  <article class="b-card cardio" data-action="method:hrr"><h3>Heart Rate Recovery</h3><strong class="b-value">${hrr != null ? hrr + '<small>bpm</small>' : '<span class="muted">No data</span>'}</strong><span class="${hrr != null ? (hrr > 22 ? 'pink' : 'orange') : 'muted'}">${hrr == null ? 'Needs a zone-4 effort' : hrr > 22 ? 'Normal' : 'Low'}</span></article>
 </div>
 ${sectionHead("Today's Activity")}${timeline(s, false)}
 ${sectionHead('Routines')}${workoutsView(s, day)}`;
}

/* ---------- Biology ---------- */
function bioDial(b: Obj): string {
 // U-shaped scale (screen angles 165° → 15°, through the bottom), calendar age ±5 years.
 const lo = b.chronological - 5, hi = b.chronological + 5, pos = (v: number) => Math.max(0, Math.min(1, (v - lo) / (hi - lo)));
 const at = (t: number, r: number) => { const a = (165 - t * 150) * Math.PI / 180; return [150 + r * Math.cos(a), 24 + r * Math.sin(a)]; };
 const ticks = Array.from({ length: 81 }, (_, i) => { const [x1, y1] = at(i / 80, 132), [x2, y2] = at(i / 80, i % 10 ? 124 : 118); return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`; }).join('');
 const marker = (v: number, cls: string) => { const [x, y] = at(pos(v), 128); return `<circle class="${cls}" cx="${x}" cy="${y}" r="${cls === 'bio' ? 7 : 4.5}"/>`; };
 const [lx, ly] = at(0, 104), [rx, ry] = at(1, 104);
 return `<svg class="bio-dial" viewBox="0 0 300 170" aria-hidden="true"><g class="ticks">${ticks}</g>${marker(b.chronological, 'chrono')}${marker(b.biological, 'bio')}<text x="${lx}" y="${ly}">${fmt(lo, 1)}</text><text x="${rx}" y="${ry}" text-anchor="end">${fmt(hi, 1)}</text></svg>`;
}
function biomarkerRing(c: Obj): string {
 const p = c.years == null ? 0 : Math.min(100, Math.abs(c.years) / 2 * 100), col = c.years == null ? 'var(--faint)' : c.years <= 0 ? 'var(--green)' : 'var(--orange)';
 return `<span class="bm-ring" style="--p:${p};--c:${col}">${icon(c.icon)}</span>`;
}
const yearsText = (y: number | null) => y == null ? 'No data available' : Math.abs(y) < 0.05 ? 'On par with your age' : `${fmt(Math.abs(y), 1)} years ${y < 0 ? 'younger' : 'older'}`;
export function biologyView(s: Obj): string {
 const b = s.bioage || {}, r = s.rings || {};
 const hero = b.available ? `<section class="bio-hero"><h1>Biological Age</h1><p class="muted">As of ${esc(longDay(b.as_of))}</p><div class="bio-number"><strong>${fmt(b.biological, 1)}</strong><span class="${b.difference <= 0 ? 'green' : 'orange'}">${yearsText(b.difference)}</span>${b.change != null ? `<button class="chip" data-action="bio-history">${b.change > 0 ? '▲' : b.change < 0 ? '▼' : '•'} ${b.change > 0 ? '+' : ''}${fmt(b.change, 1)} from last week ${icon('chevron')}</button>` : ''}</div>${bioDial(b)}<p class="bio-chrono">${fmt(b.chronological, 1)}</p><p class="muted center">Next update in <b>${b.next_update_days} day${b.next_update_days === 1 ? '' : 's'}</b></p></section>
  <button class="b-card confidence ${b.confidence >= 70 ? 'good' : ''}" data-action="bio-confidence"><span>${icon('check')}</span><div><strong>${b.confidence}% confidence</strong><small>${b.confidence >= 70 ? 'Up-to-date data' : 'Partial or aging data'}</small></div>${icon('arrow')}</button>`
  : `<section class="bio-hero"><h1>Biological Age</h1>${empty('age', 'Not available yet', b.reason || 'Add your date of birth and sex in settings.')}</section>`;
 const cats = Object.values(b.categories || {}) as Obj[];
 const other = [['Weight', 'weight', 'kg'], ['HRV Baselines', 'hrv', 'ms'], ['RHR Baselines', 'rhr', 'bpm'], ['VO₂ Max', 'vo2max', '']].map(([label, key, unit]) => {
  const rows = (s.history || []).filter((h: Obj) => h[key] != null).slice(-30), last = rows.at(-1)?.[key];
  const first = rows[0]?.[key], dir = rows.length < 2 ? 'none' : Math.abs(last - first) / (first || 1) < 0.02 ? 'Stabilizing' : last > first ? 'Increasing' : 'Decreasing';
  return `<article class="b-card other"><div><h3>${esc(label)}</h3><span class="${rows.length ? '' : 'muted'}">${rows.length ? `${icon('trend')}${dir} · <b>${fmt(last, 1)} ${unit}</b>` : `${icon('close')}No trends available · — ${unit}`}</span></div>${spark(rows.map((x: Obj) => ({ v: x[key], band: null })), 'var(--muted)', 150, 50)}</article>`;
 }).join('');
 return `${hero}${sectionHead('Age Biomarkers')}${cats.map(c => `<button class="b-card biomarker" data-action="bio-cat:${c.key}">${biomarkerRing(c)}<div><strong>${esc(c.label)}</strong><span class="${c.years == null ? 'muted' : c.years <= 0 ? 'green' : 'orange'}">${yearsText(c.years)}</span></div>${icon('chevron')}</button>`).join('')}
 ${insight(s, 'biology')}
 ${sectionHead('Other Biomarkers', '', 'tab:metrics', 'All data')}${other}
 <button class="b-card methods-link" data-action="method:bioage">${icon('book')}<div><strong>Methods and studies</strong><small>Every factor, hazard ratio and source</small></div>${icon('arrow')}</button>
 ${ageView(s)}${r.vo2_estimate ? '' : ''}`;
}

/* ---------- Modals content ---------- */
export function bioCategoryModal(s: Obj, key: string): string {
 const c = s.bioage?.categories?.[key]; if (!c) return '';
 return `<p class="muted">Four-week averages compared with age/sex benchmarks. Years = ln(hazard ratio) ÷ 0.085 (Gompertz), halved for overlapping habits, weighted by data confidence.</p>${c.factors.map((f: Obj) => `<div class="factor"><div class="factor-head"><strong>${esc(f.label)}</strong><span class="${f.weighted == null ? 'muted' : f.weighted <= 0 ? 'green' : 'orange'}">${f.weighted == null ? 'No data' : `${f.weighted > 0 ? '+' : ''}${fmt(f.weighted, 2)} y`}</span></div><p>${f.value != null ? `<b>${esc(fmt(f.value, 1) === '—' ? f.value : fmt(f.value, 1))} ${esc(f.unit)}</b>${f.target ? ` · target ${esc(f.target)}` : ''} · ` : ''}${f.days} days · confidence ${Math.round(f.confidence * 100)}%</p><p class="muted">${esc(f.note)}</p><p class="refs">${f.refs.map((x: string[]) => `<a href="${esc(x[1])}" target="_blank" rel="noopener noreferrer">${esc(x[0])}</a>`).join('')}</p></div>`).join('')}`;
}
export function bioConfidenceModal(s: Obj): string {
 const cats = Object.values(s.bioage?.categories || {}) as Obj[];
 return `<p class="muted">Full confidence needs 20+ days of data in the last 4 weeks per factor; a blood test counts fully when it is under 3 months old and as four factors.</p>${cats.map(c => `<h3>${esc(c.label)}</h3>${c.factors.map((f: Obj) => `<div class="driver"><span>${esc(f.label)}</span><div class="mini-bar"><i style="width:${f.confidence * 100}%"></i></div><strong>${Math.round(f.confidence * 100)}<small>%</small></strong></div>`).join('')}`).join('')}`;
}
export function methodModal(s: Obj, key: string): string {
 if (key === 'bioage') {
  const m = s.bioage?.method || {};
  return `<p>Biological age follows the structure Bevel describes: Sleep, Activity, Fitness, Lifestyle and Blood, four-week averages, updated every Monday, compared with age- and sex-based benchmarks using published hazard ratios.</p><p>Hazard ratio → years: adult mortality rises about 8.5 % per year of age (Gompertz), so years = ln(HR) ÷ ${m.gompertz}. Habit effects are multiplied by ${m.mutual_adjustment} to allow for overlap between correlated habits, capped at ±${m.cap} years per factor, then weighted by data confidence. The total is the sum of the categories.</p><p class="refs">${(m.refs || []).map((x: string[]) => `<a href="${esc(x[1])}" target="_blank" rel="noopener noreferrer">${esc(x[0])}</a>`).join('')}</p><p class="card-note">A population-level estimate for education and motivation, not a diagnosis. Open a category to see every study.</p>`;
 }
 const keys = key === 'strain' ? ['strain', 'target', 'zones'] : key === 'recovery' ? ['recovery'] : key === 'sleep' ? ['sleep'] : key === 'stress' ? ['stress', 'energy'] : [key];
 return keys.map(k => s.methods?.[k]).filter(Boolean).map((m: Obj) => `<div class="factor"><h3>${esc(m.title)}</h3><p>${esc(m.text)}</p><p class="refs">${m.refs.map((x: string[]) => `<a href="${esc(x[1])}" target="_blank" rel="noopener noreferrer">${esc(x[0])}</a>`).join('')}</p></div>`).join('') || '<p class="muted">No method notes.</p>';
}
export function sessionModal(s: Obj, id: string): string {
 const x = (s.rings?.sessions || []).find((v: Obj) => v.id === id); if (!x) return '';
 const zones = x.zones ? `<div class="b-card list">${x.zones.map((m: number, i: number) => `<div class="driver"><span>Zone ${i}</span><div class="mini-bar"><i style="width:${Math.min(100, 100 * m / Math.max(1, x.minutes))}%"></i></div><strong>${m}<small>min</small></strong></div>`).reverse().join('')}</div>` : '';
 return `<div class="tile-row">${tile('Duration', 'clock', hm(x.minutes))}${tile('Strain', 'gauge', x.strain != null ? String(x.strain) : '—', '%')}${tile('Avg HR', 'heart', fmt(x.avg_hr), 'bpm')}${tile('Energy', 'flash', fmt(x.kcal), 'kcal')}</div>${x.hrr != null ? `<p>Heart-rate recovery: <b>${x.hrr} bpm</b> in 2 minutes${x.detected ? ' (estimated from minute data)' : ''}.</p>` : ''}${zones}${x.detected ? `<p class="card-note">Detected from heart rate (≥60 % HRmax for 10+ minutes). Energy via the Keytel equation.</p>${button('Log as workout', 'add:workout', 'secondary', 'plus')}` : ''}`;
}
export function addMenu(): string {
 const items: [string, string, string][] = [['water:250', 'drop', 'Glass of water'], ['add:meal', 'food', 'Meal'], ['food-ai', 'camera', 'Meal with AI'], ['add:workout', 'workout', 'Workout'], ['add:sleep', 'moon', 'Sleep'], ['add:vitals', 'pulse', 'Measurements'], ['add:lab', 'flask', 'Blood test'], ['add:journal', 'book', 'Journal note']];
 return `<div class="add-grid">${items.map(([a, ic, l]) => `<button class="b-card add-item" data-action="${a}">${icon(ic)}<span>${esc(l)}</span></button>`).join('')}</div>`;
}
export function askBar(): string {
 return `<form id="ask-form" class="ask-bar" autocomplete="off"><span class="ask-orb"><i></i><i></i></span><input name="message" placeholder="Ask Demel anything" aria-label="Ask Demel anything" maxlength="6000"></form>`;
}
