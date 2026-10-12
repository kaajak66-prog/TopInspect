<script setup>
import { ref, reactive, onMounted, onUnmounted, nextTick } from 'vue'
import { RouterLink } from 'vue-router'
import gsap from 'gsap'
import { api } from '../store'

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

const state = reactive({
  loading: false,
  error: '',
  hasJob: false,
  report: null, // { job_id, generated_at, model, facts, ai_sections }
})

const cmCanvas = ref(null)
const prCanvas = ref(null)
const reportRoot = ref(null)

// 动画显示值：指标卡数字滚动用（key -> 当前显示字符串）
const disp = reactive({})
// AI 报告分段：5 段，逐段打字机
const aiSections = [
  { key: 'executive_summary', title: '执行摘要', icon: 'fa-flag' },
  { key: 'threat_assessment', title: '威胁研判', icon: 'fa-shield-halved' },
  { key: 'model_evaluation', title: '模型评估', icon: 'fa-gauge-high' },
  { key: 'recommendations', title: '处置建议与防范措施', icon: 'fa-list-check' },
  { key: 'conclusion', title: '总体结论', icon: 'fa-clipboard-check' },
]
const AI_SECTIONS = aiSections
// 每段的打字机显示文本（key -> 当前已打出的字符串）
const ai = reactive({})
AI_SECTIONS.forEach(s => { ai[s.key] = '' })
ai.done = false

let tweens = []
let typeTimers = []

function fmtInt(n) {
  return (n == null) ? '—' : Number(n).toLocaleString('zh-CN')
}
function fmtPct(x, digits = 1) {
  return (x == null) ? '无标签' : (x * 100).toFixed(digits) + '%'
}
function fmtNum(x, digits = 3) {
  return (x == null) ? '—' : Number(x).toFixed(digits)
}
function fmtTime(iso) {
  if (!iso) return ''
  try { return new Date(iso).toLocaleString('zh-CN', { hour12: false }) } catch { return iso }
}

// 指标卡定义：value 为真实值，render 决定如何把动画中间值格式化成字符串
function buildMetrics(f) {
  return [
    { key: 'flows', label: '总流量', cls: 'accent', value: f.total_flows, render: v => Math.round(v).toLocaleString('zh-CN') },
    { key: 'anom', label: '异常数', cls: 'danger', value: f.anomaly_count, render: v => Math.round(v).toLocaleString('zh-CN') },
    { key: 'rate', label: '异常率', cls: 'warn', value: f.anomaly_rate * 100, render: v => v.toFixed(2) + '%' },
    { key: 'thr', label: '检测阈值', cls: 'accent', value: f.threshold, render: v => v.toFixed(4) },
    { key: 'acc', label: '准确率', cls: 'safe', value: f.accuracy == null ? null : f.accuracy * 100, render: v => v.toFixed(1) + '%', na: '无标签' },
    { key: 'f1', label: 'F1 分数', cls: 'safe', value: f.f1, render: v => v.toFixed(3), na: '—' },
    { key: 'recall', label: '召回率', cls: 'plain', value: f.recall == null ? null : f.recall * 100, render: v => v.toFixed(1) + '%', na: '无标签' },
    { key: 'fpr', label: '误报率 FPR', cls: 'plain', value: f.fpr == null ? null : f.fpr * 100, render: v => v.toFixed(2) + '%', na: '—' },
  ]
}
const metrics = ref([])

function animateCounters() {
  metrics.value.forEach((m, i) => {
    if (m.value == null) { disp[m.key] = m.na || '—'; return }
    if (reduceMotion) { disp[m.key] = m.render(m.value); return }
    disp[m.key] = m.render(0)
    const obj = { v: 0 }
    tweens.push(gsap.to(obj, {
      v: m.value,
      duration: 1.4,
      delay: 0.15 + i * 0.08,
      ease: 'power2.out',
      onUpdate: () => { disp[m.key] = m.render(obj.v) },
      onComplete: () => { disp[m.key] = m.render(m.value) },
    }))
  })
}

