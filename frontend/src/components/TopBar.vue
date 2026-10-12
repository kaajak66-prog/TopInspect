<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { navRoutes } from '../router'

const clock = ref('--:--:--')
let timer = null

function tick() {
  clock.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
}

onMounted(() => {
  tick()
  timer = setInterval(tick, 1000)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div id="topbar">
    <div class="t-left">
      <span class="sys-name"><i class="fa-solid fa-shield-halved"></i> 拓察 TopInspect · 3D 赛博作战中心</span>
      <span class="t-sep">|</span>
      <span id="tClock">{{ clock }}</span>
      <span class="t-sep">|</span>
      <span><span class="t-dot"></span> 系统运行中</span>
      <span class="t-sep">|</span>
      <span>数据集: NF-UNSW-NB15-v3</span>
    </div>
    <div class="t-right">
      <!-- 状态字段组：label-value 小块。动态 id 由 engine.js 直接写值，勿改为 Vue 绑定，勿改 id -->
      <div class="t-stats">
        <span class="t-stat"><span class="t-stat-k">威胁</span><span class="t-stat-v" style="color:var(--text-dim);" id="tThreat">待检测</span></span>
        <span class="t-stat"><span class="t-stat-k">模型</span><span class="t-stat-v" style="color:var(--accent);" id="tModel">TopInspect（拓察）</span></span>
        <span class="t-stat"><span class="t-stat-k">节点</span><span class="t-stat-v" style="color:var(--accent);" id="tNodes">0</span></span>
        <span class="t-stat"><span class="t-stat-k">边</span><span class="t-stat-v" style="color:var(--accent);" id="tEdges">0</span></span>
      </div>
      <span class="t-divider"></span>
      <!-- 导航图标组 -->
      <nav class="t-nav">
        <RouterLink v-for="r in navRoutes" :key="r.name"
          :to="'/' + r.name" class="nav-icon" active-class="active" :title="r.meta.title">
          <i class="fa-solid" :class="r.meta.icon"></i>
        </RouterLink>
      </nav>
    </div>
  </div>
</template>
