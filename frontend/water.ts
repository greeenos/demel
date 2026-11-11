// Water "physics": a liquid-filled drop vessel, flying drops, splash and level rise.
import { fmt } from './ui';

const VB_W = 100, VB_H = 196, BOTTOM = 190, SPAN = 183;
// Left half of a standing figure (open outline); mirrored for the right half.
const HALF = 'M44 35.7L44 42Q44 45 38 46L28 48.5Q20 50.5 19 60L14 102Q13.5 108 17 108.5Q20.5 108.5 20.5 103L25 66Q26.5 64 28 66L29 96Q29.5 104 28 112L31 184Q31.5 190 37 190L44 190Q46 190 46 186L47.5 124Q48.5 119 50 119';
const MIRROR = 'matrix(-1 0 0 1 100 0)';
let uid = 0;

const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
const level = (total: number, goal: number) => { const f = Math.max(0, Math.min(1, total / (goal || 1))); return total > 0 ? Math.max(f, .05) : 0; };
const surfaceY = (total: number, goal: number) => BOTTOM - level(total, goal) * SPAN;

/** The vessel: a standing figure outline, clipped liquid with looping waves and rising bubbles. */
export function vessel(total: number, goal: number): string {
  const id = 'wv' + (++uid);
  const y = surfaceY(total, goal).toFixed(2);
  let wave = 'M0 0Q8 -3.2 16 0'; for (let x = 32; x <= 224; x += 16) wave += `T${x} 0`; wave += 'V230H0Z';
  const closed = HALF + 'L50 36Z';
  return `<div class="water-vessel" aria-hidden="true"><svg viewBox="0 0 ${VB_W} ${VB_H}">
  <defs><clipPath id="${id}c"><circle cx="50" cy="22" r="15"/><path d="${closed}"/><path d="${closed}" transform="${MIRROR}"/></clipPath>
  <linearGradient id="${id}g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#a8dcff"/><stop offset=".35" stop-color="#6fb3f5"/><stop offset="1" stop-color="#3f74d8"/></linearGradient></defs>
  <g class="vessel-shell"><circle cx="50" cy="22" r="15"/><path d="${closed}"/><path d="${closed}" transform="${MIRROR}"/></g>
  <g clip-path="url(#${id}c)"><g class="liquid" transform="translate(0 ${y})">
   <g class="waves"><path class="wave wave-back" d="${wave}" fill="url(#${id}g)"/><path class="wave wave-front" d="${wave}" fill="url(#${id}g)"/></g>
   <circle class="bubble b1" cx="40" cy="22" r="1.8"/><circle class="bubble b2" cx="58" cy="30" r="1.3"/><circle class="bubble b3" cx="50" cy="40" r="1.5"/>
  </g></g>
  <g class="vessel-rim"><circle cx="50" cy="22" r="15"/><path d="${HALF}"/><path d="${HALF}" transform="${MIRROR}"/></g>
  <path class="vessel-gloss" d="M33 72Q32 85 33 97"/><path class="vessel-gloss" d="M43 13.5Q39 16 38.5 21"/>
 </svg></div>`;
}

/* ---------- overlay ---------- */
function layer(): HTMLElement {
  let el = document.getElementById('fx');
  if (!el) {
    el = document.createElement('div'); el.id = 'fx';
    el.innerHTML = '<svg width="0" height="0" style="position:absolute"><defs><linearGradient id="fx-water" x1="0" y1="0" x2=".3" y2="1"><stop offset="0" stop-color="#d4eeff"/><stop offset=".5" stop-color="#7cbcf7"/><stop offset="1" stop-color="#3f74d8"/></linearGradient></defs></svg>';
    document.body.append(el);
  }
  return el;
}
const spawn = (cls: string, html = '') => { const n = document.createElement('div'); n.className = cls; n.innerHTML = html; layer().append(n); return n; };
const DROP = '<svg viewBox="0 0 20 26"><path d="M10 1C10 1 2 11 2 17a8 8 0 0 0 16 0C18 11 10 1 10 1Z" fill="url(#fx-water)"/><ellipse cx="7" cy="16" rx="1.8" ry="3.2" fill="#fff" opacity=".55" transform="rotate(18 7 16)"/></svg>';

function impactPoint(card: HTMLElement) {
  const v = card.querySelector<HTMLElement>('.water-vessel'); if (!v) return null;
  const r = v.getBoundingClientRect(), total = Number(card.dataset.total || 0), goal = Number(card.dataset.goal || 1);
  return { x: r.left + r.width / 2, y: r.top + (surfaceY(total, goal) / VB_H) * r.height, vessel: v, rect: r };
}

