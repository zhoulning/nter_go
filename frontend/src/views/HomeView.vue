<script setup lang="ts">
import { computed, inject, onMounted, ref } from 'vue'
import {
  ArrowForwardOutline,
  CalendarOutline,
  DocumentTextOutline,
  GridOutline,
  PaperPlaneOutline,
  TimeOutline,
  TrophyOutline,
} from '@vicons/ionicons5'
import type { Component } from 'vue'
import { api } from '../api'
import type { Opportunity, RoundInfo } from '../types'
import { ROUND_LABEL, STATUSES as STATUSES_META, avatarGradient } from '../types'
import { FOCUS_BOARD } from '../injectionKeys'

const props = defineProps<{ go: (page: string) => void }>()

const opportunities = ref<Opportunity[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    const data = await api.listOpportunities()
    opportunities.value = data.items
  } finally {
    loading.value = false
  }
})

const ARCHIVED = ['rejected', 'no_response', 'give_up']
const activeOpps = computed(() => opportunities.value.filter((o) => !ARCHIVED.includes(o.status)))

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 11) return '早上好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

const today = new Date()
const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
const dateLabel = `${today.getMonth() + 1}月${today.getDate()}日 ${WEEKDAYS[today.getDay()]}`

// ---- 统计卡片 ----
const weekAgo = computed(() => Date.now() - 7 * 86400000)
const statCards = computed(() => [
  {
    label: '在跟进岗位',
    value: activeOpps.value.length,
    icon: GridOutline,
    tint: 'bg-indigo-50 text-indigo-600',
    page: 'board',
  },
  {
    label: '未来 7 天面试',
    value: upcomingItems.value.length,
    icon: CalendarOutline,
    tint: 'bg-amber-50 text-amber-600',
    page: 'board',
  },
  {
    label: '近 7 天投递',
    value: opportunities.value.filter(
      (o) => o.applied_at && Date.parse(o.applied_at) >= weekAgo.value,
    ).length,
    icon: PaperPlaneOutline,
    tint: 'bg-sky-50 text-sky-600',
    page: 'board',
  },
  {
    label: '累计 Offer',
    value: opportunities.value.filter((o) => o.status === 'offer' || o.status === 'accepted')
      .length,
    icon: TrophyOutline,
    tint: 'bg-emerald-50 text-emerald-600',
    page: 'offers',
  },
])

// ---- 未来 7 天面试（按天分组）----
interface UpcomingItem {
  opp: Opportunity
  round: RoundInfo
  ts: number
}
const upcomingItems = computed<UpcomingItem[]>(() => {
  const startToday = new Date()
  startToday.setHours(0, 0, 0, 0)
  const end = startToday.getTime() + 8 * 86400000
  const items: UpcomingItem[] = []
  for (const opp of opportunities.value) {
    if (ARCHIVED.includes(opp.status)) continue
    for (const round of opp.rounds) {
      if (!round.scheduled_at || round.result !== 'pending') continue
      const ts = Date.parse(round.scheduled_at)
      if (ts >= startToday.getTime() && ts < end) items.push({ opp, round, ts })
    }
  }
  return items.sort((a, b) => a.ts - b.ts)
})

interface DayGroup {
  key: string
  label: string
  items: (UpcomingItem & { hm: string })[]
}
const dayGroups = computed<DayGroup[]>(() => {
  const groups = new Map<string, DayGroup>()
  for (const item of upcomingItems.value) {
    const d = new Date(item.ts)
    const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
    if (!groups.has(key)) {
      // 用目标日期的零点算自然日差，避免"明天 14:00"因时分被舍入成后天
      const dayStart = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
      const diff = Math.round((dayStart - startOfToday().getTime()) / 86400000)
      const dayLabel =
        diff === 0 ? '今天' : diff === 1 ? '明天' : diff === 2 ? '后天' : `${d.getMonth() + 1}/${d.getDate()} ${WEEKDAYS[d.getDay()]}`
      groups.set(key, { key, label: dayLabel, items: [] })
    }
    groups.get(key)!.items.push({
      ...item,
      hm: `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`,
    })
  }
  return [...groups.values()]
})

function startOfToday() {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d
}

// ---- 待办（按类型聚合，点公司标签直达看板过滤）----
const focusBoard = inject(FOCUS_BOARD, null)

interface TodoItem {
  label: string // 标签文案
  query: string // 跳看板时的过滤词
}
interface TodoGroup {
  key: string
  title: string
  hint: string
  icon: Component
  tint: string
  items: TodoItem[]
}

