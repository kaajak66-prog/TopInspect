/**
 * 鼠标荧光发光拖尾（SOC 玻璃态科技风）。
 * 原生 canvas + rAF，零依赖。固定全屏覆盖、pointer-events:none，不挡交互。
 * 思路：鼠标每次移动 push 一个粒子，粒子带生命值递减；每帧用渐隐叠加重绘，
 * 形成一条由青色（移动）渐变到的发光尾迹，领头一个高亮核心点。
 * 触屏 / prefers-reduced-motion 下不启用。
 */
const ACCENT = [0, 212, 255];   // --accent #00d4ff
const SAFE = [0, 255, 135];     // --safe   #00ff87，快速移动时偏移配色

export function useCursorTrail() {
  if (typeof window === 'undefined') return () => {};
  const fine = window.matchMedia('(pointer: fine)').matches;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!fine || reduced) return () => {};

  const canvas = document.createElement('canvas');
  canvas.id = 'cursorTrailCanvas';
  Object.assign(canvas.style, {
    position: 'fixed', inset: '0', width: '100vw', height: '100vh',
    pointerEvents: 'none', zIndex: '9998',
  });
  document.body.appendChild(canvas);
  const ctx = canvas.getContext('2d');

  let dpr = Math.min(window.devicePixelRatio || 1, 2);
  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = window.innerWidth * dpr;
    canvas.height = window.innerHeight * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  resize();
  window.addEventListener('resize', resize);

  const particles = [];
  let mx = -100, my = -100, px = -100, py = -100, hasMoved = false;

  function onMove(e) {
    mx = e.clientX; my = e.clientY;
    if (!hasMoved) { px = mx; py = my; hasMoved = true; }
    const dx = mx - px, dy = my - py;
    const speed = Math.min(Math.hypot(dx, dy), 60);
    // 移动越快、补越多中间粒子，尾迹连贯不断点
    const steps = Math.max(1, Math.floor(speed / 6));
    for (let i = 1; i <= steps; i++) {
      particles.push({
        x: px + (dx * i) / steps,
        y: py + (dy * i) / steps,
        life: 1,
        r: 3 + Math.random() * 2,
        spd: speed,
      });
    }
    px = mx; py = my;
    if (particles.length > 260) particles.splice(0, particles.length - 260);
  }
  window.addEventListener('mousemove', onMove, { passive: true });

  let raf = 0;
  function frame() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.globalCompositeOperation = 'lighter';   // 叠加发光
    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];
      p.life -= 0.07;
      if (p.life <= 0) continue;
      const t = 1 - p.life;
      // 速度越快越偏 safe 绿，营造“高速数据流”的色相位移
      const mix = Math.min(p.spd / 60, 1) * 0.5;
      const cr = Math.round(ACCENT[0] + (SAFE[0] - ACCENT[0]) * mix);
      const cg = Math.round(ACCENT[1] + (SAFE[1] - ACCENT[1]) * mix);
      const cb = Math.round(ACCENT[2] + (SAFE[2] - ACCENT[2]) * mix);
      const radius = p.r * (1 + t * 1.4);
      const alpha = p.life * 0.22;
      const g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, radius);
      g.addColorStop(0, `rgba(${cr},${cg},${cb},${alpha})`);
      g.addColorStop(1, `rgba(${cr},${cg},${cb},0)`);
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
      ctx.fill();
    }
    // 领头核心亮点
    if (hasMoved) {
      const core = ctx.createRadialGradient(mx, my, 0, mx, my, 5);
      core.addColorStop(0, 'rgba(220,250,255,0.5)');
      core.addColorStop(0.4, `rgba(${ACCENT[0]},${ACCENT[1]},${ACCENT[2]},0.3)`);
      core.addColorStop(1, `rgba(${ACCENT[0]},${ACCENT[1]},${ACCENT[2]},0)`);
      ctx.fillStyle = core;
      ctx.beginPath();
      ctx.arc(mx, my, 5, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalCompositeOperation = 'source-over';
    // 清理已死粒子（从头部批量移除）
    while (particles.length && particles[0].life <= 0) particles.shift();
    raf = requestAnimationFrame(frame);
  }
  raf = requestAnimationFrame(frame);

  return function dispose() {
    cancelAnimationFrame(raf);
    window.removeEventListener('mousemove', onMove);
    window.removeEventListener('resize', resize);
    canvas.remove();
  };
}