// 逐字打字机：把 text 按字符写入 reactive[key]
function typewriter(text, key, startDelay) {
  return new Promise(resolve => {
    if (reduceMotion || !text) { ai[key] = text || ''; resolve(); return }
    let i = 0
    const speed = 12 // ms/字（内容变长，略加速）
    const begin = setTimeout(function step() {
      ai[key] = text.slice(0, i)
      i++
      if (i <= text.length) { typeTimers.push(setTimeout(step, speed)) }
      else { ai[key] = text; resolve() }
    }, startDelay)
    typeTimers.push(begin)
  })
}

async function runTypewriters() {
  const a = state.report.ai_sections
  AI_SECTIONS.forEach(s => { ai[s.key] = '' })
  ai.done = false
  let first = true
  for (const s of AI_SECTIONS) {
    await typewriter(a[s.key] || '', s.key, first ? 400 : 120)
    first = false
  }
  ai.done = true
}

function clearAnims() {
  tweens.forEach(t => t.kill()); tweens = []
  typeTimers.forEach(t => clearTimeout(t)); typeTimers = []
}

async function generate() {
  const jobId = window._apiJobId
  if (!jobId) { state.error = ''; state.hasJob = false; return }
  clearAnims()
  state.hasJob = true
  state.loading = true
  state.error = ''
  try {
    state.report = await api.generateReport(jobId)
    metrics.value = buildMetrics(state.report.facts)
    state.loading = false       // 先关加载态，让报告正文（含 canvas）渲染出来
    await nextTick()
    drawCharts()                // 此刻 canvas 已挂载，才能拿到 ref
    animateCounters()
    runTypewriters()
  } catch (e) {
    state.error = e.message || '报告生成失败'
    state.loading = false
  }
}

function drawCharts() {
  drawConfusion()
  drawPR()
}

// 混淆矩阵：用 facts.confusion 真值
function drawConfusion() {
  const cv = cmCanvas.value
  const c = state.report && state.report.facts && state.report.facts.confusion
  if (!cv || !c) return
  const dpr = window.devicePixelRatio || 1
  const w = cv.parentElement.clientWidth - 28, h = 240
  cv.width = w * dpr; cv.height = h * dpr; cv.style.width = w + 'px'; cv.style.height = h + 'px'
  const ctx = cv.getContext('2d'); ctx.scale(dpr, dpr); ctx.clearRect(0, 0, w, h)
  const pad = 48, cell = (Math.min(w, h) - pad * 2) / 2
  const ox = (w - cell * 2) / 2
  const cm = [[c.tn, c.fp], [c.fn, c.tp]]
  const mx = Math.max(c.tn, c.fp, c.fn, c.tp, 1)
  const labels = [['TN', 'FP'], ['FN', 'TP']]
  for (let i = 0; i < 2; i++) for (let j = 0; j < 2; j++) {
    const inten = cm[i][j] / mx
    ctx.fillStyle = (i === j) ? 'rgba(0,255,135,' + (0.18 + inten * 0.7) + ')' : 'rgba(255,45,85,' + (0.18 + inten * 0.7) + ')'
    ctx.fillRect(ox + j * cell, pad + i * cell, cell - 3, cell - 3)
    ctx.fillStyle = '#fff'; ctx.textAlign = 'center'
    ctx.font = 'bold 15px "JetBrains Mono"'
    ctx.fillText(cm[i][j].toLocaleString(), ox + j * cell + cell / 2, pad + i * cell + cell / 2 + 2)
    ctx.fillStyle = 'rgba(255,255,255,0.65)'; ctx.font = '9px "JetBrains Mono"'
    ctx.fillText(labels[i][j], ox + j * cell + cell / 2, pad + i * cell + 16)
  }
  ctx.fillStyle = '#5a6e85'; ctx.font = '9px "Inter"'; ctx.textAlign = 'center'
  ctx.fillText('预测正常', ox + cell / 2, pad - 12)
  ctx.fillText('预测异常', ox + cell + cell / 2, pad - 12)
  ctx.save(); ctx.translate(ox - 14, pad + cell / 2); ctx.rotate(-Math.PI / 2)
  ctx.fillText('真实正常', 0, 0); ctx.restore()
  ctx.save(); ctx.translate(ox - 14, pad + cell + cell / 2); ctx.rotate(-Math.PI / 2)
  ctx.fillText('真实异常', 0, 0); ctx.restore()
}

