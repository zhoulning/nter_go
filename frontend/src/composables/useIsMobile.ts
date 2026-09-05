import { ref } from 'vue'

const QUERY = '(max-width: 767.98px)'
const isMobile = ref(false)
let inited = false

function update() {
  isMobile.value = window.matchMedia(QUERY).matches
}

/** 是否移动端布局（<768px）。模块级单例，多处使用共享同一份状态 */
export function useIsMobile() {
  if (!inited) {
    inited = true
    update()
    window.matchMedia(QUERY).addEventListener('change', update)
  }
  return isMobile
}
