<script setup>
import { onMounted, onUnmounted, nextTick } from 'vue'
import LeftPanel from '../components/LeftPanel.vue'
import RightPanel from '../components/RightPanel.vue'
import TopologyArea from '../components/TopologyArea.vue'
import { initTopologyView, teardownTopologyView } from '../engine'

onMounted(async () => {
  await nextTick()
  initTopologyView()
})
onUnmounted(() => {
  teardownTopologyView()
})
</script>

<template>
  <div id="statsbar">
    <span>模型:</span>
    <select id="modelSelect" onchange="onModelChange()"><option value="improved">TopInspect (拓察·优化后)</option><option value="baseline">Anomal-E-CBLOF (基线)</option></select>
    <span class="t-sep">|</span>
    <button onclick="startUploadDetection()" id="btnDetect"><i class="fa-solid fa-play"></i> 开始检测</button>
    <span style="font-size:8px;color:var(--text-dim)" id="detectStatus">就绪 · 等待检测</span>
    <span style="display:none" id="replayTimeLabel"></span>
    <span class="t-sep">|</span>
    <span>流量: <span style="color:var(--accent);font-weight:700" id="ssFlows">—</span></span>
    <span>异常: <span style="color:var(--danger);font-weight:700" id="ssAnomalies">—</span></span>
    <span>召回率: <span style="color:var(--safe);font-weight:700" id="ssAcc">—</span></span>
    <span>延迟: <span style="color:var(--warn);font-weight:700" id="ssLatency">—</span></span>
  </div>
  <div id="main-area" style="display:grid; grid-template-columns: 240px 1fr 240px; gap:12px; flex:1; overflow:hidden; padding:12px;">
    <LeftPanel />
    <TopologyArea />
    <RightPanel />
  </div>

  <!-- 底部信息行（bPos/bModel/bNext 由 engine.js 按 id 更新）-->
  <div id="info-row">
    <span class="info-item"><span class="b-dot live" style="width:5px;height:5px;border-radius:50%;background:var(--safe);display:inline-block;margin-right:3px"></span> 在线</span>
    <span class="info-sep">|</span>
    <span class="info-item">威胁等级: <span class="threat-chip low" id="irThreat"><i class="fa-solid fa-shield-halved"></i> 正常</span></span>
    <span class="info-sep">|</span>
    <span class="info-item">回放进度: <span class="info-val" id="bPos">--</span></span>
    <span class="info-sep">|</span>
    <span class="info-item">当前模型: <span class="info-val" id="bModel">TopInspect (拓察 · 优化后)</span></span>
    <span class="info-sep">|</span>
    <span class="info-item">检测阈值: <span class="info-val">0.0234</span></span>
    <span class="info-sep">|</span>
    <span class="info-item">下次更新: <span class="info-val" id="bNext">--</span></span>
    <span class="info-sep">|</span>
    <span class="info-item">数据集: <span class="info-val">NF-UNSW-NB15-v3</span></span>
    <span style="margin-left:auto"><i class="fa-solid fa-shield-halved"></i> 拓察 TopInspect v4.0 · 3D 赛博模式</span>
  </div>
</template>