// PR 曲线：复用 engine 缓存的 window._apiPrCurve（已就位的真实曲线）
function drawPR() {
  const cv = prCanvas.value
  if (!cv) return
  const dpr = window.devicePixelRatio || 1
  const w = cv.parentElement.clientWidth - 28, h = 240
  cv.width = w * dpr; cv.height = h * dpr; cv.style.width = w + 'px'; cv.style.height = h + 'px'
  const ctx = cv.getContext('2d'); ctx.scale(dpr, dpr); ctx.clearRect(0, 0, w, h)
  const padL = 42, padR = 16, padT = 16, padB = 32
  const plotW = w - padL - padR, plotH = h - padT - padB
  // 网格 + 刻度（0~1）
  ctx.strokeStyle = 'rgba(26,48,80,0.5)'; ctx.lineWidth = 0.5
  ctx.fillStyle = '#5a6e85'; ctx.font = '9px "JetBrains Mono"'
  for (let i = 0; i <= 4; i++) {
    const y = padT + plotH * i / 4
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(padL + plotW, y); ctx.stroke()
    ctx.textAlign = 'right'; ctx.fillText((1 - i / 4).toFixed(1), padL - 6, y + 3) // Precision 轴
    const x = padL + plotW * i / 4
    ctx.textAlign = 'center'; ctx.fillText((i / 4).toFixed(1), x, padT + plotH + 14) // Recall 轴
  }
  // 轴标题
  ctx.fillStyle = '#8aa0b8'; ctx.font = '10px "Inter"'
  ctx.textAlign = 'center'; ctx.fillText('Recall 召回率', padL + plotW / 2, h - 4)
  ctx.save(); ctx.translate(11, padT + plotH / 2); ctx.rotate(-Math.PI / 2)
  ctx.fillText('Precision 精确率', 0, 0); ctx.restore()
  const raw = (state.report && state.report.facts && state.report.facts.pr_curve) || window._apiPrCurve || []
  const pts = raw.map(p => [p.recall, p.precision])
  if (pts.length) {
    // 曲线下浅填充
    ctx.beginPath()
    pts.forEach((p, i) => {
      const px = padL + plotW * p[0], py = padT + plotH * (1 - p[1])
      i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py)
    })
    ctx.lineTo(padL + plotW * pts[pts.length - 1][0], padT + plotH)
    ctx.lineTo(padL + plotW * pts[0][0], padT + plotH)
    ctx.closePath()
    ctx.fillStyle = 'rgba(0,212,255,0.10)'; ctx.fill()
    // 曲线主线 + 发光
    ctx.beginPath(); ctx.strokeStyle = '#00d4ff'; ctx.lineWidth = 2.5
    ctx.shadowColor = 'rgba(0,212,255,0.6)'; ctx.shadowBlur = 8
    pts.forEach((p, i) => {
      const px = padL + plotW * p[0], py = padT + plotH * (1 - p[1])
      i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py)
    })
    ctx.stroke(); ctx.shadowBlur = 0
  } else {
    ctx.fillStyle = '#5a6e85'; ctx.font = '11px "JetBrains Mono"'; ctx.textAlign = 'center'
    ctx.fillText('无标签数据，PR 曲线不可用', w / 2, h / 2)
  }
}

function exportPDF() {
  // 导出前把动画落到终值，避免打印到半截滚动的数字 / 半句话
  clearAnims()
  metrics.value.forEach(m => { disp[m.key] = (m.value == null) ? (m.na || '—') : m.render(m.value) })
  if (state.report) {
    const a = state.report.ai_sections
    AI_SECTIONS.forEach(s => { ai[s.key] = a[s.key] || '' })
    ai.done = true
  }
  nextTick(() => window.print())
}

