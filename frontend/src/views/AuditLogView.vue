<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { NButton, NSelect, NTag, useMessage } from 'naive-ui'
import { api } from '../api'
import type { AuditLogItem } from '../api'

const message = useMessage()
const PAGE_SIZE = 50

const items = ref<AuditLogItem[]>([])
const total = ref(0)
const usernames = ref<string[]>([])
const loading = ref(false)
const category = ref('')
const username = ref<string | null>(null)
const offset = ref(0)

const CATEGORIES = [
  { label: '全部', value: '' },
  { label: '登录认证', value: 'auth' },
  { label: '账号资料', value: 'account' },
  { label: '用户管理', value: 'user' },
  { label: '系统配置', value: 'settings' },
]

const ACTION_LABELS: Record<string, string> = {
  'auth.login': '登录',
  'auth.login_failed': '登录失败',
  'auth.logout': '退出登录',
  'auth.register': '提交注册',
  'account.password_change': '修改密码',
  'account.profile_update': '修改资料',
  'account.avatar_update': '更换头像',
  'account.avatar_remove': '移除头像',
  'user.create': '创建用户',
  'user.approve': '审核通过',
  'user.reject': '拒绝注册',
  'user.disable': '禁用用户',
  'user.enable': '启用用户',
  'user.reset_password': '重置用户密码',
  'user.delete': '删除用户',
  'settings.ai': '修改 AI 配置',
  'settings.browser': '修改浏览器配置',
  'settings.kb': '修改知识库配置',
  'settings.asr': '修改语音转写配置',
  'settings.registration': '修改注册开关',
}

const ACTION_TYPES: Record<string, 'success' | 'error' | 'warning' | 'info' | 'default'> = {
  'auth.login': 'success',
  'auth.login_failed': 'error',
  'auth.logout': 'default',
  'auth.register': 'info',
  'account.password_change': 'warning',
  'account.profile_update': 'default',
  'account.avatar_update': 'default',
  'account.avatar_remove': 'default',
  'user.create': 'success',
  'user.approve': 'success',
  'user.reject': 'error',
  'user.disable': 'warning',
  'user.enable': 'success',
  'user.reset_password': 'warning',
  'user.delete': 'error',
  'settings.ai': 'info',
  'settings.browser': 'info',
  'settings.kb': 'info',
  'settings.asr': 'info',
  'settings.registration': 'info',
}

const usernameOptions = () => usernames.value.map((u) => ({ label: u, value: u }))

function fmtTime(v: string | null) {
  if (!v) return '—'
  return new Date(v).toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'medium' })
}

async function load(reset = true) {
  loading.value = true
  try {
    const page = await api.listAuditLogs({
      category: category.value,
      username: username.value ?? undefined,
      limit: PAGE_SIZE,
      offset: reset ? 0 : offset.value,
    })
    items.value = reset ? page.items : [...items.value, ...page.items]
    total.value = page.total
    usernames.value = page.usernames
    offset.value = reset ? page.items.length : offset.value + page.items.length
  } catch (e) {
    message.error((e as Error).message || '读取操作日志失败')
  } finally {
    loading.value = false
  }
}

function switchCategory(v: string) {
  if (category.value === v) return
  category.value = v
  load(true)
}

function switchUsername(v: string | null) {
  username.value = v
  load(true)
}

const hasMore = () => items.value.length < total.value

onMounted(() => load(true))
</script>