function splash(x: number, y: number, vesselEl: HTMLElement | null, strength = 1) {
  for (const [i, delay] of [[0, 0], [1, 110]] as const) {
    const ring = spawn('fx-ripple'); ring.style.left = x + 'px'; ring.style.top = y + 'px';
    ring.animate([{ transform: 'scale(.15)', opacity: .95 }, { transform: `scale(${1 + i * .35})`, opacity: 0 }], { duration: 620, delay, easing: 'cubic-bezier(.2,.7,.3,1)', fill: 'both' }).onfinish = () => ring.remove();
  }
  const n = Math.round(5 + strength * 2);
  for (let i = 0; i < n; i++) {
    const dot = spawn('fx-dot'), a = (-90 + (i / (n - 1) - .5) * 150 + (Math.random() - .5) * 18) * Math.PI / 180;
    const dist = 16 + Math.random() * 18 * strength, dx = Math.cos(a) * dist, dy = Math.sin(a) * dist, s = .5 + Math.random() * .8;
    dot.style.left = x + 'px'; dot.style.top = y + 'px';
    dot.animate([
      { transform: `translate(0,0) scale(${s})`, opacity: 1 },
      { transform: `translate(${dx}px,${dy}px) scale(${s})`, opacity: 1, offset: .45 },
      { transform: `translate(${dx * 1.35}px,${dy * .2 + 18}px) scale(${s * .6})`, opacity: 0 }
    ], { duration: 560 + Math.random() * 160, easing: 'cubic-bezier(.25,.8,.4,1)', fill: 'both' }).onfinish = () => dot.remove();
  }
  vesselEl?.animate([{ transform: 'scale(1,1)' }, { transform: 'scale(1.06,.93)' }, { transform: 'scale(.97,1.04)' }, { transform: 'scale(1,1)' }], { duration: 420, easing: 'ease-out' });
}

function fly(from: { x: number; y: number }, to: { x: number; y: number }, delay: number, size: number): Promise<void> {
  const el = spawn('fx-drop', DROP); el.style.width = size + 'px'; el.style.height = size * 1.3 + 'px'; el.style.margin = `${-size * .65}px 0 0 ${-size / 2}px`;
  const c = { x: to.x, y: Math.min(from.y, to.y) - 40 };
  const pt = (t: number) => ({ x: (1 - t) ** 2 * from.x + 2 * (1 - t) * t * c.x + t * t * to.x, y: (1 - t) ** 2 * from.y + 2 * (1 - t) * t * c.y + t * t * to.y });
  const frames: Keyframe[] = [];
  for (let i = 0; i <= 24; i++) {
    const t = i / 24, p = pt(t), q = pt(Math.min(1, t + .02)), p0 = pt(Math.max(0, t - .02));
    const ang = Math.atan2(q.y - p0.y, q.x - p0.x) * 180 / Math.PI - 90, stretch = 1 + Math.min(.35, Math.hypot(q.x - p0.x, q.y - p0.y) / 60);
    frames.push({ transform: `translate(${p.x}px,${p.y}px) rotate(${ang}deg) scale(${(i === 0 ? .2 : 1) / Math.sqrt(stretch)},${(i === 0 ? .2 : 1) * stretch})`, opacity: i === 24 ? .2 : 1, offset: t });
  }
  const anim = el.animate(frames, { duration: 820, delay, easing: 'cubic-bezier(.5,0,.75,.45)', fill: 'both' });
  return anim.finished.then(() => { el.remove(); });
}

