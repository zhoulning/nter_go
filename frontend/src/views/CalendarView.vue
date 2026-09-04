<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useDialog, useMessage } from 'naive-ui'
import { AddOutline, ChevronBackOutline, ChevronForwardOutline } from '@vicons/ionicons5'
import { api } from '../api'
import type { Opportunity, RoundEvent } from '../types'
import { ROUND_LABEL, ROUND_RESULT_META } from '../types'
import { addDays, hm, startOfWeek, ymd } from '../utils'
import RoundModal from '../components/RoundModal.vue'

const message = useMessage()
const dialog = useDialog()

const viewMode = ref<'month' | 'week'>('month')
const cursor = ref<Date>(new Date())
const selectedDate = ref<string>(ymd(new Date()))
const events = ref<RoundEvent[]>([])
const opportunities = ref<Opportunity[]>([])
const loading = ref(false)

const modalShow = ref(false)
const editing = ref<RoundEvent | null>(null)
const modalDefaultDate = ref<string | null>(null)

const WEEK_DAYS = ['一', '二', '三', '四', '五', '六', '日']

// ---- 日期网格 ----
const cells = computed<Date[]>(() => {
  if (viewMode.value === 'week') {
    const monday = startOfWeek(cursor.value)
    return Array.from({ length: 7 }, (_, i) => addDays(monday, i))
  }
  const first = new Date(cursor.value.getFullYear(), cursor.value.getMonth(), 1)
  const gridStart = startOfWeek(first)
  return Array.from({ length: 42 }, (_, i) => addDays(gridStart, i))
})

const periodTitle = computed(() => {
  const d = cursor.value
  if (viewMode.value === 'week') {
    const start = startOfWeek(d)
    const end = addDays(start, 6)
    const fmt = (x: Date) => `${x.getMonth() + 1}月${x.getDate()}日`
    return `${fmt(start)} - ${fmt(end)}`
  }
  return `${d.getFullYear()} 年 ${d.getMonth() + 1} 月`
})

/** 事件按天分组，key = YYYY-MM-DD */
const eventsByDay = computed(() => {
  const map = new Map<string, RoundEvent[]>()
  for (const ev of events.value) {
    if (!ev.scheduled_at) continue
    const key = ymd(new Date(ev.scheduled_at))
    const list = map.get(key) ?? []
    list.push(ev)
    map.set(key, list)
  }
  for (const list of map.values()) {
    list.sort((a, b) => (a.scheduled_at ?? '').localeCompare(b.scheduled_at ?? ''))
  }
  return map
})

const rangeStart = computed(() => ymd(cells.value[0]))
const rangeEnd = computed(() => ymd(cells.value[cells.value.length - 1]))

async function load() {
  loading.value = true
  try {
    const data = await api.calendarEvents(rangeStart.value, rangeEnd.value)
    events.value = data.events
  } catch (e) {
    message.error((e as Error).message || '加载日历失败')
  } finally {
    loading.value = false
  }
}

async function loadOpportunities() {
  try {
    const data = await api.listOpportunities()
    opportunities.value = data.items
  } catch {
    /* 日历主体不依赖它，失败静默 */
  }
}

onMounted(() => {
  load()
  loadOpportunities()
})

function prev() {
  const d = cursor.value
  cursor.value =
    viewMode.value === 'week'
      ? addDays(d, -7)
      : new Date(d.getFullYear(), d.getMonth() - 1, 1)
  afterNavigate()
}
function next() {
  const d = cursor.value
  cursor.value =
    viewMode.value === 'week'
      ? addDays(d, 7)
      : new Date(d.getFullYear(), d.getMonth() + 1, 1)
  afterNavigate()
}
function goToday() {
  cursor.value = new Date()
  selectedDate.value = ymd(new Date())
  afterNavigate()
}
function afterNavigate() {
  if (viewMode.value === 'month') {
    const c = cursor.value
    // 月视图切换后，选中日跟随到当月（保持 1-28 号）
    const day = Math.min(selectedDayNumber.value, new Date(c.getFullYear(), c.getMonth() + 1, 0).getDate())
    selectedDate.value = ymd(new Date(c.getFullYear(), c.getMonth(), day))
  }
  load()
}
const selectedDayNumber = computed(() => Number(selectedDate.value.slice(8, 10)))

const selectedEvents = computed(() => eventsByDay.value.get(selectedDate.value) ?? [])

function cellClasses(cell: Date) {
  const key = ymd(cell)
  return {
    today: key === ymd(new Date()),
    selected: key === selectedDate.value,
    dim: viewMode.value === 'month' && cell.getMonth() !== cursor.value.getMonth(),
  }
}

