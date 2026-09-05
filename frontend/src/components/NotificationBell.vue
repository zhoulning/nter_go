<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { NBadge, NButton, NEmpty, NPopover, NTabPane, NTabs } from 'naive-ui'
import { NotificationsOutline } from '@vicons/ionicons5'
import { api } from '../api'
import type { NotificationSummary } from '../api'

const emit = defineEmits<{ (e: 'open-opportunity', id: number): void }>()

const show = ref(false)
const loading = ref(false)
const summary = ref<NotificationSummary>({ unread_count: 0, items: [], interview_reminders: [] })
let timer: number | null = null

const activeTab = ref<'reminders' | 'account'>('reminders')

async function refresh() {
  try {
    summary.value = await api.notificationSummary()
  } catch {
    /* 静默：铃铛轮询失败不打扰用户 */
  }
}

async function onUpdateShow(v: boolean) {
  show.value = v
  if (!v) return
  loading.value = true
  // 有面试提醒时默认落在提醒页，否则落在账号通知页
  await refresh()
  activeTab.value = summary.value.interview_reminders.length ? 'reminders' : 'account'
  loading.value = false
  if (summary.value.unread_count) {
    // 打开面板即视为已读（延迟一点，让用户先看到未读红点消失的过渡）
    setTimeout(async () => {
      try {
        await api.markNotificationsRead()
        summary.value.unread_count = 0
        summary.value.items = summary.value.items.map((n) => ({ ...n, read: true }))
      } catch {
        /* ignore */
      }
    }, 800)
  }
}

function goOpp(id: number) {
  show.value = false
  emit('open-opportunity', id)
}

function timeText(iso: string | null) {
  if (!iso) return ''
  const d = new Date(iso)
  const today = new Date()
  const sameDay = d.toDateString() === today.toDateString()
  const time = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  if (sameDay) return `今天 ${time}`
  return `${d.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })} ${time}`
}

onMounted(() => {
  refresh()
  timer = window.setInterval(refresh, 60_000)
})

onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<template>
  <n-popover trigger="click" placement="bottom-end" :width="320" raw :show="show" @update:show="onUpdateShow">
    <template #trigger>
      <button
        class="relative grid h-9 w-9 place-items-center rounded-lg text-zinc-500 transition-colors hover:bg-zinc-100 active:bg-zinc-100"
      >
        <n-badge :value="summary.unread_count" :max="99" :show="summary.unread_count > 0">
          <n-icon :component="NotificationsOutline" :size="19" />
        </n-badge>
      </button>
    </template>

    <div class="rounded-xl bg-white shadow-[0_12px_40px_-8px_rgba(16,24,40,0.18)]">
      <n-tabs v-model:value="activeTab" type="line" size="small" class="px-3 pt-2">
        <n-tab-pane name="reminders" tab="面试提醒">
          <div class="max-h-[320px] overflow-y-auto">
            <NEmpty
              v-if="!summary.interview_reminders.length"
              description="近两天没有面试安排"
              class="py-8"
              size="small"
            />
            <button
              v-for="r in summary.interview_reminders"
              :key="r.round_id"
              class="block w-full rounded-lg px-2.5 py-2.5 text-left transition-colors hover:bg-zinc-50"
              @click="goOpp(r.opportunity_id)"
            >
              <div class="flex items-center gap-2">
                <span
                  class="rounded px-1.5 py-0.5 text-[10.5px] font-semibold"
                  :class="r.day_label === '今天' ? 'bg-indigo-50 text-indigo-600' : 'bg-zinc-100 text-zinc-500'"
                >
                  {{ r.day_label }} {{ r.time_text }}
                </span>
                <span v-if="r.is_past && r.pending" class="text-[10.5px] text-amber-600">进行中/已过点</span>
              </div>
              <div class="mt-1 truncate text-[13px] font-semibold text-zinc-800">
                {{ r.company }} · {{ r.round_type === 'written' ? '笔试' : '面试' }}
              </div>
              <div class="truncate text-[11.5px] text-zinc-400">
                {{ r.position }}{{ r.note ? ` · ${r.note}` : '' }}
              </div>
            </button>
          </div>
        </n-tab-pane>

        <n-tab-pane name="account" :tab="`通知${summary.unread_count ? ` (${summary.unread_count})` : ''}`">
          <div class="max-h-[320px] overflow-y-auto">
            <NEmpty v-if="!summary.items.length" description="暂无通知" class="py-8" size="small" />
            <div
              v-for="n in summary.items"
              :key="n.id"
              class="rounded-lg px-2.5 py-2.5 transition-colors hover:bg-zinc-50"
            >
              <div class="flex items-start gap-2">
                <span
                  v-if="!n.read"
                  class="mt-[5px] h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-500"
                />
                <div class="min-w-0 flex-1">
                  <div class="text-[13px] font-semibold text-zinc-800">{{ n.title }}</div>
                  <div v-if="n.body" class="mt-0.5 text-[11.5px] leading-relaxed text-zinc-500">
                    {{ n.body }}
                  </div>
                  <div class="mt-1 text-[10.5px] text-zinc-300">{{ timeText(n.created_at) }}</div>
                </div>
              </div>
            </div>
          </div>
        </n-tab-pane>
      </n-tabs>
    </div>
  </n-popover>
</template>
