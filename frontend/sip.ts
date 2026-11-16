// Full-screen sip reminder (formerly the Drinky app). Shown
//  - by the desktop app on every monitor: /?overlay=1&desktop=1#device=<token>
//  - after tapping a phone notification: /?overlay=1
//  - over the open app whenever a sip comes due.
// The server decides when a sip is due; every device follows /api/hydration/events,
// so "Done" on one device clears the reminder everywhere.
import { esc, fmt, icon, wordmark } from './ui';
import { vessel } from './water';

export type Sip = {due:boolean,next_at:number|null,total:number,goal:number,remaining:number,sip_ml:number,enabled:boolean};

const params = new URLSearchParams(location.search);
const inDesktopApp = params.has('desktop');
const at = (t:number|null) => t ? new Date(t*1000).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'}) : '';
const liters = (s:Sip) => `${fmt(s.total/1000,2)} of ${fmt(s.goal/1000,1)} l today`;
// The desktop window already covers the monitor; iPhone has no Fullscreen API for pages.
const canFullscreen = () => !inDesktopApp && document.fullscreenEnabled && !document.fullscreenElement;
let enteredFullscreen = false;

/** Desktop windows open pages with #device=<token>; swap it for the usual cookie and drop it from the URL. */
export async function adoptDevice() {
 const token = location.hash.match(/^#device=([\w-]+)$/)?.[1];
 if (!token) return;
 history.replaceState(null, '', location.pathname + location.search);
 await fetch('/api/auth/adopt', {method:'POST', headers:{Authorization:'Bearer '+token}}).catch(() => {});
}

export function sipView(s:Sip, page:boolean):string {
 if (!s.due) {
  const next = s.next_at ? `Next sip around ${esc(at(s.next_at))}.` : s.remaining ? 'No reminders right now.' : 'Today’s water goal is done.';
  return `<div class="sip-overlay calm"><div class="sip-box"><span class="brand">${wordmark}</span><h1>All caught up</h1><p>${next} ${liters(s)}.</p>${page && !inDesktopApp ? '<div class="button-row"><a class="btn secondary" href="/">Open Demel</a></div>' : ''}</div></div>`;
 }
 const pct = Math.min(100, 100*s.total/(s.goal||1));
 return `<div class="sip-overlay" role="dialog" aria-modal="true" aria-labelledby="sip-title"><div class="sip-box">
  <div class="sip-figure">${vessel(s.total, s.goal)}</div>
  <h1 id="sip-title">Time for a sip</h1>
  <p>Just ${fmt(s.sip_ml)} ml. ${liters(s)}.</p>
  <div class="sip-meter" role="progressbar" aria-label="Water today" aria-valuenow="${Math.round(pct)}" aria-valuemin="0" aria-valuemax="100"><span style="width:${pct.toFixed(1)}%"></span></div>
  <div class="button-row"><button type="button" class="btn primary" data-sip="drink">${icon('drop')}Done · ${fmt(s.sip_ml)} ml</button><button type="button" class="btn secondary" data-sip="snooze">In 5 min</button><button type="button" class="btn subtle" data-sip="skip">Skip</button></div>
  ${canFullscreen() ? '<button type="button" class="btn subtle sip-full" data-sip="fullscreen">Full screen</button>' : ''}
  <p class="sip-keys">Enter: done · Esc: in 5 min</p>
 </div></div>`;
}

const live = (s:any):Sip => ({due:s.due, next_at:s.next_at, total:s.total, goal:s.goal, remaining:s.remaining, sip_ml:s.settings.sip_ml, enabled:s.settings.enabled});

/** Runs a button of the overlay. Returns the new state, or null for "fullscreen". */
export async function sipAction(action:string):Promise<Sip|null> {
 if (action === 'fullscreen') { await document.documentElement.requestFullscreen().catch(() => {}); enteredFullscreen = !!document.fullscreenElement; return null; }
 const r = await fetch('/api/hydration/'+action, {method:'POST'});
 const data = await r.json().catch(() => ({}));
 if (!r.ok) throw new Error(data.detail || 'Request failed.');
 if (enteredFullscreen && document.fullscreenElement) { enteredFullscreen = false; document.exitFullscreen().catch(() => {}); }
 return live(data);
}

/** Follows the live sip state over SSE (the browser reconnects by itself). Returns a stop function. */
export function followSips(onState:(s:Sip)=>void):()=>void {
 const source = new EventSource('/api/hydration/events');
 source.onmessage = e => { try { onState(JSON.parse(e.data)); } catch {} };
 return () => source.close();
}

/** Click and keyboard handling for an element that holds sipView(). */
export function bindSip(root:HTMLElement, done:(s:Sip|null)=>void, failed:(message:string)=>void) {
 root.addEventListener('click', async e => {
  const b = (e.target as HTMLElement).closest<HTMLButtonElement>('[data-sip]');
  if (!b || b.disabled) return;
  b.disabled = true;
  try { done(await sipAction(b.dataset.sip!)); } catch (error) { failed((error as Error).message); } finally { b.disabled = false; }
 });
 document.addEventListener('keydown', e => {
  if (!root.querySelector('[data-sip=drink]') || e.defaultPrevented || e.isComposing) return;
  const target = e.key === 'Enter' ? 'drink' : e.key === 'Escape' && !document.fullscreenElement ? 'snooze' : '';
  if (!target) return;
  e.preventDefault();
  root.querySelector<HTMLButtonElement>(`[data-sip=${target}]`)?.click();
 });
}

/** The standalone reminder page (?overlay=1). */
export async function startSipPage(app:HTMLElement) {
 document.body.dataset.route = 'sip';
 document.documentElement.dataset.theme = 'dark';
 await adoptDevice();
 const auth = await fetch('/api/auth/status').then(r => r.json()).catch(() => ({authenticated:false}));
 if (!auth.authenticated) {
  app.innerHTML = `<div class="sip-overlay calm"><div class="sip-box"><span class="brand">${wordmark}</span><h1>Log in first</h1><p>Open Demel and log in. Sip reminders then show up here.</p><div class="button-row"><a class="btn primary" href="/">Open Demel</a></div></div></div>`;
  return;
 }
 const show = (s:Sip|null) => { if (!s) { app.querySelector('.sip-full')?.remove(); return; } app.innerHTML = sipView(s, true); app.querySelector<HTMLElement>('[data-sip=drink]')?.focus(); };
 bindSip(app, show, message => { app.querySelector('.sip-box')?.insertAdjacentHTML('beforeend', `<p class="form-error" role="alert">${esc(message)}</p>`); });
 followSips(show);
}
