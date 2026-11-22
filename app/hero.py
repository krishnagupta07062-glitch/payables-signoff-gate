"""Landing hero for the Demo tab: the headline beside an interactive dot field.

Dots stream along arcs into a dotted gate line. Most pass (ink), some are stopped at the gate (red), some
wait there for a moment before going through (amber), the way the gate treats ALLOW, BLOCK and ESCALATE.
The grid of dots leans away from the pointer; a click releases a burst. Purely visual; it reads and
changes nothing. Motion stops under prefers-reduced-motion and while the tab is hidden.
"""
from __future__ import annotations

import streamlit.components.v1 as components

HEADLINE = "Pay each invoice once."
HIGHLIGHT = "Never change a bank account on an email's word."

_HTML = """<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400..600&display=swap" rel="stylesheet">
<style>
  :root { --canvas:#F4F2EE; --ink:#141414; --lime:#E4F222; }
  html, body { margin:0; height:100%; background:var(--canvas); overflow:hidden; }
  .hero { display:grid; grid-template-columns: minmax(0,1.05fr) minmax(0,1fr); height:100%; align-items:center; }
  h1 { font-family:'Geist', system-ui, sans-serif; font-weight:500; color:var(--ink); margin:0;
       font-size:clamp(2.5rem, 4.8vw, 4.7rem); line-height:1.02; letter-spacing:-0.048em; max-width:13ch;
       text-wrap:balance; font-feature-settings:'ss01';
       animation: rise .7s cubic-bezier(.2,.7,.2,1) both; }
  mark { background:linear-gradient(transparent 64%, var(--lime) 64%); color:inherit; padding:0 .04em; }
  canvas { width:100%; height:100%; display:block; cursor:crosshair; }
  @keyframes rise { from { opacity:0; transform:translateY(10px); } to { opacity:1; transform:none; } }
  @media (max-width: 760px) { .hero { grid-template-columns:1fr; grid-template-rows:auto 1fr; }
    h1 { padding-top:.4rem; } }
  @media (prefers-reduced-motion: reduce) { h1 { animation:none; } }
</style></head><body>
<div class="hero"><h1>__HEADLINE__ <mark>__HIGHLIGHT__</mark></h1><canvas id="c" aria-hidden="true"></canvas></div>
<script>
(() => {
  const cv = document.getElementById('c'), cx = cv.getContext('2d');
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const INK = [20,20,20], RED = [209,59,42], AMBER = [245,165,36];
  const GAP = 18;
  let W = 0, H = 0, dpr = 1, dots = [], shots = [], sparks = [], mouse = {x:-1e4, y:-1e4}, gateX = 0, t0 = 0;

  function size() {
    dpr = Math.min(devicePixelRatio || 1, 2);
    W = cv.clientWidth; H = cv.clientHeight;
    cv.width = W * dpr; cv.height = H * dpr; cx.setTransform(dpr, 0, 0, dpr, 0, 0);
    gateX = W * 0.62; dots = [];
    for (let y = GAP / 2; y < H; y += GAP) for (let x = GAP / 2; x < W; x += GAP) dots.push({x, y, ox:0, oy:0});
  }

  function spawn(burst) {
    const r = Math.random(), kind = r < 0.68 ? 'pass' : r < 0.86 ? 'block' : 'wait';
    const y0 = H * (0.18 + Math.random() * 0.64), y1 = H * (0.3 + Math.random() * 0.4);
    shots.push({kind, t:0, y0, y1, lift: H * (0.12 + Math.random() * 0.22) * (Math.random() < .5 ? 1 : -1),
                speed: (burst ? 1.4 : 1) * (0.0042 + Math.random() * 0.002), hold: 0, trail: []});
  }

  function at(s, u) {               // quadratic arc from the left edge to the gate, then straight on
    if (u <= 1) {
      const x = gateX * u, k = 4 * u * (1 - u);
      return {x, y: s.y0 + (s.y1 - s.y0) * u - s.lift * k};
    }
    return {x: gateX + (u - 1) * gateX, y: s.y1};
  }

  function burst(x, y) {
    for (let i = 0; i < 14; i++) {
      const a = Math.random() * Math.PI * 2, v = 0.6 + Math.random() * 1.8;
      sparks.push({x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: 1});
    }
  }

  function rgba(c, a) { return `rgba(${c[0]},${c[1]},${c[2]},${a})`; }

  function frame(now) {
    const dt = Math.min(48, now - (t0 || now)); t0 = now;
    cx.clearRect(0, 0, W, H);

    // dot grid, leaning away from the pointer
    for (const d of dots) {
      const dx = d.x - mouse.x, dy = d.y - mouse.y, dist = Math.hypot(dx, dy), R = 110;
      let tx = 0, ty = 0, near = 0;
      if (dist < R) { near = 1 - dist / R; const f = near * near * 14; tx = dx / (dist || 1) * f; ty = dy / (dist || 1) * f; }
      d.ox += (tx - d.ox) * 0.14; d.oy += (ty - d.oy) * 0.14;
      cx.fillStyle = near > 0.55 ? rgba(INK, 0.55) : rgba(INK, 0.13 + near * 0.3);
      cx.beginPath(); cx.arc(d.x + d.ox, d.y + d.oy, 1.05 + near * 1.6, 0, 6.283); cx.fill();
    }

    // the gate: a dotted vertical line
    for (let y = 6; y < H; y += 7) { cx.fillStyle = rgba(INK, 0.35); cx.fillRect(gateX - 0.75, y, 1.5, 2.5); }

    // projectiles with dotted trails
    if (!still && Math.random() < dt / 520) spawn(false);
    for (const s of shots) {
      if (s.kind === 'wait' && s.t >= 1 && s.hold < 900) s.hold += dt;
      else if (!(s.kind === 'block' && s.t >= 1)) s.t += s.speed * dt / 16;
      if (s.kind === 'block' && s.t >= 1 && !s.hit) { s.t = 1; s.hit = true; const p = at(s, 1); burst(p.x, p.y); }
      const p = at(s, s.t);
      if (!s.hit) { s.trail.push(p); if (s.trail.length > 26) s.trail.shift(); }
      else if (s.trail.length) s.trail.shift();
      const col = s.kind === 'block' ? RED : s.kind === 'wait' && s.t >= 1 && s.hold < 900 ? AMBER
                : s.kind === 'wait' && s.t < 1 ? AMBER : INK;
      s.trail.forEach((q, i) => {
        if (i % 2) return;
        cx.fillStyle = rgba(col, 0.08 + 0.6 * i / s.trail.length);
        cx.beginPath(); cx.arc(q.x, q.y, 1.1 + 1.4 * i / s.trail.length, 0, 6.283); cx.fill();
      });
      if (!s.hit) {
        if (s.kind === 'wait' && s.t >= 1 && s.hold < 900) {   // waiting at the gate: a breathing ring
          cx.strokeStyle = rgba(AMBER, 0.5 + 0.4 * Math.sin(now / 120)); cx.lineWidth = 1.5;
          cx.beginPath(); cx.arc(p.x, p.y, 7, 0, 6.283); cx.stroke();
        }
        cx.fillStyle = rgba(col, 1); cx.beginPath(); cx.arc(p.x, p.y, 3.4, 0, 6.283); cx.fill();
      }
    }
    shots = shots.filter(s => at(s, s.t).x < W + 20 && !(s.hit && !s.trail.length));

    for (const k of sparks) {
      k.x += k.vx; k.y += k.vy; k.vx *= 0.94; k.vy *= 0.94; k.life -= dt / 700;
      cx.fillStyle = rgba(RED, Math.max(0, k.life) * 0.8); cx.beginPath(); cx.arc(k.x, k.y, 1.6, 0, 6.283); cx.fill();
    }
    sparks = sparks.filter(k => k.life > 0);

    if (!still && !document.hidden) requestAnimationFrame(frame);
  }

  cv.addEventListener('pointermove', e => { const r = cv.getBoundingClientRect(); mouse = {x: e.clientX - r.left, y: e.clientY - r.top}; if (still) frame(performance.now()); });
  cv.addEventListener('pointerleave', () => { mouse = {x:-1e4, y:-1e4}; if (still) frame(performance.now()); });
  cv.addEventListener('pointerdown', () => { for (let i = 0; i < 6; i++) setTimeout(() => spawn(true), i * 70); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden && !still) { t0 = 0; requestAnimationFrame(frame); } });
  addEventListener('resize', size);
  size();
  if (still) { frame(performance.now()); }
  else { for (let i = 0; i < 4; i++) spawn(false); requestAnimationFrame(frame); }
})();
</script></body></html>"""


def render(height: int = 340) -> None:
    components.html(_HTML.replace("__HEADLINE__", HEADLINE).replace("__HIGHLIGHT__", HIGHLIGHT), height=height)
