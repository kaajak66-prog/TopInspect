<script setup>
import { reactive, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../store'

const state = reactive({
  loading: true,
  error: '',
  dataset: '',
  metricDefs: [],
  baseline: null,   // { id, name, subtitle, status, metrics }
  improved: null,
})

// 取当前检测 jobId（engine.js 检测成功后写到 window._apiJobId）
function currentJobId() { return window._apiJobId || null }

// 指标显示：百分比类 ×100 加 %（保留 4 位小数，避免 100% 看起来过整），延迟保留 ms，其余保留 4 位
function fmt(def, v) {
  if (v === null || v === undefined) return '--'
  if (def.unit === '%') return (v * 100).toFixed(4) + '%'
  if (def.unit === 'ms') return Math.round(v) + ' ms'
  return Number(v).toFixed(4)
}

// 进度条宽度（0-100）。百分比类直接×100；延迟做反向归一（越低条越长，封顶200ms）；其余×100
function barPct(def, v) {
  if (v === null || v === undefined) return 0
  if (def.unit === '%') return Math.min(100, v * 100)
  if (def.unit === 'ms') return Math.max(4, 100 - Math.min(100, v / 2))
  return Math.min(100, v * 100)
}

// 改进版 vs 基线：返回 { better:bool, deltaText } —— 数据齐全时才算
function verdict(def) {
  const b = state.baseline?.metrics?.[def.key]
  const im = state.improved?.metrics?.[def.key]
  if (b == null || im == null) return null
  const better = def.higherBetter ? im > b : im < b
  let delta = def.higherBetter ? (im - b) : (b - im)
  let deltaText
  if (def.unit === '%') deltaText = (delta * 100 >= 0 ? '+' : '') + (delta * 100).toFixed(4) + '%'
  else if (def.unit === 'ms') deltaText = (delta >= 0 ? '-' : '+') + Math.abs(Math.round(delta)) + 'ms'
  else deltaText = (delta >= 0 ? '+' : '') + delta.toFixed(4)
  return { better, deltaText }
}

async function load() {
  state.loading = true; state.error = ''
  try {
    const data = await api.fetchCompare(currentJobId())
    state.dataset = data.dataset
    state.metricDefs = data.metricDefs
    state.baseline = data.models.find(m => m.role === 'baseline')
    state.improved = data.models.find(m => m.role === 'improved')
  } catch (e) {
    state.error = e.message || '加载失败'
  } finally {
    state.loading = false
  }
}

onMounted(load)
</script>

<template>
  <div id="compare-view">
    <!-- 顶部 -->
    <div class="cmp-head">
      <div>
        <div class="cmp-title"><i class="fa-solid fa-scale-balanced"></i> 模型对比报告</div>
        <div class="cmp-sub">Anomal-E-CBLOF vs TopInspect（拓察·优化后） · 数据集: {{ state.dataset || '—' }}</div>
      </div>
      <div class="cmp-actions">
        <button class="cmp-btn" @click="load"><i class="fa-solid fa-rotate-right"></i> 刷新</button>
        <RouterLink to="/topology" class="cmp-btn"><i class="fa-solid fa-diagram-project"></i> 返回拓扑</RouterLink>
      </div>
    </div>

    <div v-if="state.error" class="cmp-error"><i class="fa-solid fa-triangle-exclamation"></i> {{ state.error }}</div>

    <!-- 双栏模型卡 -->
    <div class="cmp-cards">
      <div class="cmp-card baseline">
        <div class="cmp-card-tag">论文基线</div>
        <div class="cmp-card-name">{{ state.baseline?.name || 'Anomal-E-CBLOF' }}</div>
        <div class="cmp-card-desc">{{ state.baseline?.subtitle }}</div>
        <div class="cmp-card-status" :class="state.baseline?.status">
          <i class="fa-solid" :class="state.baseline?.status==='ready' ? 'fa-circle-check' : 'fa-clock'"></i>
          {{ state.baseline?.status === 'ready' ? '真实指标已就绪' : '待检测' }}
        </div>
      </div>

      <div class="cmp-vs"><i class="fa-solid fa-bolt"></i></div>

      <div class="cmp-card improved">
        <div class="cmp-card-tag improved-tag">优化后 · 主角</div>
        <div class="cmp-card-name">{{ state.improved?.name || 'TopInspect（拓察）' }}</div>
        <div class="cmp-card-desc">{{ state.improved?.subtitle }}</div>
        <div class="cmp-card-status" :class="state.improved?.status">
          <i class="fa-solid" :class="state.improved?.status==='ready' ? 'fa-circle-check' : 'fa-clock'"></i>
          {{ state.improved?.status === 'ready' ? '真实指标已就绪' : '待检测' }}
        </div>
      </div>
    </div>

    <!-- 指标对比区 -->
    <div class="cmp-metrics">
      <div class="cmp-metrics-title"><i class="fa-solid fa-chart-bar"></i> 核心指标对比</div>
      <div v-if="state.loading" class="cmp-loading">加载中...</div>
      <div v-else v-for="def in state.metricDefs" :key="def.key" class="cmp-row">
        <div class="cmp-row-label">
          {{ def.label }}
          <span class="cmp-hint">{{ def.higherBetter ? '越高越好' : '越低越好' }}</span>
        </div>
        <div class="cmp-bars">
          <!-- 基础 -->
          <div class="cmp-bar-line">
            <span class="cmp-bar-role">基础</span>
            <div class="cmp-bar-track"><div class="cmp-bar-fill base" :style="{ width: barPct(def, state.baseline?.metrics?.[def.key]) + '%' }"></div></div>
            <span class="cmp-bar-val">{{ fmt(def, state.baseline?.metrics?.[def.key]) }}</span>
          </div>
          <!-- 优化后 -->
          <div class="cmp-bar-line">
            <span class="cmp-bar-role improved">优化后</span>
            <div class="cmp-bar-track">
              <div class="cmp-bar-fill imp" :style="{ width: barPct(def, state.improved?.metrics?.[def.key]) + '%' }"></div>
            </div>
            <span class="cmp-bar-val imp">{{ fmt(def, state.improved?.metrics?.[def.key]) }}</span>
          </div>
        </div>
        <!-- 胜负/提升 -->
        <div class="cmp-delta">
          <template v-if="verdict(def)">
            <span class="cmp-delta-badge" :class="verdict(def).better ? 'win' : 'lose'">
              <i class="fa-solid" :class="verdict(def).better ? 'fa-arrow-trend-up' : 'fa-arrow-trend-down'"></i>
              {{ verdict(def).deltaText }}
            </span>
          </template>
          <span v-else class="cmp-delta-pending">待对比</span>
        </div>
      </div>
    </div>

    <div class="cmp-footer">
      <i class="fa-solid fa-circle-info"></i>
      两个模型均基于本次上传数据的真实攻击标签实时计算指标。Anomal-E-CBLOF 为论文基线（E-GraphSAGE 自监督表征 + CBLOF 聚类离群检测），绿色徽章表示 TopInspect（拓察）优化后模型相对该基线的提升幅度。
    </div>
  </div>
</template>

<style scoped>
#compare-view{height:100%;overflow-y:auto;padding:18px 22px;color:var(--text);background:linear-gradient(rgba(3,10,20,0.82),rgba(3,10,20,0.9)),url('../assets/bg-cyber.jpg');background-size:cover;background-position:center;background-attachment:fixed}
.cmp-head{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:16px}
.cmp-title{font-size:18px;font-weight:700;color:var(--accent);letter-spacing:1px}
.cmp-title i{margin-right:6px}
.cmp-sub{font-size:10px;color:var(--text-dim);margin-top:4px}
.cmp-actions{display:flex;gap:8px}
.cmp-btn{display:inline-flex;align-items:center;gap:5px;font-size:10px;padding:6px 12px;border-radius:6px;background:rgba(0,212,255,0.06);border:1px solid rgba(0,212,255,0.2);color:var(--text);cursor:pointer;text-decoration:none;font-family:var(--font-mono);transition:all 0.18s}
.cmp-btn:hover{border-color:var(--accent);color:var(--accent)}
.cmp-error{background:rgba(255,45,85,0.08);border:1px solid rgba(255,45,85,0.25);color:var(--danger);padding:8px 14px;border-radius:6px;font-size:11px;margin-bottom:14px}

.cmp-cards{display:flex;align-items:stretch;gap:14px;margin-bottom:20px}
.cmp-card{flex:1;border-radius:12px;padding:18px 20px;position:relative;overflow:hidden;backdrop-filter:blur(16px);border:1px solid}
.cmp-card.baseline{background:linear-gradient(135deg,rgba(120,140,160,0.08),rgba(120,140,160,0.02));border-color:rgba(150,170,190,0.2)}
.cmp-card.improved{background:linear-gradient(135deg,rgba(0,212,255,0.12),rgba(0,255,135,0.04));border-color:rgba(0,212,255,0.4);box-shadow:0 0 30px rgba(0,212,255,0.12)}
.cmp-card.improved.pending{border-style:dashed;opacity:0.92}
.cmp-card-tag{display:inline-block;font-size:8px;font-weight:700;padding:2px 9px;border-radius:9px;background:rgba(150,170,190,0.15);color:var(--text-dim);letter-spacing:1px;margin-bottom:10px}
.cmp-card-tag.improved-tag{background:rgba(0,212,255,0.18);color:var(--accent)}
.cmp-card-name{font-size:17px;font-weight:700;margin-bottom:3px}
.cmp-card.improved .cmp-card-name{color:var(--accent)}
.cmp-card-desc{font-size:10px;color:var(--text-dim);margin-bottom:14px}
.cmp-card-status{font-size:10px;display:inline-flex;align-items:center;gap:5px;padding:4px 10px;border-radius:8px}
.cmp-card-status.ready{background:rgba(0,255,135,0.1);color:var(--safe);border:1px solid rgba(0,255,135,0.25)}
.cmp-card-status.waiting{background:rgba(150,170,190,0.1);color:var(--text-dim);border:1px solid rgba(150,170,190,0.2)}
.cmp-card-status.pending{background:rgba(255,149,0,0.1);color:var(--warn);border:1px solid rgba(255,149,0,0.25)}
.cmp-vs{display:flex;align-items:center;justify-content:center;width:44px;color:var(--accent);font-size:18px;filter:drop-shadow(0 0 6px rgba(0,212,255,0.5))}

.cmp-metrics{background:rgba(6,14,26,0.5);border:1px solid rgba(0,212,255,0.12);border-radius:12px;padding:16px 18px}
.cmp-metrics-title{font-size:12px;font-weight:700;color:var(--text-bright);margin-bottom:14px;letter-spacing:0.5px}
.cmp-metrics-title i{margin-right:6px;color:var(--accent)}
.cmp-loading{font-size:11px;color:var(--text-dim);padding:20px;text-align:center}
.cmp-row{display:grid;grid-template-columns:130px 1fr 92px;gap:14px;align-items:center;padding:11px 0;border-bottom:1px solid rgba(255,255,255,0.04)}
.cmp-row:last-child{border-bottom:none}
.cmp-row-label{font-size:11px;font-weight:600}
.cmp-hint{display:block;font-size:8px;color:var(--text-dim);margin-top:2px;font-weight:400}
.cmp-bars{display:flex;flex-direction:column;gap:6px}
.cmp-bar-line{display:flex;align-items:center;gap:8px}
.cmp-bar-role{font-size:8px;color:var(--text-dim);width:34px;flex-shrink:0}
.cmp-bar-role.improved{color:var(--accent)}
.cmp-bar-track{flex:1;height:10px;background:rgba(10,20,38,0.7);border-radius:5px;overflow:hidden;position:relative}
.cmp-bar-fill{height:100%;border-radius:5px;transition:width 0.6s cubic-bezier(0.16,1,0.3,1)}
.cmp-bar-fill.base{background:linear-gradient(90deg,#5a6e85,#8fa6bd)}
.cmp-bar-fill.imp{background:linear-gradient(90deg,#006994,#00d4ff);box-shadow:0 0 8px rgba(0,212,255,0.4)}
.cmp-bar-pending{position:absolute;left:8px;top:50%;transform:translateY(-50%);font-size:8px;color:var(--warn);letter-spacing:1px}
.cmp-bar-val{font-size:11px;font-weight:700;font-family:var(--font-mono);width:64px;text-align:right;color:var(--text-dim)}
.cmp-bar-val.imp{color:var(--accent)}
.cmp-delta{text-align:center}
.cmp-delta-badge{font-size:10px;font-weight:700;padding:3px 9px;border-radius:8px;display:inline-flex;align-items:center;gap:4px;font-family:var(--font-mono)}
.cmp-delta-badge.win{background:rgba(0,255,135,0.12);color:var(--safe);border:1px solid rgba(0,255,135,0.3)}
.cmp-delta-badge.lose{background:rgba(255,45,85,0.1);color:var(--danger);border:1px solid rgba(255,45,85,0.25)}
.cmp-delta-pending{font-size:9px;color:var(--text-dim)}
.cmp-footer{margin-top:16px;font-size:10px;color:var(--text-dim);line-height:1.7;padding:12px 14px;background:rgba(0,212,255,0.03);border-radius:8px;border:1px solid rgba(0,212,255,0.08)}
.cmp-footer i{color:var(--accent);margin-right:5px}
</style>
