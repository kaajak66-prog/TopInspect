<template>
  <div id="right-panel">
    <div class="ratio-tilt-card" id="ratioTiltCard" style="position:relative; width:100%; padding:0; flex:0 0 auto; height:160px; overflow:visible; transform-style:preserve-3d; background:transparent; border:none; box-shadow:none; margin-bottom:12px;">
      <div style="position:absolute; inset:0; border-radius:1rem; background:linear-gradient(135deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.01) 100%); border:1px solid rgba(255,255,255,0.05); box-shadow:inset 0 1px 1px rgba(255,255,255,0.1), 0 30px 60px rgba(0,0,0,0.6); backdrop-filter:blur(24px); transform-style:preserve-3d; display:flex; align-items:center; justify-content:center;">
        <div class="mouse-glow" id="ratioGlow" style="position:absolute; width:120px; height:120px; border-radius:50%; background:radial-gradient(circle, rgba(0,212,255,0.15) 0%, transparent 70%); pointer-events:none; mix-blend-mode:screen; transform:translate(-50%, -50%) translateZ(15px); opacity:0;"></div>
        <div class="card-core" style="position:absolute; inset:8px; border-radius:calc(1rem - 8px); background:radial-gradient(circle at 50% 0%, rgba(0,212,255,0.08), transparent 60%); border:1px solid rgba(0,212,255,0.05); transform:translateZ(10px); transform-style:preserve-3d;">
          <div class="ring-track" style="position:absolute; inset:0; margin:auto; width:100px; height:100px; border-radius:50%; border:2px solid rgba(255,255,255,0.03); box-shadow:inset 0 0 30px rgba(0,212,255,0.03); transform:translateZ(20px);"></div>
          <div class="ring-data" style="position:absolute; inset:0; margin:auto; width:100px; height:100px; transform:translateZ(40px); filter:drop-shadow(0 0 12px rgba(0,212,255,0.4));">
            <svg width="100" height="100" viewBox="0 0 100 100" style="overflow:visible">
              <defs>
                <linearGradient id="neonGlowRatio" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stop-color="#4df0ff" /><stop offset="50%" stop-color="#00d4ff" /><stop offset="100%" stop-color="#0055ff" />
                </linearGradient>
                <linearGradient id="neonGlowRed" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stop-color="#ff6b80" /><stop offset="50%" stop-color="#ff2d55" /><stop offset="100%" stop-color="#991122" />
                </linearGradient>
                <filter id="blurGlowRatio">
                  <feGaussianBlur stdDeviation="4" result="coloredBlur"/>
                  <feMerge><feMergeNode in="coloredBlur"/><feMergeNode in="SourceGraphic"/></feMerge>
                </filter>
              </defs>
              <circle id="ratioSvgCircle" cx="50" cy="50" r="40" fill="none" stroke="url(#neonGlowRatio)" stroke-width="8" stroke-linecap="round" stroke-dasharray="251.32" stroke-dashoffset="251.32" filter="url(#blurGlowRatio)" transform="rotate(-90 50 50)" />
            </svg>
          </div>
          <div class="center-data" style="position:absolute; inset:0; margin:auto; display:flex; flex-direction:column; align-items:center; justify-content:center; transform:translateZ(60px);">
            <div id="ratioNumber" style="font-family:'JetBrains Mono', monospace; font-size:24px; font-weight:bold; background:linear-gradient(180deg, #ffffff 0%, #a0c4d8 100%); -webkit-background-clip:text; -webkit-text-fill-color:transparent; margin:0; line-height:1; letter-spacing:-1px;">--</div>
            <div style="font-size:7px; color:#5a6e85; letter-spacing:2px; text-transform:uppercase; margin-top:4px; font-weight:600;">异常占比</div>
          </div>
        </div>
      </div>
      <div id="ratioLabel" style="position:absolute; bottom:-18px; left:0; width:100%; text-align:center; font-size:8px; color:var(--text-dim); transform:translateZ(10px);">等待数据...</div>
    </div>

    <div class="card spot" style="padding:8px 10px;flex:0 0 auto;">
      <div class="spot-glow"></div>
      <div class="card-title titlefx" style="margin-bottom:5px;"><i class="fa-solid fa-wave-square tfx-ico"></i> 异常时间轴</div>
      <div class="timeline-scroll">
        <canvas id="chartTimeline" style="height:95px;display:block"></canvas>
      </div>
      <div class="chart-legend">
        <span class="cl-item"><span class="cl-dot" style="background:#00d4ff"></span>每步异常数</span>
        <span class="cl-item" style="margin-left:auto;color:var(--text-dim)">横轴: 时间步 →</span>
      </div>
    </div>
    <div class="card spot" style="padding:8px 10px;flex:0 0 auto;">
      <div class="spot-glow"></div>
      <div class="card-title titlefx" style="margin-bottom:5px;"><i class="fa-solid fa-chart-column tfx-ico"></i> 分数分布</div>
      <canvas id="chartScoreDist" class="mini-chart"></canvas>
      <div class="chart-legend">
        <span class="cl-item"><span class="cl-dot" style="background:#00d4ff"></span>正常</span>
        <span class="cl-item"><span class="cl-dot" style="background:#ff2d55"></span>异常</span>
        <span class="cl-item" style="margin-left:auto;color:var(--text-dim)">横轴: 异常分数 0→1</span>
      </div>
    </div>
    <div class="card spot" style="padding:8px 10px;flex:1 1 auto;min-height:140px;">
      <div class="spot-glow"></div>
      <div class="card-title titlefx" style="margin-bottom:6px;"><i class="fa-solid fa-bug tfx-ico"></i> 攻击类型分布</div>
      <div id="attackTypeDist" class="atk-dist">
        <div class="atk-empty">暂无攻击 · 等待检测数据...</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'

// Spotlight：右面板卡片 hover 跟随光晕（与左面板一致）
let panel = null
function onMove(e) {
  const card = e.target.closest?.('.card.spot')
  if (!card) return
  const r = card.getBoundingClientRect()
  card.style.setProperty('--mx', (e.clientX - r.left) + 'px')
  card.style.setProperty('--my', (e.clientY - r.top) + 'px')
}
onMounted(() => {
  panel = document.getElementById('right-panel')
  panel?.addEventListener('mousemove', onMove)
})
onUnmounted(() => {
  panel?.removeEventListener('mousemove', onMove)
})
</script>