<template>
  <div class="flex h-full flex-col">
    <div class="fade-up flex items-end justify-between gap-3 px-7 pb-4 pt-6 max-md:gap-2.5 max-md:px-4 max-md:pt-4">
      <div>
        <h1 class="text-[21px] font-bold tracking-tight text-zinc-900">操作日志</h1>
        <p class="mt-1 text-[13px] text-zinc-400">登录认证、账号资料、用户管理与系统配置的关键操作留痕</p>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="fade-up flex flex-wrap items-center gap-2 px-7 pb-3 max-md:px-4">
      <div class="flex flex-wrap gap-1 rounded-xl bg-zinc-100/80 p-1">
        <button
          v-for="c in CATEGORIES"
          :key="c.value"
          class="rounded-lg px-3 py-1.5 text-[12.5px] transition-colors"
          :class="category === c.value ? 'bg-white font-semibold text-indigo-600 shadow-sm' : 'text-zinc-500 hover:text-zinc-700'"
          @click="switchCategory(c.value)"
        >
          {{ c.label }}
        </button>
      </div>
      <n-select
        :value="username"
        :options="usernameOptions()"
        placeholder="全部操作人"
        clearable
        filterable
        size="small"
        class="w-[150px] max-md:w-full"
        @update:value="switchUsername"
      />
      <span class="ml-auto text-[12px] text-zinc-400 max-md:hidden">共 {{ total }} 条</span>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto px-7 pb-10 max-md:px-4">
      <div v-if="loading && !items.length" class="py-16 text-center text-[13px] text-zinc-400">加载中…</div>

      <template v-else>
        <div v-if="!items.length" class="rounded-2xl border border-zinc-100 bg-white py-16 text-center text-[13px] text-zinc-400">
          暂无日志
        </div>

        <template v-else>
          <!-- PC 表格 -->
          <div class="hidden overflow-x-auto rounded-2xl border border-zinc-100 bg-white md:block">
            <table class="w-full text-left text-[13px]">
              <thead>
                <tr class="border-b border-zinc-100 bg-zinc-50/70 text-[12px] text-zinc-400">
                  <th class="px-5 py-3 font-medium">时间</th>
                  <th class="px-3 py-3 font-medium">操作人</th>
                  <th class="px-3 py-3 font-medium">操作</th>
                  <th class="px-3 py-3 font-medium">对象</th>
                  <th class="px-3 py-3 font-medium">说明</th>
                  <th class="px-5 py-3 font-medium">IP</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="log in items"
                  :key="log.id"
                  class="border-b border-zinc-50 transition-colors last:border-0 hover:bg-zinc-50/60"
                >
                  <td class="whitespace-nowrap px-5 py-3 text-zinc-500">{{ fmtTime(log.created_at) }}</td>
                  <td class="px-3 py-3 font-medium text-zinc-700">{{ log.username || '—' }}</td>
                  <td class="px-3 py-3">
                    <n-tag :type="ACTION_TYPES[log.action] ?? 'default'" size="small" round>
                      {{ ACTION_LABELS[log.action] ?? log.action }}
                    </n-tag>
                  </td>
                  <td class="px-3 py-3 text-zinc-600">{{ log.target || '—' }}</td>
                  <td class="max-w-[320px] truncate px-3 py-3 text-zinc-500" :title="log.detail ?? ''">{{ log.detail || '—' }}</td>
                  <td class="px-5 py-3 text-zinc-400">{{ log.ip || '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 移动端卡片 -->
          <div class="flex flex-col gap-2 md:hidden">
            <div v-for="log in items" :key="log.id" class="rounded-xl border border-zinc-100 bg-white p-3.5">
              <div class="flex items-center justify-between gap-2">
                <n-tag :type="ACTION_TYPES[log.action] ?? 'default'" size="small" round>
                  {{ ACTION_LABELS[log.action] ?? log.action }}
                </n-tag>
                <span class="text-[11px] text-zinc-400">{{ fmtTime(log.created_at) }}</span>
              </div>
              <div class="mt-2 text-[13px] text-zinc-700">
                <span class="font-semibold">{{ log.username || '—' }}</span>
                <span v-if="log.target"> → {{ log.target }}</span>
              </div>
              <div v-if="log.detail" class="mt-1 break-all text-[11.5px] text-zinc-400">{{ log.detail }}</div>
              <div v-if="log.ip" class="mt-1 text-[11px] text-zinc-300">IP {{ log.ip }}</div>
            </div>
          </div>

          <!-- 加载更多 -->
          <div v-if="hasMore()" class="mt-4 text-center">
            <n-button size="small" quaternary :loading="loading" @click="load(false)">
              加载更多（已显示 {{ items.length }} / {{ total }}）
            </n-button>
          </div>
        </template>
      </template>
    </div>
  </div>
</template>
