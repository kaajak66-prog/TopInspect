import * as THREE from 'three'
import { reduceMotion } from '../store'

// 搬自老版 graph-v4-3d.html 的 initBg：星场 + 双层网格 + 鼠标视差 + resize + anim 循环。
// 渲染逻辑原样保留，仅改为挂在传入的 canvas 上、返回 dispose 供卸载清理。
export function useBackground3D(canvas) {
  if (!canvas) return () => {}

  let bgScene, bgCamera, bgRenderer, bgParticles, bgGrid
  let _bgMX = 0, _bgMY = 0
  let rafId = null

  bgScene = new THREE.Scene()
  bgCamera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 500)
  bgCamera.position.z = 50
  bgCamera.position.y = -5
  bgRenderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: false })
  bgRenderer.setSize(window.innerWidth, window.innerHeight)
  bgRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5))

  // Starfield
  const N = 1200
  const g = new THREE.BufferGeometry()
  const p = new Float32Array(N * 3)
  const cl = new Float32Array(N * 3)
  for (let i = 0; i < N; i++) {
    p[i * 3] = (Math.random() - 0.5) * 180
    p[i * 3 + 1] = (Math.random() - 0.5) * 100
    p[i * 3 + 2] = (Math.random() - 0.5) * 60
    const r = Math.random()
    cl[i * 3] = r < 0.7 ? 0 : r < 0.9 ? 1 : 1
    cl[i * 3 + 1] = r < 0.7 ? 0.7 + Math.random() * 0.3 : r < 0.9 ? 0.3 + Math.random() * 0.3 : 0.5 + Math.random() * 0.5
    cl[i * 3 + 2] = r < 0.7 ? 1 : r < 0.9 ? 0.2 : 0
  }
  g.setAttribute('position', new THREE.BufferAttribute(p, 3))
  g.setAttribute('color', new THREE.BufferAttribute(cl, 3))
  bgParticles = new THREE.Points(g, new THREE.PointsMaterial({
    size: 0.15, vertexColors: true, blending: THREE.AdditiveBlending,
    depthWrite: false, transparent: true, opacity: 0.75,
  }))
  bgScene.add(bgParticles)

  // Grid（双层）
  bgGrid = new THREE.GridHelper(110, 28, 0x00d4ff, 0x003355)
  bgGrid.position.y = -22
  bgGrid.material.opacity = 0.12
  bgGrid.material.transparent = true
  bgScene.add(bgGrid)
  const g2 = new THREE.GridHelper(110, 55, 0x005577, 0x001122)
  g2.position.y = -22
  g2.material.opacity = 0.06
  g2.material.transparent = true
  bgScene.add(g2)

  function onMouseMove(e) {
    _bgMX = (e.clientX / window.innerWidth) * 2 - 1
    _bgMY = -(e.clientY / window.innerHeight) * 2 + 1
  }
  function onResize() {
    bgCamera.aspect = window.innerWidth / window.innerHeight
    bgCamera.updateProjectionMatrix()
    bgRenderer.setSize(window.innerWidth, window.innerHeight)
  }
  document.addEventListener('mousemove', onMouseMove)
  window.addEventListener('resize', onResize)

  function anim() {
    rafId = requestAnimationFrame(anim)
    if (bgParticles) {
      bgParticles.rotation.y += 0.00008
      bgParticles.position.x += (_bgMX * 2.5 - bgParticles.position.x) * 0.015
      bgParticles.position.y += (_bgMY * 1.5 - bgParticles.position.y) * 0.015
    }
    if (bgGrid) {
      bgGrid.position.x += (_bgMX * 1 - bgGrid.position.x) * 0.012
    }
    bgRenderer.render(bgScene, bgCamera)
  }
  // reduceMotion 时只渲染一帧静态画面，不跑循环
  if (reduceMotion) {
    bgRenderer.render(bgScene, bgCamera)
  } else {
    anim()
  }

  return function dispose() {
    if (rafId) cancelAnimationFrame(rafId)
    document.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('resize', onResize)
    bgRenderer.dispose()
    g.dispose()
  }
}