// ---- 轮次增删改 ----
function openCreate() {
  editing.value = null
  modalDefaultDate.value = selectedDate.value
  modalShow.value = true
}
function openEdit(ev: RoundEvent) {
  editing.value = ev
  modalShow.value = true
}
function onSaved(_round: RoundEvent, isNew: boolean) {
  message.success(isNew ? '面试已排期' : '面试安排已更新')
  load()
}
function confirmDelete(ev: RoundEvent) {
  dialog.warning({
    title: '删除面试安排',
    content: `确定删除「${ev.company} · ${ROUND_LABEL[ev.round_type] ?? '面试'}」的安排吗？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.deleteRound(ev.id)
        message.success('已删除')
        await load()
      } catch (e) {
        message.error((e as Error).message || '删除失败')
      }
    },
  })
}

function resultChipClass(result: string): string {
  if (result === 'passed') return 'bg-emerald-50 text-emerald-600'
  if (result === 'failed') return 'bg-rose-50 text-rose-600'
  if (result === 'no_show') return 'bg-zinc-100 text-zinc-500'
  return 'bg-amber-50 text-amber-600'
}
</script>

<template>
  <div class="flex h-full flex-col">
    <!-- 页头 -->
    <header class="fade-up flex flex-wrap items-end justify-between gap-4 px-7 pb-3 pt-6">
      <div>
        <h1 class="text-[21px] font-bold tracking-tight text-zinc-900">面试日历</h1>
        <p class="mt-1 text-[13px] text-zinc-400">
          区间内共 {{ events.length }} 场面试 · 点击日期查看与排期
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2.5">
        <div class="seg">
          <button :class="viewMode === 'month' && 'active'" @click="viewMode = 'month'; afterNavigate()">月</button>
          <button :class="viewMode === 'week' && 'active'" @click="viewMode = 'week'; afterNavigate()">周</button>
        </div>
        <div class="flex items-center gap-1 rounded-xl border border-zinc-200/80 bg-white px-1 py-1">
          <button class="grid h-6 w-6 place-items-center rounded-md text-zinc-500 hover:bg-zinc-100" @click="prev">
            <n-icon :component="ChevronBackOutline" :size="15" />
          </button>
          <button class="rounded-md px-2 py-0.5 text-[12px] text-zinc-600 hover:bg-zinc-100" @click="goToday">今天</button>
          <button class="grid h-6 w-6 place-items-center rounded-md text-zinc-500 hover:bg-zinc-100" @click="next">
            <n-icon :component="ChevronForwardOutline" :size="15" />
          </button>
        </div>
        <span class="min-w-[120px] text-[13.5px] font-semibold text-zinc-700">{{ periodTitle }}</span>
        <button class="btn-gradient" @click="openCreate">
          <n-icon :component="AddOutline" :size="16" />
          新增面试
        </button>
      </div>
    </header>

    <!-- 主体：日历 + 当日面板 -->
    <div class="fade-up-d1 flex min-h-0 flex-1 gap-4 px-7 pb-5">
      <!-- 日历网格 -->
      <div class="flex min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border border-zinc-200/70 bg-white">
        <div class="grid border-b border-zinc-100 bg-zinc-50/60" :class="viewMode === 'month' ? 'grid-cols-7' : 'grid-cols-7'">
          <div
            v-for="(d, i) in WEEK_DAYS"
            :key="d"
            class="py-2 text-center text-[12px] font-medium text-zinc-400"
            :class="i >= 5 && 'text-rose-300'"
          >
            周{{ d }}
          </div>
        </div>

        <!-- 月视图 -->
        <div v-if="viewMode === 'month'" class="grid flex-1 grid-cols-7 grid-rows-6">
          <button
            v-for="cell in cells"
            :key="ymd(cell)"
            class="cal-cell group relative flex flex-col items-stretch border-b border-r border-zinc-100 p-1.5 text-left transition-colors hover:bg-indigo-50/40"
            :class="{
              'cal-today': cellClasses(cell).today,
              'cal-selected': cellClasses(cell).selected,
              'cal-dim': cellClasses(cell).dim,
            }"
            @click="selectedDate = ymd(cell)"
          >
            <span
              class="cell-num mb-1 inline-flex h-5 w-5 items-center justify-center rounded-full text-[12px]"
              :class="cellClasses(cell).today ? 'bg-indigo-500 font-bold text-white' : 'text-zinc-600'"
            >
              {{ cell.getDate() }}
            </span>
            <div class="flex min-h-0 flex-1 flex-col gap-0.5 overflow-hidden">
              <span
                v-for="ev in (eventsByDay.get(ymd(cell)) ?? []).slice(0, 2)"
                :key="ev.id"
                class="flex items-center gap-1 truncate rounded-md px-1 py-0.5 text-[10.5px] leading-[16px]"
                :class="resultChipClass(ev.result)"
              >
                <span class="shrink-0 font-medium">{{ hm(ev.scheduled_at!) }}</span>
                <span class="truncate">{{ ev.company }}</span>
              </span>
              <span
                v-if="(eventsByDay.get(ymd(cell)) ?? []).length > 2"
                class="pl-1 text-[10.5px] text-zinc-400"
              >
                +{{ (eventsByDay.get(ymd(cell)) ?? []).length - 2 }} 场
              </span>
            </div>
          </button>
        </div>

        <!-- 周视图 -->
        <div v-else class="grid flex-1 grid-cols-7">
          <div
            v-for="cell in cells"
            :key="ymd(cell)"
            class="cal-cell flex min-h-0 flex-col gap-2 border-b border-r border-zinc-100 p-2 transition-colors last:border-r-0 hover:bg-indigo-50/40"
            :class="{
              'cal-today': cellClasses(cell).today,
              'cal-selected': cellClasses(cell).selected,
              'cal-dim': cellClasses(cell).dim,
            }"
            @click="selectedDate = ymd(cell)"
          >
            <div class="flex items-baseline gap-1.5 px-0.5">
              <span
                class="cell-num inline-flex h-5 items-center rounded-full px-1.5 text-[12px]"
                :class="cellClasses(cell).today ? 'bg-indigo-500 font-bold text-white' : 'text-zinc-600'"
              >
                {{ cell.getDate() }}
              </span>
              <span class="text-[11px] text-zinc-400">{{ eventsByDay.get(ymd(cell))?.length || '' }}</span>
            </div>
            <button
              v-for="ev in eventsByDay.get(ymd(cell)) ?? []"
              :key="ev.id"
              class="w-full rounded-lg border p-1.5 text-left transition-all hover:-translate-y-px hover:shadow-sm"
              :class="resultChipClass(ev.result).replace('text-', 'border-').replace('bg-', 'bg-')"
              @click.stop="openEdit(ev)"
            >
              <div class="flex items-center gap-1 text-[11px] font-semibold">
                <span>{{ hm(ev.scheduled_at!) }}</span>
                <span>{{ ROUND_LABEL[ev.round_type] ?? '面试' }}</span>
              </div>
              <div class="mt-0.5 truncate text-[11.5px] font-medium text-zinc-700">{{ ev.company }}</div>
            </button>
            <button
              class="mt-auto rounded-lg border border-dashed border-zinc-200 py-1 text-[11px] text-zinc-300 transition-colors hover:border-indigo-300 hover:text-indigo-500"
              @click.stop="selectedDate = ymd(cell); openCreate()"
            >
              + 排期
            </button>
          </div>
        </div>
      </div>

      <!-- 当日面板 -->
      <aside class="flex w-[300px] shrink-0 flex-col overflow-hidden rounded-2xl border border-zinc-200/70 bg-white">
        <div class="border-b border-zinc-100 px-4 py-3.5">
          <div class="text-[14px] font-bold text-zinc-800">
            {{ Number(selectedDate.slice(5, 7)) }}月{{ Number(selectedDate.slice(8, 10)) }}日
          </div>
          <div class="mt-0.5 text-[12px] text-zinc-400">
            {{ selectedEvents.length ? `${selectedEvents.length} 场面试` : '当天暂无安排' }}
          </div>
        </div>
        <div class="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto p-3.5">
          <div
            v-for="ev in selectedEvents"
            :key="ev.id"
            class="rounded-xl border border-zinc-200/80 bg-white p-3"
          >
            <div class="flex items-center gap-2">
              <span class="text-[13px] font-semibold text-zinc-800">{{ ev.company }}</span>
              <span
                class="rounded-md px-1.5 py-0.5 text-[10.5px] font-medium"
                :class="resultChipClass(ev.result)"
              >
                {{ ROUND_LABEL[ev.round_type] ?? '面试' }} · {{ ROUND_RESULT_META[ev.result]?.label }}
              </span>
            </div>
            <div class="mt-1 text-[12px] text-zinc-500">{{ ev.position }}</div>
            <div class="mt-1 text-[12px] text-zinc-400">{{ hm(ev.scheduled_at!) }}</div>
            <p v-if="ev.note" class="mt-1.5 rounded-lg bg-zinc-50 px-2 py-1.5 text-[11.5px] leading-relaxed text-zinc-500">
              {{ ev.note }}
            </p>
            <div class="mt-2 flex gap-1.5">
              <n-button size="tiny" quaternary type="primary" @click="openEdit(ev)">编辑</n-button>
              <n-button size="tiny" quaternary type="error" @click="confirmDelete(ev)">删除</n-button>
            </div>
          </div>

          <button
            class="rounded-xl border border-dashed border-zinc-200 py-2.5 text-[12px] text-zinc-400 transition-colors hover:border-indigo-300 hover:text-indigo-500"
            @click="openCreate"
          >
            + 在这一天添加面试
          </button>
        </div>
      </aside>
    </div>

    <RoundModal
      v-model:show="modalShow"
      :round="editing"
      :default-date="modalDefaultDate"
      :opportunities="opportunities"
      @saved="onSaved"
    />
  </div>
</template>