const todoGroups = computed<TodoGroup[]>(() => {
  const groups: TodoGroup[] = []
  const startToday = startOfToday()

  // 1) 过去的面试还没填结果
  const resultItems: TodoItem[] = []
  for (const opp of opportunities.value) {
    if (ARCHIVED.includes(opp.status)) continue
    for (const round of opp.rounds) {
      if (round.result !== 'pending' || !round.scheduled_at) continue
      if (Date.parse(round.scheduled_at) < startToday.getTime()) {
        resultItems.push({
          label: `${opp.company} · ${ROUND_LABEL[round.round_type] ?? '面试'}`,
          query: opp.company,
        })
      }
    }
  }
  if (resultItems.length) {
    groups.push({
      key: 'results',
      title: '补填面试结果',
      hint: '面试已结束，记下通过与否，好推进下一步',
      icon: TimeOutline,
      tint: 'bg-amber-50 text-amber-600',
      items: resultItems,
    })
  }

  // 2) 想投超过 7 天
  const overdueItems: TodoItem[] = activeOpps.value
    .filter(
      (o) => o.status === 'wishlist' && Date.now() - Date.parse(o.created_at) > 7 * 86400000,
    )
    .map((o) => ({ label: `${o.company} · ${o.position}`, query: o.company }))
  if (overdueItems.length) {
    groups.push({
      key: 'overdue',
      title: '想投超期，尽快行动',
      hint: '加入「想投」已超 7 天，投递或果断放弃',
      icon: PaperPlaneOutline,
      tint: 'bg-rose-50 text-rose-600',
      items: overdueItems,
    })
  }

  // 3) 投出去了但还没填工作描述
  const jdItems: TodoItem[] = activeOpps.value
    .filter((o) => o.status !== 'wishlist' && !o.jd_text)
    .map((o) => ({ label: o.company, query: o.company }))
  if (jdItems.length) {
    groups.push({
      key: 'jd',
      title: '补充工作描述',
      hint: '有 JD 才能做匹配度分析和题目预测',
      icon: DocumentTextOutline,
      tint: 'bg-indigo-50 text-indigo-600',
      items: jdItems,
    })
  }

  return groups
})

const todoTotal = computed(() =>
  todoGroups.value.reduce((acc, g) => acc + g.items.length, 0),
)

function onTodoClick(query: string) {
  if (focusBoard) focusBoard(query)
  else props.go('board')
}

// ---- 最近更新 ----
const recent = computed(() =>
  [...activeOpps.value]
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    .slice(0, 5),
)

function statusMetaOf(status: string) {
  return STATUSES_META.find((s) => s.key === status)
}
</script>