onMounted(() => { generate() })
onUnmounted(() => { clearAnims() })
</script>

<template>
  <div class="page-overlay active" id="page-reports">
    <!-- 极光 / 粒子氛围背景层（打印时隐藏） -->
    <div class="rep-aurora no-print" aria-hidden="true">
      <span class="aur aur-1"></span>
      <span class="aur aur-2"></span>
      <span class="aur aur-3"></span>
      <span class="rep-grid-lines"></span>
    </div>
    <div class="po-header no-print">
      <div class="po-head-left">
        <span class="po-title"><i class="fa-solid fa-chart-line"></i> AI 分析报告</span>
        <span class="po-sub">基于检测结果的智能研判</span>
      </div>
      <div class="po-actions">
        <button class="btn" :disabled="state.loading" @click="generate">
          <i class="fa-solid fa-wand-magic-sparkles"></i>
          {{ state.report ? '重新生成' : '生成 AI 报告' }}
        </button>
        <button class="btn" :disabled="!state.report" @click="exportPDF">
          <i class="fa-solid fa-file-pdf"></i> 导出 PDF
        </button>
        <RouterLink to="/topology" class="po-back"><i class="fa-solid fa-diagram-project"></i> 返回拓扑</RouterLink>
      </div>
    </div>

    <div class="po-body" id="reportsBody">
      <!-- 无 job：空态 -->
      <div v-if="!state.hasJob" class="rep-empty">
        <div class="rep-empty-ring"><i class="fa-solid fa-satellite-dish"></i></div>
        <div class="rep-empty-title">分析报告 · 暂无数据</div>
        <div class="rep-empty-sub">请先在拓扑页运行检测，结果将在此生成 AI 报告</div>
        <button class="btn" onclick="navigateTo('topology')"><i class="fa-solid fa-play"></i> 去运行检测</button>
      </div>

      <!-- 加载中：骨架 -->
      <div v-else-if="state.loading" class="rep-loading">
        <div class="rep-spinner"></div>
        <div class="rep-loading-text">正在生成分析报告，AI 研判中…</div>
      </div>

      <!-- 出错 -->
      <div v-else-if="state.error" class="rep-error">
        <i class="fa-solid fa-triangle-exclamation"></i>
        <span>{{ state.error }}</span>
        <button class="btn small" @click="generate">重试</button>
      </div>

      <!-- 报告正文 -->
      <div v-else-if="state.report" class="report-doc" ref="reportRoot">
        <!-- 报告头 -->
        <header class="rep-doc-head">
          <div>
            <h1 class="rep-doc-title">网络入侵检测分析报告</h1>
            <div class="rep-doc-meta">
              <span><i class="fa-solid fa-database"></i> {{ state.report.model.dataset }}</span>
              <span><i class="fa-solid fa-microchip"></i> {{ state.report.model.name }}</span>
              <span><i class="fa-solid fa-clock"></i> {{ fmtTime(state.report.generated_at) }}</span>
            </div>
          </div>
          <div class="rep-doc-badge" :class="state.report.ai_sections.available ? 'on' : 'off'">
            <i class="fa-solid" :class="state.report.ai_sections.available ? 'fa-robot' : 'fa-robot'"></i>
            {{ state.report.ai_sections.available ? 'AI 已生成' : 'AI 未启用（自动摘要）' }}
          </div>
        </header>

        <!-- 真实指标卡片（数字滚动） -->
        <section class="rep-section print-hide">
          <div class="rep-sec-title"><i class="fa-solid fa-chart-simple"></i> 关键指标（真实检测数据）</div>
          <div class="metric-grid">
            <div class="metric-card fx-card" v-for="m in metrics" :key="m.key">
              <div class="mc-value" :class="m.cls">{{ disp[m.key] }}</div>
              <div class="mc-label">{{ m.label }}</div>
            </div>
          </div>
        </section>

        <!-- 图表 -->
        <section class="rep-section print-hide">
          <div class="rep-charts">
            <div class="rep-chart-panel fx-card">
              <div class="rep-sec-title"><i class="fa-solid fa-chart-line"></i> PR 曲线（精确率-召回率）</div>
              <canvas ref="prCanvas"></canvas>
              <div class="chart-help">
                <p><b>横轴 Recall 召回率</b>：所有真实攻击里被抓到的比例，越高漏报越少。</p>
                <p><b>纵轴 Precision 精确率</b>：报为异常的流量里真的是攻击的比例，越高误报越少。</p>
                <p>曲线随检测阈值从松到严滑动绘制；<b>越贴近右上角，模型越好</b>。</p>
              </div>
            </div>
            <div class="rep-chart-panel fx-card">
              <div class="rep-sec-title"><i class="fa-solid fa-table-cells"></i> 混淆矩阵</div>
              <canvas ref="cmCanvas"></canvas>
              <div class="chart-help">
                <p>横向是<b>模型预测</b>，纵向是<b>真实标签</b>，对角线（绿）为判断正确：</p>
                <p><span class="tag ok">TP</span> 真攻击被抓到 ·
                   <span class="tag ok">TN</span> 正常流被放行</p>
                <p><span class="tag bad">FP</span> 正常被误判为异常（误报）·
                   <span class="tag bad">FN</span> 真攻击被漏掉（漏报）</p>
              </div>
            </div>
          </div>
        </section>

        <!-- Top 异常 IP + 攻击类型 -->
        <section class="rep-section print-hide" v-if="state.report.facts.top_anomaly_ips.length || state.report.facts.top_attack_types.length">
          <div class="rep-two-col">
            <div v-if="state.report.facts.top_anomaly_ips.length" class="rep-list-panel fx-card">
              <div class="rep-sec-title"><i class="fa-solid fa-ranking-star"></i> Top 异常源 IP</div>
              <div class="rep-rank">
                <div v-for="(ip, i) in state.report.facts.top_anomaly_ips" :key="ip.ip" class="rep-rank-row">
                  <span class="rr-idx">{{ i + 1 }}</span>
                  <span class="rr-ip">{{ ip.ip }}</span>
                  <span class="rr-type">{{ ip.attack_type }}</span>
                  <span class="rr-count">{{ fmtInt(ip.anomaly_count) }}</span>
                </div>
              </div>
            </div>
            <div v-if="state.report.facts.top_attack_types.length" class="rep-list-panel fx-card">
              <div class="rep-sec-title"><i class="fa-solid fa-bug"></i> 主要攻击类型</div>
              <div class="rep-rank">
                <div v-for="(t, i) in state.report.facts.top_attack_types" :key="t.type" class="rep-rank-row">
                  <span class="rr-idx">{{ i + 1 }}</span>
                  <span class="rr-ip">{{ t.type }}</span>
                  <span class="rr-count">{{ fmtInt(t.count) }}</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- AI 分析报告（5 段，逐段打字机浮现） -->
        <section class="rep-section ai-sections">
          <div class="ai-block fx-card" v-for="s in aiSections" :key="s.key">
            <div class="ai-block-title"><i class="fa-solid" :class="s.icon"></i> {{ s.title }}</div>
            <p class="ai-text" :class="{ typing: ai[s.key].length < (state.report.ai_sections[s.key] || '').length }">{{ ai[s.key] }}</p>
          </div>
          <div class="ai-disclaimer" v-if="!state.report.ai_sections.available">
            <i class="fa-solid fa-circle-info"></i>
            AI 分析服务未配置或暂不可用，以上文字为基于真实检测数据的自动摘要；指标卡片与图表均为真实计算结果。
          </div>
        </section>

        <footer class="rep-doc-foot">
          拓察 TopInspect · 自监督图神经网络入侵检测系统 · 报告由系统自动生成，指标为真实检测结果
        </footer>
      </div>
    </div>
  </div>
