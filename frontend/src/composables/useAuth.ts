/** 登录态全局状态：App.vue 据此决定展示登录页还是应用壳。 */
import { computed, reactive } from 'vue'
import type { AuthUser } from '../api'

interface AuthState {
  user: AuthUser | null
  /** 是否已完成首次登录态检查（避免登录页闪烁） */
  ready: boolean
}

const state = reactive<AuthState>({ user: null, ready: false })

export const isAdmin = computed(() => state.user?.role === 'admin')
/** 内置超级管理员账号（admin）：系统配置（AI/浏览器/知识库/注册）仅它可见可改 */
export const isBuiltinAdmin = computed(() => state.user?.username === 'admin')
export const displayName = computed(
  () => state.user?.display_name || state.user?.username || '',
)

async function authRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch('/api' + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error((body as { detail?: string }).detail ?? `请求失败 (${res.status})`)
  }
  return res.json() as Promise<T>
}

export function useAuth() {
  async function fetchMe() {
    try {
      state.user = await authRequest<AuthUser>('/auth/me')
    } catch {
      state.user = null
    } finally {
      state.ready = true
    }
  }

  async function login(username: string, password: string) {
    const user = await authRequest<AuthUser>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
    state.user = user
    return user
  }

  async function register(username: string, password: string, displayName: string) {
    return authRequest<{ status: string; message: string }>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, password, display_name: displayName || null }),
    })
  }

  async function logout() {
    try {
      await authRequest('/auth/logout', { method: 'POST' })
    } finally {
      state.user = null
    }
  }

  return { state, fetchMe, login, register, logout }
}

/** api.ts 捕获到业务接口 401 时回调：切回登录页 */
export function clearAuthUser() {
  state.user = null
  state.ready = true
}

/** 个人设置保存后同步全局头像/昵称 */
export function setAuthUser(user: AuthUser) {
  state.user = user
}