<template>
  <div class="h-full overflow-y-auto">
    <!-- 问候 -->
    <header class="fade-up px-7 pb-4 pt-6">
      <h1 class="text-[21px] font-bold tracking-tight text-zinc-900">{{ greeting }}，继续冲刺</h1>
      <p class="mt-1 text-[13px] text-zinc-400">今天是 {{ dateLabel }} · 面试节奏尽在掌握</p>
    </header>

    <div v-if="loading" class="grid h-40 place-items-center text-sm text-zinc-400">
      正在加载…
    </div>

    <template v-else>
      <!-- 统计卡片 -->
      <div class="fade-up-d1 grid grid-cols-2 gap-3.5 px-7 xl:grid-cols-4">
        <button
          v-for="card in statCards"
          :key="card.label"
          class="flex items-center gap-3.5 rounded-2xl border border-zinc-200/70 bg-white p-4 text-left shadow-[0_1px_2px_rgba(16,24,40,0.04)] transition-all hover:-translate-y-px hover:shadow-[0_8px_20px_-8px_rgba(16,24,40,0.15)]"
          @click="go(card.page)"
        >
          <span class="grid h-11 w-11 shrink-0 place-items-center rounded-xl" :class="card.tint">
            <n-icon :component="card.icon" :size="22" />
          </span>
          <span>
            <span class="block text-[24px] font-bold leading-none tabular-nums text-zinc-900">
              {{ card.value }}
            </span>
            <span class="mt-1 block text-[12px] text-zinc-400">{{ card.label }}</span>
          </span>
        </button>
      </div>

      <!-- 主体两栏 -->
      <div class="fade-up-d1 mt-4 grid grid-cols-1 gap-3.5 px-7 pb-6 xl:grid-cols-3">
        <!-- 未来 7 天面试 -->
        <section class="rounded-2xl border border-zinc-200/70 bg-white p-5 xl:col-span-2">
          <div class="mb-4 flex items-center justify-between">
            <h2 class="text-[14.5px] font-bold text-zinc-800">未来 7 天面试</h2>
            <span class="text-[12px] text-zinc-400">{{ upcomingItems.length }} 场</span>
          </div>

          <div v-if="dayGroups.length === 0" class="py-10 text-center text-[13px] text-zinc-400">
            未来 7 天没有面试安排，安心准备 📚
          </div>

          <div v-for="group in dayGroups" :key="group.key" class="mb-4 last:mb-0">
            <div class="mb-2 text-[12px] font-semibold text-zinc-400">{{ group.label }}</div>
            <button
              v-for="item in group.items"
              :key="item.round.id"
              class="group flex w-full items-center gap-3 rounded-xl border border-zinc-100 px-3 py-2.5 text-left transition-colors hover:border-indigo-200 hover:bg-indigo-50/40"
              @click="go('board')"
            >
              <span class="w-[52px] shrink-0 text-[15px] font-bold tabular-nums text-zinc-800">
                {{ item.hm }}
              </span>
              <span
                class="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-[12px] font-bold text-white"
                :style="{ background: avatarGradient(item.opp.company) }"
              >
                {{ item.opp.company.slice(0, 1) }}
              </span>
              <span class="min-w-0 flex-1">
                <span class="block truncate text-[13px] font-semibold text-zinc-800">
                  {{ item.opp.company }}
                  <span class="ml-1.5 rounded-md bg-zinc-100 px-1.5 py-0.5 text-[10.5px] font-medium text-zinc-500">
                    {{ ROUND_LABEL[item.round.round_type] ?? '面试' }}
                  </span>
                </span>
                <span class="block truncate text-[11.5px] text-zinc-400">{{ item.opp.position }}</span>
              </span>
              <n-icon
                :component="ArrowForwardOutline"
                :size="14"
                class="shrink-0 text-zinc-300 transition-colors group-hover:text-indigo-400"
              />
            </button>
          </div>
        </section>

        <!-- 待办提醒 -->
        <section class="rounded-2xl border border-zinc-200/70 bg-white p-5">
          <div class="mb-4 flex items-center justify-between">
            <h2 class="text-[14.5px] font-bold text-zinc-800">待办提醒</h2>
            <span
              v-if="todoTotal"
              class="rounded-full bg-rose-50 px-2 py-0.5 text-[11px] font-semibold text-rose-500"
            >
              {{ todoTotal }}
            </span>
          </div>

          <div v-if="todoGroups.length === 0" class="py-10 text-center text-[13px] text-zinc-400">
            全部搞定，没有待办 🎉
          </div>

          <div
            v-for="group in todoGroups"
            :key="group.key"
            class="mb-2.5 rounded-xl border border-zinc-100 p-3 transition-colors last:mb-0 hover:border-zinc-200"
          >
            <div class="flex items-center gap-2">
              <span
                class="grid h-6 w-6 shrink-0 place-items-center rounded-md"
                :class="group.tint"
              >
                <n-icon :component="group.icon" :size="13" />
              </span>
              <span class="text-[13px] font-semibold text-zinc-800">{{ group.title }}</span>
              <span class="text-[11px] font-semibold tabular-nums text-zinc-400">
                × {{ group.items.length }}
              </span>
            </div>
            <p class="mb-2 mt-1 text-[11px] text-zinc-400">{{ group.hint }}</p>
            <div class="flex flex-wrap gap-1.5">
              <button
                v-for="item in group.items"
                :key="group.key + item.label"
                class="group/chip inline-flex items-center gap-1 rounded-full border border-zinc-200 bg-white py-1 pl-2.5 pr-2 text-[11.5px] font-medium text-zinc-600 transition-all hover:border-indigo-300 hover:bg-indigo-50/60 hover:text-indigo-600"
                :title="`去处理：${item.label}`"
                @click="onTodoClick(item.query)"
              >
                {{ item.label }}
                <n-icon
                  :component="ArrowForwardOutline"
                  :size="10"
                  class="text-zinc-300 transition-colors group-hover/chip:text-indigo-400"
                />
              </button>
            </div>
          </div>
        </section>

        <!-- 最近更新 -->
        <section class="rounded-2xl border border-zinc-200/70 bg-white p-5 xl:col-span-3">
          <div class="mb-3 flex items-center justify-between">
            <h2 class="text-[14.5px] font-bold text-zinc-800">最近更新</h2>
            <button
              class="flex items-center gap-1 text-[12px] text-indigo-500 hover:text-indigo-600"
              @click="go('board')"
            >
              查看看板 <n-icon :component="ArrowForwardOutline" :size="12" />
            </button>
          </div>
          <div class="flex flex-wrap gap-2.5">
            <button
              v-for="opp in recent"
              :key="opp.id"
              class="flex items-center gap-2 rounded-full border border-zinc-200/80 py-1.5 pl-1.5 pr-3.5 transition-all hover:border-indigo-200 hover:bg-indigo-50/40"
              @click="go('board')"
            >
              <span
                class="grid h-6 w-6 place-items-center rounded-full text-[10.5px] font-bold text-white"
                :style="{ background: avatarGradient(opp.company) }"
              >
                {{ opp.company.slice(0, 1) }}
              </span>
              <span class="text-[12.5px] font-medium text-zinc-700">{{ opp.company }}</span>
              <span class="text-[11px] text-zinc-400">
                {{ statusMetaOf(opp.status)?.label ?? opp.status }} · 停留
                {{ Math.max(0, Math.floor((Date.now() - Date.parse(opp.status_changed_at)) / 86400000)) }} 天
              </span>
            </button>
          </div>
        </section>
      </div>
    </template>
  </div>
</template>
