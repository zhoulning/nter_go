<script setup lang="ts">
import { computed, inject, onMounted, ref } from 'vue'
import type { Component } from 'vue'
import {
  AddCircleOutline,
  ArrowForwardOutline,
  BookOutline,
  CalendarOutline,
  ChatbubblesOutline,
  CheckmarkCircleOutline,
  CheckmarkDoneOutline,
  CloseCircleOutline,
  DocumentTextOutline,
  GridOutline,
  MicOutline,
  PaperPlaneOutline,
  SparklesOutline,
  TimeOutline,
  TrophyOutline,
} from '@vicons/ionicons5'
import { api } from '../api'
import type { DashboardData } from '../api'
import { OPEN_OPPORTUNITY_DETAIL, OPEN_RESUME_DETAIL, FOCUS_BOARD } from '../injectionKeys'
import { ROUND_LABEL, avatarGradient } from '../types'

const props = defineProps<{ go: (page: string) => void }>()

const data = ref<DashboardData | null>(null)
const loading = ref(true)

const openOpportunityDetail = inject(OPEN_OPPORTUNITY_DETAIL, null)
const openResumeDetail = inject(OPEN_RESUME_DETAIL, null)
const focusBoard = inject(FOCUS_BOARD, null)

onMounted(async () => {
  try {
    data.value = await api.statsDashboard()
  } finally {
    loading.value = false
  }
})

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

// ---- 头部速览：今日面试 / 待办总数 ----
const todayInterviews = computed(() => {
  const t = new Date()
  return (data.value?.upcoming ?? []).filter((u) => {
    const d = new Date(u.scheduled_at)
    return (
      d.getFullYear() === t.getFullYear() && d.getMonth() === t.getMonth() && d.getDate() === t.getDate()
    )
  }).length
})

const todoTotal = computed(() => {
  const t = data.value?.todos
  if (!t) return 0
  return (
    t.round_results_total +
    t.overdue_total +
    t.missing_jd_total +
    t.questions_todo +
    t.recordings_total +
    t.resumes_total
  )
})

// ---- 指标卡（点击直达对应模块）----
interface StatCard {
  label: string
  value: number
  sub?: string
  icon: Component
  tint: string
  page: string
}

const statCards = computed<StatCard[]>(() => {
  const c = data.value?.cards
  if (!c) return []
  return [
    {
      label: '在跟进岗位',
      value: c.active_opportunities,
      icon: GridOutline,
      tint: 'bg-indigo-50 text-indigo-600',
      page: 'board',
    },
    {
      label: '未来 7 天面试',
      value: c.upcoming_interviews,
      sub: todayInterviews.value ? `今日 ${todayInterviews.value} 场` : undefined,
      icon: CalendarOutline,
      tint: 'bg-amber-50 text-amber-600',
      page: 'calendar',
    },
    {
      label: '近 7 天投递',
      value: c.applied_week,
      icon: PaperPlaneOutline,
      tint: 'bg-sky-50 text-sky-600',
      page: 'board',
    },
    {
      label: '累计 Offer',
      value: c.offers,
      icon: TrophyOutline,
      tint: 'bg-emerald-50 text-emerald-600',
      page: 'offers',
    },
    {
      label: '错题待复习',
      value: c.questions_todo,
      sub: `题库共 ${c.questions_total} 题`,
      icon: BookOutline,
      tint: 'bg-rose-50 text-rose-600',
      page: 'questions',
    },
    {
      label: '录音待复盘',
      value: c.recordings_todo,
      sub: c.review_avg_score != null ? `复盘均分 ${c.review_avg_score}` : undefined,
      icon: MicOutline,
      tint: 'bg-violet-50 text-violet-600',
      page: 'recordings',
    },
  ]
})

// ---- 未来 7 天面试（按天分组）----
interface UpcomingItem {
  round_id: number
  opportunity_id: number
  company: string
  position: string
  round_type: string
  ts: number
  hm: string
}