</template>

<style scoped>
.po-header { position: relative; z-index: 2; }
.po-actions { display: flex; gap: 8px; align-items: center; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── 空态 / 加载 / 错误 ── */
.rep-empty, .rep-loading { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 60vh; gap: 14px; font-family: var(--font-mono); text-align: center; }
.rep-empty-ring { width: 80px; height: 80px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 28px; color: var(--accent); border: 1px solid var(--glass-border-active); background: radial-gradient(circle, rgba(0,212,255,0.10), transparent 70%); box-shadow: 0 0 36px rgba(0,212,255,0.16); }
.rep-empty-title { font-size: 15px; letter-spacing: 2px; color: var(--text-bright); }
.rep-empty-sub { font-size: 10px; color: var(--text-dim); letter-spacing: 1px; }
.rep-spinner { width: 44px; height: 44px; border: 3px solid rgba(0,212,255,0.15); border-top-color: var(--accent); border-radius: 50%; animation: repSpin 0.9s linear infinite; }
@keyframes repSpin { to { transform: rotate(360deg); } }
.rep-loading-text { font-size: 11px; color: var(--text-dim); letter-spacing: 1px; }
.rep-error { display: flex; align-items: center; gap: 12px; padding: 16px; margin: 20px auto; max-width: 600px; border: 1px solid var(--danger-dim); border-radius: 8px; background: rgba(255,45,85,0.06); color: var(--danger); font-size: 11px; }

/* ── 报告文档 ── */
.report-doc { max-width: 980px; margin: 0 auto; }
.rep-doc-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding-bottom: 16px; margin-bottom: 20px; border-bottom: 1px solid var(--glass-border); }
.rep-doc-title { font-size: 22px; font-weight: 700; color: var(--text-bright); letter-spacing: 1px; margin-bottom: 8px; font-family: var(--font-body); }
.rep-doc-meta { display: flex; flex-wrap: wrap; gap: 16px; font-size: 10px; color: var(--text-dim); font-family: var(--font-mono); }
.rep-doc-meta i { color: var(--accent); margin-right: 4px; }
.rep-doc-badge { flex-shrink: 0; font-size: 10px; padding: 6px 12px; border-radius: 20px; font-family: var(--font-mono); white-space: nowrap; }
.rep-doc-badge.on { color: var(--safe); background: rgba(0,255,135,0.08); border: 1px solid rgba(0,255,135,0.25); }
.rep-doc-badge.off { color: var(--warn); background: rgba(255,149,0,0.08); border: 1px solid rgba(255,149,0,0.25); }