/** Launch drops from the pressed button into the vessel. Resolves on the first impact. */
export function launch(ml: number, origin: HTMLElement | null | undefined, card: HTMLElement | null): Promise<void> {
  if (!card || reduced()) return Promise.resolve();
  const hit = impactPoint(card); if (!hit) return Promise.resolve();
  let from: { x: number; y: number };
  if (origin && origin.isConnected) { const r = origin.getBoundingClientRect(); from = { x: r.left + r.width / 2, y: r.top + r.height / 2 }; }
  else from = { x: hit.x, y: Math.max(20, hit.rect.top - 120) };
  const count = ml >= 500 ? 5 : ml >= 250 ? 3 : ml >= 100 ? 2 : 1;
  const label = spawn('fx-label'); label.textContent = '+' + fmt(ml) + ' ml';
  label.style.left = hit.rect.right + 28 + 'px'; label.style.top = hit.y - 18 + 'px'; label.style.opacity = '0';
  let first: Promise<void> | null = null;
  for (let i = 0; i < count; i++) {
    const size = 15 + Math.random() * 7 - i * .6;
    const landed = fly(from, { x: hit.x + (Math.random() - .5) * 6, y: hit.y }, i * 110, size).then(() => {
      const now = impactPoint(card.isConnected ? card : (document.querySelector<HTMLElement>('.water-card') || card));
      splash(hit.x, now?.y ?? hit.y, now?.vessel ?? null, i === count - 1 ? 1.4 : .8);
      if (i === 0) label.animate([{ transform: 'translate(-50%,8px) scale(.8)', opacity: 0 }, { transform: 'translate(-50%,0) scale(1)', opacity: 1, offset: .2 }, { transform: 'translate(-50%,-28px) scale(1)', opacity: 0 }], { duration: 1500, easing: 'cubic-bezier(.2,.7,.3,1)', fill: 'both' }).onfinish = () => label.remove();
    });
    if (!first) first = landed;
  }
  return first || Promise.resolve();
}

/** After re-render: animate level rise, waves slosh, number count-up, progress fill, goal celebration. */
export function settle(from: number) {
  const card = document.querySelector<HTMLElement>('.water-card'); if (!card) return;
  const to = Number(card.dataset.total || 0), goal = Number(card.dataset.goal || 1); if (to === from) return;
  const num = card.querySelector<HTMLElement>('.water-num');
  if (reduced()) return;
  card.querySelector('.liquid')?.animate([{ transform: `translate(0px,${surfaceY(from, goal)}px)` }, { transform: `translate(0px,${surfaceY(to, goal)}px)` }], { duration: 1150, easing: 'cubic-bezier(.22,1.25,.36,1)' });
  const v = card.querySelector('.water-vessel'); v?.classList.remove('slosh'); void (v as HTMLElement)?.offsetWidth; v?.classList.add('slosh');
  setTimeout(() => v?.classList.remove('slosh'), 1500);
  const bar = card.querySelector<HTMLElement>('.progress > i');
  bar?.animate([{ width: Math.min(100, 100 * from / goal) + '%' }, { width: Math.min(100, 100 * to / goal) + '%' }], { duration: 1000, easing: 'cubic-bezier(.2,.8,.2,1)' });
  if (num) {
    const start = performance.now(), dur = 850;
    const step = (now: number) => { const k = Math.min(1, (now - start) / dur), e = 1 - (1 - k) ** 3; num.textContent = fmt((from + (to - from) * e) / 1000, 2); if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  }
  if (from < goal && to >= goal) setTimeout(() => celebrate(card), 650);
}

function celebrate(card: HTMLElement) {
  const v = card.querySelector<HTMLElement>('.water-vessel'); if (!v) return;
  const r = v.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height * .55;
  const glow = spawn('fx-glow'); glow.style.left = cx + 'px'; glow.style.top = cy + 'px';
  glow.animate([{ transform: 'scale(.2)', opacity: .9 }, { transform: 'scale(2.6)', opacity: 0 }], { duration: 900, easing: 'cubic-bezier(.2,.7,.3,1)', fill: 'both' }).onfinish = () => glow.remove();
  const colors = ['#a8dcff', '#74b0f2', '#9aaae6', '#5fd6a0', '#d4eeff'];
  for (let i = 0; i < 26; i++) {
    const d = spawn('fx-dot'), a = Math.random() * Math.PI * 2, dist = 50 + Math.random() * 70, s = .6 + Math.random() * 1.1;
    d.style.left = cx + 'px'; d.style.top = cy + 'px'; d.style.background = colors[i % colors.length]; d.style.boxShadow = `0 0 8px ${colors[i % colors.length]}`;
    d.animate([{ transform: `translate(0,0) scale(${s})`, opacity: 1 }, { transform: `translate(${Math.cos(a) * dist}px,${Math.sin(a) * dist}px) scale(${s})`, opacity: 1, offset: .6 }, { transform: `translate(${Math.cos(a) * dist * 1.15}px,${Math.sin(a) * dist * 1.15 + 30}px) scale(0)`, opacity: 0 }], { duration: 1100 + Math.random() * 300, easing: 'cubic-bezier(.15,.8,.3,1)', fill: 'both' }).onfinish = () => d.remove();
  }
}
