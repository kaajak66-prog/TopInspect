<template>
<div id="left-panel">
      <div class="card spot">
        <div class="spot-glow"></div>
        <div class="card-title titlefx"><i class="fa-solid fa-gauge-high tfx-ico"></i> 实时统计</div>
        <div class="stat-row">
          <div class="stat-cell"><div class="val" style="color:var(--accent)" id="lcFlows">—</div><div class="lbl">总流量</div></div>
          <div class="stat-cell"><div class="val" style="color:var(--danger)" id="lcAnomalies">—</div><div class="lbl">异常数</div></div>
        </div>
        <div class="stat-row">
          <div class="stat-cell"><div class="val" style="color:var(--safe)" id="lcAcc">—</div><div class="lbl">召回率</div></div>
          <div class="stat-cell"><div class="val" style="color:var(--warn)" id="lcLatency">—</div><div class="lbl">延迟</div></div>
        </div>
      </div>
      <div class="card spot">
        <div class="spot-glow"></div>
        <div class="card-title titlefx"><i class="fa-solid fa-shield-virus tfx-ico"></i> 威胁概览</div>
        <div class="threat-grid">
          <div class="threat-cell critical"><div class="tc-num" id="tovCritical">0</div><div class="tc-lbl">危险节点</div></div>
          <div class="threat-cell warning"><div class="tc-num" id="tovWarning">0</div><div class="tc-lbl">警告节点</div></div>
          <div class="threat-cell safe"><div class="tc-num" id="tovSafe">0</div><div class="tc-lbl">安全节点</div></div>
        </div>
        <div class="threat-meter">
          <div class="tm-label"><span>受影响节点占比</span><span id="tovAffectedPct">0%</span></div>
          <div class="tm-track"><div class="tm-fill" id="tovAffectedBar" style="width:0%"></div></div>
        </div>
        <div class="threat-foot">
          <span><i class="fa-solid fa-network-wired"></i> 活跃连接 <b id="tovEdges">0</b></span>
          <span><i class="fa-solid fa-bolt"></i> 攻击流 <b id="tovAttackFlows">0</b></span>
        </div>
      </div>
      <div class="card spot">
        <div class="spot-glow"></div>
        <div class="card-title titlefx"><i class="fa-solid fa-microchip tfx-ico"></i> 检测模型</div>
        <button class="model-btn active" data-model="improved" onclick="selectModel('improved',this)"><span class="check">&#10003;</span> TopInspect（拓察）<div class="model-sub">Graph AutoEncoder · 低误报优化版</div></button>
        <button class="model-btn" data-model="baseline" onclick="selectModel('baseline',this)"><span class="check">&#10003;</span> Anomal-E-CBLOF<div class="model-sub">E-GraphSAGE + CBLOF · 论文基线</div></button>
        <div style="display:flex;align-items:center;gap:6px;margin-top:8px">
          <span id="modelRunBadgeSup" class="run-badge idle"><span class="rb-dot"></span>TopInspect: 未运行</span>
          <RouterLink to="/compare" class="run-badge idle" style="text-decoration:none;cursor:pointer"><span class="rb-dot"></span>对比报告 &rsaquo;</RouterLink>
        </div>
      </div>
      <div class="card spot">
        <div class="spot-glow"></div>
        <div class="card-title titlefx"><i class="fa-solid fa-circle-play tfx-ico"></i> 回放控制</div>
        <div class="replay-btns">
          <button onclick="replaySkipBack()" title="回到起点"><i class="fa-solid fa-backward"></i></button>
          <button onclick="replayStepBack()" title="上一步"><i class="fa-solid fa-caret-left"></i></button>
          <button onclick="toggleReplay()" id="btnPlayPause"><i class="fa-solid fa-play"></i></button>
          <button onclick="replayStepForward()" title="下一步"><i class="fa-solid fa-caret-right"></i></button>
          <button onclick="replaySkipForward()" title="跳到结尾"><i class="fa-solid fa-forward"></i></button>
        </div>
        <button onclick="resetReplayData()" style="width:100%;margin-top:6px;padding:4px;background:rgba(255,45,85,0.06);border:1px solid rgba(255,45,85,0.15);color:var(--danger);font-size:8px;font-family:var(--font-mono);border-radius:3px;cursor:pointer;transition:all 0.2s"><i class="fa-solid fa-rotate-left"></i> 重置全部数据</button>
        <div class="replay-progress" style="max-width:none"><div class="fill" id="replayFill2"></div></div>
        <div style="display:flex;justify-content:space-between;align-items:center;font-size:9px;color:var(--text-dim);margin-top:4px;font-family:var(--font-mono)">
          <span id="replayCurrent">00:00</span>
          <span class="replay-pct" id="replayPct">0%</span>
          <span id="replaySpeed">1x</span>
          <span id="replayTotal">00:00</span>
        </div>
      </div>
      <!-- Upload card -->
      <div class="card spot" style="padding:10px;flex-shrink:0" id="uploadCard">
        <div class="spot-glow"></div>
        <div class="card-title titlefx" style="margin-bottom:6px"><i class="fa-solid fa-cloud-arrow-up tfx-ico"></i> 数据上传</div>
        <div class="upload-drop-zone" id="uploadDropZone" onclick="document.getElementById('uploadFileInput').click()" style="border:1px dashed var(--glass-border);border-radius:8px;padding:12px;text-align:center;cursor:pointer;transition:border-color 0.2s,background 0.2s;font-size:9px;color:var(--text-dim);margin-bottom:7px">
          <i class="fa-solid fa-cloud-arrow-up" style="font-size:18px;display:block;margin-bottom:5px;color:var(--accent)"></i>
          拖放或点击选择 NetFlow CSV
        </div>
        <input type="file" id="uploadFileInput" accept=".csv" style="display:none" onchange="handleUploadFile(event)">
        <div style="font-size:9px;color:var(--text-dim);margin-bottom:6px;min-height:14px" id="uploadFileName">未选择文件</div>
        <div class="progress-track" style="margin-bottom:6px"><div class="progress-fill" id="uploadProgressFill" style="width:0%;background:var(--accent)"></div></div>
        <div style="display:flex;justify-content:space-between;font-size:9px;color:var(--text-dim);font-family:var(--font-mono)">
          <span id="uploadProgressLabel">等待上传...</span>
          <span id="uploadProgressPct">0%</span>
        </div>
        <button class="btn small" onclick="startUploadDetection()" id="btnUploadDetect" style="width:100%;margin-top:7px;font-size:10px;padding:6px"><i class="fa-solid fa-play"></i> 开始检测</button>
      </div>
    </div>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import { RouterLink } from 'vue-router'

// Spotlight：卡片 hover 时让光晕跟随鼠标（借鉴 ReactBits SpotlightCard）
let panel = null
function onMove(e) {
  const card = e.target.closest?.('.card.spot')
  if (!card) return
  const r = card.getBoundingClientRect()
  card.style.setProperty('--mx', (e.clientX - r.left) + 'px')
  card.style.setProperty('--my', (e.clientY - r.top) + 'px')
}
onMounted(() => {
  panel = document.getElementById('left-panel')
  panel?.addEventListener('mousemove', onMove)
})
onUnmounted(() => {
  panel?.removeEventListener('mousemove', onMove)
})
</script>
