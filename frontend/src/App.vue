<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import TopBar from './components/TopBar.vue'
import IntroOverlay from './components/IntroOverlay.vue'
import { useBackground3D } from './composables/useBackground3D'
import { useCursorTrail } from './composables/useCursorTrail'
import { initEngine, setNavFn, setCurrentPage } from './engine'

const isIntroVisible = ref(true)
const bgCanvas = ref(null)
const router = useRouter()
let disposeBg = null
let disposeTrail = null

function handleIntroFinish() {
  isIntroVisible.value = false
  // 开机动画结束后始终落到拓扑页（避免刷新时停留在 #/reports 等子页）
  if (router.currentRoute.value.name !== 'topology') router.replace('/topology')
}

onMounted(() => {
  disposeBg = useBackground3D(bgCanvas.value)
  disposeTrail = useCursorTrail()
  // 引擎内部请求跳转时（如检测后切回拓扑）走 Vue Router
  setNavFn((page) => router.push('/' + page))
  router.afterEach((to) => setCurrentPage(to.name || 'topology'))
  // 诊断：抓“自动跳上传页”的元凶——记录每次跳转到 upload 的来源页 + 调用栈。
  router.beforeEach((to, from) => {
    if (to.name === 'upload') {
      console.warn('[跳转诊断] 即将进入上传页，来自:', from.name, '\n调用栈:', new Error().stack)
    }
    return true
  })
  setCurrentPage(router.currentRoute.value.name || 'topology')
  initEngine()
})
onUnmounted(() => {
  if (disposeBg) disposeBg()
  if (disposeTrail) disposeTrail()
})
</script>

<template>
  <!-- 跨路由持久的 three.js 背景星场 -->
  <canvas id="bg3dCanvas" ref="bgCanvas"></canvas>

  <IntroOverlay v-if="isIntroVisible" @finish="handleIntroFinish" />

  <div id="app-shell" v-show="!isIntroVisible">
    <TopBar />
    <RouterView />
  </div>
</template>

<style>
#bg3dCanvas { position: fixed; inset: 0; width: 100vw; height: 100vh; z-index: 0; pointer-events: none; }
#app-shell { position: relative; z-index: 1; display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
</style>