const dayGroups = computed(() => {
  const groups = new Map<string, { key: string; label: string; items: UpcomingItem[] }>()
  for (const u of data.value?.upcoming ?? []) {
    const d = new Date(u.scheduled_at)
    const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
    if (!groups.has(key)) {
      // 用目标日期的零点算自然日差，避免"明天 14:00"因时分被舍入成后天
      const dayStart = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
      const diff = Math.round((dayStart - startOfToday().getTime()) / 86400000)
      const dayLabel =
        diff === 0
          ? '今天'
          : diff === 1
            ? '明天'
            : diff === 2
              ? '后天'
              : `${d.getMonth() + 1}/${d.getDate()} ${WEEKDAYS[d.getDay()]}`
      groups.set(key, { key, label: dayLabel, items: [] })
    }
    groups.get(key)!.items.push({
      ...u,
      ts: d.getTime(),
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

function openOpp(id: number) {
  if (openOpportunityDetail) openOpportunityDetail(id)
  else props.go('board')
}

// ---- 待办提醒 ----
interface TodoGroup {
  key: string
  title: string
  hint: string
  icon: Component
  tint: string
  count: number
  chips: { label: string; title: string; action: () => void }[]
}

const todoGroups = computed<TodoGroup[]>(() => {
  const t = data.value?.todos
  if (!t) return []
  const groups: TodoGroup[] = []

  if (t.round_results_total) {
    groups.push({
      key: 'results',
      title: '补填面试结果',
      hint: '面试已结束，记下通过与否，好推进下一步',
      icon: TimeOutline,
      tint: 'bg-amber-50 text-amber-600',
      count: t.round_results_total,
      chips: t.round_results.map((x) => ({
        label: `${x.company} · ${ROUND_LABEL[x.round_type] ?? '面试'}`,
        title: `去处理：${x.company}`,
        action: () => openOpp(x.opportunity_id),
      })),
    })
  }

  if (t.overdue_total) {
    groups.push({
      key: 'overdue',
      title: '想投超期，尽快行动',
      hint: '加入「想投」已超 7 天，投递或果断放弃',
      icon: PaperPlaneOutline,
      tint: 'bg-rose-50 text-rose-600',
      count: t.overdue_total,
      chips: t.overdue_wishlist.map((x) => ({
        label: `${x.company} · ${x.position}`,
        title: `去处理：${x.company}`,
        action: () => openOpp(x.opportunity_id),
      })),
    })
  }

  if (t.missing_jd_total) {
    groups.push({
      key: 'jd',
      title: '补充工作描述',
      hint: '有 JD 才能做匹配度分析和题目预测',
      icon: DocumentTextOutline,
      tint: 'bg-indigo-50 text-indigo-600',
      count: t.missing_jd_total,
      chips: t.missing_jd.map((x) => ({
        label: x.company,
        title: `去处理：${x.company}`,
        action: () => openOpp(x.opportunity_id),
      })),
    })
  }

  if (t.questions_todo) {
    groups.push({
      key: 'questions',
      title: '错题待复习',
      hint: '还没吃透的题，趁热打铁过一遍',
      icon: BookOutline,
      tint: 'bg-rose-50 text-rose-600',
      count: t.questions_todo,
      chips: [
        {
          label: `去题库复习 ${t.questions_todo} 道错题`,
          title: '打开题库',
          action: () => props.go('questions'),
        },
      ],
    })
  }

  if (t.recordings_total) {
    groups.push({
      key: 'recordings',
      title: '录音待复盘',
      hint: '已转写的录音还没生成复盘报告',
      icon: MicOutline,
      tint: 'bg-violet-50 text-violet-600',
      count: t.recordings_total,
      chips: t.recordings_review.map((x) => ({
        label: `${x.company ?? '未知公司'} · ${x.title}`,
        title: `去复盘：${x.title}`,
        action: () => props.go('recordings'),
      })),
    })
  }

  if (t.resumes_total) {
    groups.push({
      key: 'resumes',
      title: '简历待体检',
      hint: '还没做 AI 体检的简历，看看能打几分',
      icon: DocumentTextOutline,
      tint: 'bg-sky-50 text-sky-600',
      count: t.resumes_total,
      chips: t.resumes_no_review.map((x) => ({
        label: x.name,
        title: `去体检：${x.name}`,
        action: () => (openResumeDetail ? openResumeDetail(x.id) : props.go('resumes')),
      })),
    })
  }

  return groups
})

// ---- 求职漏斗速览（完整分析见「数据洞察」）----
const FUNNEL_COLORS = ['#6366f1', '#8b5cf6', '#f59e0b', '#10b981', '#14b8a6']
const funnelRows = computed(() => {
  const funnel = data.value?.funnel ?? []
  const max = Math.max(1, funnel[0]?.count ?? 1)
  return funnel.map((f, i) => ({
    ...f,
    color: FUNNEL_COLORS[i % FUNNEL_COLORS.length],
    width: Math.max(f.count > 0 ? 6 : 2, (f.count / max) * 100),
  }))
})

// ---- 最近动态（跨模块时间线）----
const ACTIVITY_META: Record<string, { icon: Component; tint: string }> = {
  opp_created: { icon: AddCircleOutline, tint: 'bg-zinc-100 text-zinc-500' },
  applied: { icon: PaperPlaneOutline, tint: 'bg-sky-50 text-sky-600' },
  round_scheduled: { icon: CalendarOutline, tint: 'bg-amber-50 text-amber-600' },
  round_passed: { icon: CheckmarkCircleOutline, tint: 'bg-emerald-50 text-emerald-600' },
  round_failed: { icon: CloseCircleOutline, tint: 'bg-rose-50 text-rose-600' },
  offer: { icon: TrophyOutline, tint: 'bg-emerald-50 text-emerald-600' },
  accepted: { icon: CheckmarkDoneOutline, tint: 'bg-teal-50 text-teal-600' },
  recording: { icon: MicOutline, tint: 'bg-violet-50 text-violet-600' },
  review: { icon: SparklesOutline, tint: 'bg-indigo-50 text-indigo-600' },
  resume: { icon: DocumentTextOutline, tint: 'bg-zinc-100 text-zinc-500' },
  mock: { icon: ChatbubblesOutline, tint: 'bg-violet-50 text-violet-600' },
}

function activityMeta(kind: string) {
  return ACTIVITY_META[kind] ?? { icon: DocumentTextOutline, tint: 'bg-zinc-100 text-zinc-500' }
}

function timeAgo(ts: string): string {
  const diffMin = Math.floor((Date.now() - Date.parse(ts)) / 60000)
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin} 分钟前`
  const h = Math.floor(diffMin / 60)
  if (h < 24) return `${h} 小时前`
  const d = Math.floor(h / 24)
  if (d < 7) return `${d} 天前`
  const date = new Date(ts)
  return `${date.getMonth() + 1}/${date.getDate()}`
}

function onActivityClick(oppId: number | null) {
  if (oppId != null) openOpp(oppId)
  else if (focusBoard) focusBoard()
}
</script>

<template>
  <div class="h-full overflow-y-auto">
    <!-- 问候 -->
    <header
      class="fade-up flex flex-wrap items-end justify-between gap-3 px-7 pb-4 pt-6 max-md:px-4 max-md:pt-4"
    >
      <div>
        <h1 class="text-[21px] font-bold tracking-tight text-zinc-900">{{ greeting }}，继续冲刺</h1>
        <p class="mt-1 text-[13px] text-zinc-400">今天是 {{ dateLabel }}</p>
      </div>
      <div v-if="data" class="flex flex-wrap items-center gap-2">
        <span
          class="inline-flex items-center gap-1.5 rounded-full border border-amber-200/70 bg-amber-50/70 px-3 py-1 text-[12px] font-medium text-amber-700"
        >
          <n-icon :component="CalendarOutline" :size="13" />
          今日 {{ todayInterviews }} 场面试
        </span>
        <span
          class="inline-flex items-center gap-1.5 rounded-full border border-rose-200/70 bg-rose-50/70 px-3 py-1 text-[12px] font-medium text-rose-600"
        >
          <n-icon :component="TimeOutline" :size="13" />
          {{ todoTotal }} 项待办
        </span>
        <span
          class="inline-flex items-center gap-1.5 rounded-full border border-indigo-200/70 bg-indigo-50/70 px-3 py-1 text-[12px] font-medium text-indigo-600"
        >
          <n-icon :component="GridOutline" :size="13" />
          {{ data.cards.active_opportunities }} 个岗位在跟进
        </span>
      </div>
    </header>

    <div v-if="loading" class="grid h-40 place-items-center text-sm text-zinc-400">
      正在加载…
    </div>

    <template v-else-if="data">
      <!-- 指标卡：全模块一览 -->
      <div
        class="fade-up-d1 grid grid-cols-2 gap-3.5 px-7 max-md:gap-2.5 max-md:px-4 md:grid-cols-3 xl:grid-cols-6"
      >
        <button
          v-for="card in statCards"
          :key="card.label"
          class="group flex flex-col items-start gap-3 rounded-2xl border border-zinc-200/70 bg-white p-4 text-left shadow-[0_1px_2px_rgba(16,24,40,0.04)] transition-all hover:-translate-y-px hover:shadow-[0_8px_20px_-8px_rgba(16,24,40,0.15)]"
          @click="props.go(card.page)"
        >
          <span class="flex w-full items-center justify-between">
            <span class="grid h-9 w-9 place-items-center rounded-xl" :class="card.tint">
              <n-icon :component="card.icon" :size="18" />
            </span>
            <n-icon
              :component="ArrowForwardOutline"
              :size="13"
              class="text-zinc-200 transition-colors group-hover:text-indigo-400"
            />
          </span>
          <span>
            <span class="block text-[22px] font-bold leading-none tabular-nums text-zinc-900">
              {{ card.value }}
            </span>
            <span class="mt-1.5 block text-[12px] text-zinc-500">{{ card.label }}</span>
            <span v-if="card.sub" class="mt-0.5 block text-[10.5px] text-zinc-400">
              {{ card.sub }}
            </span>
          </span>
        </button>
      </div>

      <!-- 主体两栏：日程 + 待办 -->
      <div class="fade-up-d1 mt-3.5 grid grid-cols-1 gap-3.5 px-7 max-md:px-4 xl:grid-cols-3">
        <!-- 未来 7 天面试 -->
        <section class="rounded-2xl border border-zinc-200/70 bg-white p-5 max-md:p-4 xl:col-span-2">
          <div class="mb-4 flex items-center justify-between">
            <h2 class="text-[14.5px] font-bold text-zinc-800">未来 7 天面试</h2>
            <button
              class="flex items-center gap-1 text-[12px] text-indigo-500 hover:text-indigo-600"
              @click="props.go('calendar')"
            >
              完整日程 <n-icon :component="ArrowForwardOutline" :size="12" />
            </button>
          </div>

          <div v-if="dayGroups.length === 0" class="py-10 text-center text-[13px] text-zinc-400">
            未来 7 天没有面试安排，安心准备 📚
          </div>

          <div v-for="group in dayGroups" :key="group.key" class="mb-4 last:mb-0">
            <div class="mb-2 text-[12px] font-semibold text-zinc-400">{{ group.label }}</div>
            <button
              v-for="item in group.items"
              :key="item.round_id"
              class="group flex w-full items-center gap-3 rounded-xl border border-zinc-100 px-3 py-2.5 text-left transition-colors hover:border-indigo-200 hover:bg-indigo-50/40"
              @click="openOpp(item.opportunity_id)"
            >
              <span class="w-[52px] shrink-0 text-[15px] font-bold tabular-nums text-zinc-800">
                {{ item.hm }}
              </span>
              <span
                class="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-[12px] font-bold text-white"
                :style="{ background: avatarGradient(item.company) }"
              >
                {{ item.company.slice(0, 1) }}
              </span>
              <span class="min-w-0 flex-1">
                <span class="block truncate text-[13px] font-semibold text-zinc-800">
                  {{ item.company }}
                  <span
                    class="ml-1.5 rounded-md bg-zinc-100 px-1.5 py-0.5 text-[10.5px] font-medium text-zinc-500"
                  >
                    {{ ROUND_LABEL[item.round_type] ?? '面试' }}
                  </span>
                </span>
                <span class="block truncate text-[11.5px] text-zinc-400">{{ item.position }}</span>
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
        <section class="rounded-2xl border border-zinc-200/70 bg-white p-5 max-md:p-4">
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
              <span class="grid h-6 w-6 shrink-0 place-items-center rounded-md" :class="group.tint">
                <n-icon :component="group.icon" :size="13" />
              </span>
              <span class="text-[13px] font-semibold text-zinc-800">{{ group.title }}</span>
              <span class="text-[11px] font-semibold tabular-nums text-zinc-400">
                × {{ group.count }}
              </span>
            </div>
            <p class="mb-2 mt-1 text-[11px] text-zinc-400">{{ group.hint }}</p>
            <div class="flex flex-wrap gap-1.5">
              <button
                v-for="chip in group.chips"
                :key="group.key + chip.label"
                class="group/chip inline-flex max-w-full items-center gap-1 rounded-full border border-zinc-200 bg-white py-1 pl-2.5 pr-2 text-[11.5px] font-medium text-zinc-600 transition-all hover:border-indigo-300 hover:bg-indigo-50/60 hover:text-indigo-600"
                :title="chip.title"
                @click="chip.action()"
              >
                <span class="max-w-[180px] truncate">{{ chip.label }}</span>
                <n-icon
                  :component="ArrowForwardOutline"
                  :size="10"
                  class="shrink-0 text-zinc-300 transition-colors group-hover/chip:text-indigo-400"
                />
              </button>
            </div>
          </div>
        </section>
      </div>

      <!-- 漏斗速览 + 最近动态 -->
      <div
        class="fade-up-d1 mt-3.5 grid grid-cols-1 gap-3.5 px-7 pb-6 max-md:px-4 xl:grid-cols-3"
      >
        <!-- 求职漏斗速览 -->
        <section class="rounded-2xl border border-zinc-200/70 bg-white p-5 max-md:p-4">
          <div class="mb-4 flex items-center justify-between">
            <h2 class="text-[14.5px] font-bold text-zinc-800">求职漏斗</h2>
            <button
              class="flex items-center gap-1 text-[12px] text-indigo-500 hover:text-indigo-600"
              @click="props.go('stats')"
            >
              完整分析 <n-icon :component="ArrowForwardOutline" :size="12" />
            </button>
          </div>
          <div class="space-y-3">
            <button
              v-for="row in funnelRows"
              :key="row.key"
              class="block w-full text-left"
              @click="props.go('stats')"
            >
              <div class="mb-1 flex items-baseline justify-between">
                <span class="text-[12px] font-medium text-zinc-600">{{ row.label }}</span>
                <span class="text-[13px] font-bold tabular-nums" :style="{ color: row.color }">
                  {{ row.count }}
                </span>
              </div>
              <div class="h-2 overflow-hidden rounded-full bg-zinc-100">
                <div
                  class="h-full rounded-full transition-all"
                  :style="{ width: row.width + '%', background: row.color }"
                />
              </div>
            </button>
          </div>
        </section>

        <!-- 最近动态 -->
        <section class="rounded-2xl border border-zinc-200/70 bg-white p-5 max-md:p-4 xl:col-span-2">
          <div class="mb-4 flex items-center justify-between">
            <h2 class="text-[14.5px] font-bold text-zinc-800">最近动态</h2>
            <span class="text-[11.5px] text-zinc-400">岗位 / 面试 / 复盘 / 简历</span>
          </div>

          <div v-if="data.activity.length === 0" class="py-10 text-center text-[13px] text-zinc-400">
            还没有动态，从添加一个岗位开始吧
          </div>

          <ol class="space-y-0.5">
            <li v-for="(ev, i) in data.activity" :key="i">
              <button
                class="flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left transition-colors hover:bg-zinc-50"
                @click="onActivityClick(ev.opportunity_id)"
              >
                <span
                  class="grid h-7 w-7 shrink-0 place-items-center rounded-lg"
                  :class="activityMeta(ev.kind).tint"
                >
                  <n-icon :component="activityMeta(ev.kind).icon" :size="14" />
                </span>
                <span class="min-w-0 flex-1 truncate text-[12.5px] text-zinc-700">{{ ev.text }}</span>
                <span class="shrink-0 text-[11px] tabular-nums text-zinc-400">
                  {{ timeAgo(ev.ts) }}
                </span>
              </button>
            </li>
          </ol>
        </section>
      </div>
    </template>
  </div>
</template>