.rep-section { margin-bottom: 24px; }
.rep-sec-title { font-size: 11px; color: var(--accent); font-weight: 700; letter-spacing: 1px; margin-bottom: 12px; font-family: var(--font-body); }
.rep-sec-title i { margin-right: 6px; }

/* 指标卡 */
.metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.metric-card { background: var(--glass-bg); border: 1px solid var(--glass-border); border-radius: 10px; padding: 14px 10px; text-align: center; backdrop-filter: blur(var(--glass-blur)); -webkit-backdrop-filter: blur(var(--glass-blur)); }
.mc-value { font-size: 22px; font-weight: 700; font-family: var(--font-mono); line-height: 1.1; color: var(--text-bright); }
.mc-value.accent { color: var(--accent); }
.mc-value.danger { color: var(--danger); }
.mc-value.warn { color: var(--warn); }
.mc-value.safe { color: var(--safe); }
.mc-label { font-size: 9px; color: var(--text-dim); margin-top: 5px; font-family: var(--font-body); letter-spacing: 0.5px; }

/* 图表 */
.rep-charts { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.rep-chart-panel { background: var(--glass-bg); border: 1px solid var(--glass-border); border-radius: 10px; padding: 14px; backdrop-filter: blur(var(--glass-blur)); -webkit-backdrop-filter: blur(var(--glass-blur)); }
.rep-chart-panel canvas { width: 100%; height: 240px; display: block; }
.chart-help { margin-top: 10px; padding-top: 10px; border-top: 1px solid rgba(26,48,80,0.4); }
.chart-help p { font-size: 10px; line-height: 1.7; color: var(--text-dim); font-family: var(--font-body); margin: 0 0 3px; }
.chart-help p:last-child { margin-bottom: 0; }
.chart-help b { color: var(--text); font-weight: 600; }
.chart-help .tag { display: inline-block; font-family: var(--font-mono); font-weight: 700; font-size: 9px; padding: 1px 5px; border-radius: 4px; margin: 0 1px; }
.chart-help .tag.ok { color: var(--safe); background: rgba(0,255,135,0.12); }
.chart-help .tag.bad { color: var(--danger); background: rgba(255,45,85,0.12); }

/* 两栏排行 */
.rep-two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.rep-list-panel { background: var(--glass-bg); border: 1px solid var(--glass-border); border-radius: 10px; padding: 14px; backdrop-filter: blur(var(--glass-blur)); -webkit-backdrop-filter: blur(var(--glass-blur)); }
.rep-rank-row { display: flex; align-items: center; gap: 10px; padding: 7px 0; border-bottom: 1px solid rgba(26,48,80,0.3); font-size: 10px; font-family: var(--font-mono); }
.rep-rank-row:last-child { border-bottom: none; }
.rr-idx { color: var(--text-dim); min-width: 18px; }
.rr-ip { color: var(--text-bright); flex: 1; }
.rr-type { color: var(--warn); min-width: 90px; text-align: right; }
.rr-count { color: var(--accent); min-width: 50px; text-align: right; font-weight: 700; }

/* AI 三段 */
.ai-sections { display: flex; flex-direction: column; gap: 12px; }
.ai-block { background: linear-gradient(135deg, rgba(0,212,255,0.05) 0%, rgba(100,60,255,0.03) 100%); border: 1px solid var(--glass-border); border-left: 3px solid var(--accent); border-radius: 8px; padding: 14px 16px; }
.ai-block-title { font-size: 12px; font-weight: 700; color: var(--accent); letter-spacing: 1px; margin-bottom: 8px; font-family: var(--font-body); }
.ai-block-title i { margin-right: 6px; }
.ai-block p { font-size: 12px; line-height: 1.9; color: var(--text); font-family: var(--font-body); white-space: pre-line; }
.ai-disclaimer { display: flex; align-items: center; gap: 8px; font-size: 10px; color: var(--warn); padding: 10px 14px; border: 1px dashed rgba(255,149,0,0.3); border-radius: 8px; font-family: var(--font-mono); }

.rep-doc-foot { margin-top: 28px; padding-top: 14px; border-top: 1px solid var(--glass-border); text-align: center; font-size: 9px; color: var(--text-dim); letter-spacing: 1px; font-family: var(--font-mono); }

/* ══════════ 特效层 ══════════ */

/* 极光 / 网格氛围背景：沉到内容层之下（负 z-index），且自身不接收点击 */
.rep-aurora { position: absolute; inset: 0; z-index: 0; overflow: hidden; pointer-events: none; }
.rep-aurora .aur { position: absolute; border-radius: 50%; filter: blur(70px); opacity: 0.5; mix-blend-mode: screen; will-change: transform; }
.aur-1 { width: 50vw; height: 50vw; left: -10vw; top: -12vw; background: radial-gradient(circle, rgba(0,212,255,0.42), transparent 68%); animation: aurFloat1 17s ease-in-out infinite; }
.aur-2 { width: 42vw; height: 42vw; right: -8vw; top: 4vw; background: radial-gradient(circle, rgba(120,70,255,0.34), transparent 66%); animation: aurFloat2 21s ease-in-out infinite; }
.aur-3 { width: 38vw; height: 38vw; left: 28vw; bottom: -14vw; background: radial-gradient(circle, rgba(255,45,110,0.20), transparent 64%); animation: aurFloat3 25s ease-in-out infinite; }
@keyframes aurFloat1 { 0%,100% { transform: translate(0,0) scale(1); } 50% { transform: translate(8vw,6vw) scale(1.18); } }
@keyframes aurFloat2 { 0%,100% { transform: translate(0,0) scale(1.1); } 50% { transform: translate(-7vw,8vw) scale(0.9); } }
@keyframes aurFloat3 { 0%,100% { transform: translate(0,0) scale(1); } 50% { transform: translate(5vw,-7vw) scale(1.2); } }
/* 漂移网格线，赛博大屏底纹 */
.rep-grid-lines { position: absolute; inset: -50%; background-image: linear-gradient(rgba(0,212,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(0,212,255,0.05) 1px, transparent 1px); background-size: 38px 38px; animation: gridDrift 30s linear infinite; opacity: 0.5; }
@keyframes gridDrift { from { transform: translate(0,0); } to { transform: translate(38px,38px); } }

/* 让正文盖在氛围层之上 */
.po-body { position: relative; z-index: 1; }

/* 卡片入场：依次淡入上浮 + 内部扫光 */
.fx-card { position: relative; overflow: hidden; animation: fxCardIn 0.6s cubic-bezier(0.16,1,0.3,1) both; }
.report-doc .rep-section:nth-of-type(1) .fx-card:nth-child(1) { animation-delay: 0.05s; }
.metric-grid .fx-card:nth-child(1) { animation-delay: 0.05s; }
.metric-grid .fx-card:nth-child(2) { animation-delay: 0.11s; }
.metric-grid .fx-card:nth-child(3) { animation-delay: 0.17s; }
.metric-grid .fx-card:nth-child(4) { animation-delay: 0.23s; }
.metric-grid .fx-card:nth-child(5) { animation-delay: 0.29s; }
.metric-grid .fx-card:nth-child(6) { animation-delay: 0.35s; }
.metric-grid .fx-card:nth-child(7) { animation-delay: 0.41s; }
.metric-grid .fx-card:nth-child(8) { animation-delay: 0.47s; }
.ai-block.fx-card:nth-child(1) { animation-delay: 0.1s; }
.ai-block.fx-card:nth-child(2) { animation-delay: 0.2s; }
.ai-block.fx-card:nth-child(3) { animation-delay: 0.3s; }
@keyframes fxCardIn { from { opacity: 0; transform: translateY(16px) scale(0.98); } to { opacity: 1; transform: translateY(0) scale(1); } }
/* 震光扫过：一条高光从左上斜扫一次 */
.fx-card::after { content: ''; position: absolute; top: 0; left: -130%; width: 60%; height: 100%; background: linear-gradient(105deg, transparent, rgba(255,255,255,0.16), transparent); transform: skewX(-18deg); animation: fxSheen 1.1s ease-out 0.5s both; pointer-events: none; z-index: 3; }
@keyframes fxSheen { from { left: -130%; } to { left: 160%; } }
/* 悬停发光描边 + 抬升 */
.fx-card { transition: transform 0.3s, border-color 0.3s, box-shadow 0.3s; }
.fx-card:hover { transform: translateY(-3px); border-color: var(--glass-border-active); box-shadow: 0 14px 40px rgba(0,0,0,0.5), 0 0 22px rgba(0,212,255,0.22); }

/* 指标数字发光 */
.mc-value { text-shadow: 0 0 14px currentColor; }
.mc-value.plain { color: var(--text-bright); }

/* AI 打字机光标 */
.ai-text.typing::after { content: '▌'; color: var(--accent); margin-left: 1px; animation: caret 0.9s step-end infinite; }
@keyframes caret { 50% { opacity: 0; } }

/* 减少动效：全部静态落位 */
@media (prefers-reduced-motion: reduce) {
  .aur, .rep-grid-lines, .fx-card, .fx-card::after { animation: none !important; }
  .fx-card { opacity: 1; transform: none; }
  .fx-card::after { display: none; }
}

@media (max-width: 768px) {
  .metric-grid { grid-template-columns: repeat(2, 1fr); }
  .rep-charts, .rep-two-col { grid-template-columns: 1fr; }
}

/* 打印：关闭所有特效，背景层隐藏（no-print 已处理 .rep-aurora） */
@media print {
  .fx-card, .fx-card::after, .aur, .rep-grid-lines { animation: none !important; }
  .fx-card { opacity: 1 !important; transform: none !important; box-shadow: none !important; }
  .fx-card::after { display: none !important; }
  .mc-value { text-shadow: none !important; }
  .ai-text.typing::after { display: none !important; }
}
</style>
