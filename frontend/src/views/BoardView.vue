<script setup lang="ts">
import { computed, h, inject, onMounted, ref, watch } from 'vue'
import { NButton, NDataTable, useDialog, useMessage } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { AddOutline, GridOutline, ListOutline, SearchOutline } from '@vicons/ionicons5'
import { api } from '../api'
import type { Opportunity, Resume } from '../types'
import {
  CHANNELS,
  PRIORITY_CLASS,
  ROUND_LABEL,
  STATUSES,
  avatarGradient,
  statusLabel,
} from '../types'
import { daysSince, eventLabel, shortDate } from '../utils'
import { OPEN_OPPORTUNITY_DETAIL } from '../injectionKeys'
import OpportunityCard from '../components/OpportunityCard.vue'
import OpportunityModal from '../components/OpportunityModal.vue'

// 外部跳转聚焦（如首页待办点击 → 按公司过滤看板）
const props = defineProps<{ searchQuery?: string | null }>()

const message = useMessage()
const dialog = useDialog()
const openOpportunityDetail = inject(OPEN_OPPORTUNITY_DETAIL, null)

const opportunities = ref<Opportunity[]>([])
const resumes = ref<Resume[]>([])
const loading = ref(true)
const view = ref<'board' | 'list'>(location.search.includes('view=list') ? 'list' : 'board')

/** 视图切换同步进地址栏（?view=list），刷新后保持当前视图 */
function setView(v: 'board' | 'list') {
  view.value = v
  const params = new URLSearchParams(location.search)
  if (v === 'list') params.set('view', 'list')
  else params.delete('view')
  history.replaceState(null, '', `?${params.toString()}`)
}

// 筛选条件（null = 不限）
const search = ref('')
watch(
  () => props.searchQuery,
  (v) => {
    if (v != null) search.value = v
  },
)
const fStatus = ref<string[] | null>(null)
const fPriority = ref<string[] | null>(null)
const fChannel = ref<string[] | null>(null)
const fCity = ref<string[] | null>(null)

const modalShow = ref(false)
const editing = ref<Opportunity | null>(null)

// 拖拽状态
const dragId = ref<number | null>(null)
const overColumn = ref<string | null>(null)

/** 从 URL 读取逗号分隔的筛选参数，如 ?city=上海,深圳（筛选状态可分享/刷新保留） */
function parseListParam(name: string): string[] | null {
  const raw = new URLSearchParams(location.search).get(name)
  if (!raw) return null
  const list = raw
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
  return list.length ? list : null
}

async function load(silent = false) {
  if (!silent) loading.value = true
  try {
    const data = await api.listOpportunities()
    opportunities.value = data.items
  } catch (e) {
    message.error((e as Error).message || '加载失败')
  } finally {
    loading.value = false
  }
}
onMounted(() => {
  fStatus.value = parseListParam('status')
  fPriority.value = parseListParam('priority')
  fChannel.value = parseListParam('channel')
  fCity.value = parseListParam('city')
  load()
  api
    .listResumes()
    .then((data) => (resumes.value = data.items))
    .catch(() => {})
})

// ---- 筛选 ----
const filtered = computed(() => {
  let list = opportunities.value
  const kw = search.value.trim().toLowerCase()
  if (kw) {
    list = list.filter((o) =>
      [o.company, o.position, o.city, o.department].some((v) =>
        v?.toLowerCase().includes(kw),
      ),
    )
  }
  if (fStatus.value?.length) list = list.filter((o) => fStatus.value!.includes(o.status))
  if (fPriority.value?.length) list = list.filter((o) => fPriority.value!.includes(o.priority))
  if (fChannel.value?.length) list = list.filter((o) => fChannel.value!.includes(o.channel ?? ''))
  if (fCity.value?.length) list = list.filter((o) => fCity.value!.includes(o.city ?? ''))
  return list
})

const hasActiveFilter = computed(
  () =>
    !!search.value.trim() ||
    !!fStatus.value?.length ||
    !!fPriority.value?.length ||
    !!fChannel.value?.length ||
    !!fCity.value?.length,
)

function clearFilters() {
  search.value = ''
  fStatus.value = null
  fPriority.value = null
  fChannel.value = null
  fCity.value = null
}

const statusOptions = STATUSES.map((s) => ({ label: s.label, value: s.key }))
const priorityOptions = ['S', 'A', 'B'].map((v) => ({ label: v, value: v }))
const channelOptions = computed(() => {
  const set = new Set<string>(CHANNELS)
  opportunities.value.forEach((o) => o.channel && set.add(o.channel))
  return [...set].map((v) => ({ label: v, value: v }))
})
const cityOptions = computed(() => {
  const set = new Set<string>()
  opportunities.value.forEach((o) => o.city && set.add(o.city))
  return [...set].map((v) => ({ label: v, value: v }))
})

// ---- 排序 ----
const PRIORITY_ORDER: Record<string, number> = { S: 0, A: 1, B: 2 }

function sortOpps(list: Opportunity[]): Opportunity[] {
  return [...list].sort((a, b) => {
    const p = (PRIORITY_ORDER[a.priority] ?? 9) - (PRIORITY_ORDER[b.priority] ?? 9)
    if (p !== 0) return p
    const ta = a.next_event?.scheduled_at
      ? new Date(a.next_event.scheduled_at).getTime()
      : Infinity
    const tb = b.next_event?.scheduled_at
      ? new Date(b.next_event.scheduled_at).getTime()
      : Infinity
    if (ta !== tb) return ta - tb
    return b.updated_at.localeCompare(a.updated_at)
  })
}

const columns = computed(() =>
  STATUSES.map((s) => ({
    ...s,
    items: sortOpps(filtered.value.filter((o) => o.status === s.key)),
  })),
)

const listRows = computed(() => sortOpps(filtered.value))

// 顶部统计
const interviewingCount = computed(
  () => opportunities.value.filter((o) => o.status === 'interviewing').length,
)
const offerCount = computed(
  () =>
    opportunities.value.filter((o) => o.status === 'offer' || o.status === 'accepted').length,
)
const upcomingCount = computed(() => {
  const now = Date.now()
  const week = 7 * 86400000
  return opportunities.value.filter((o) => {
    const t = o.next_event?.scheduled_at
      ? new Date(o.next_event.scheduled_at).getTime()
      : null
    return t !== null && t >= now && t <= now + week
  }).length
})

// ---- 拖拽 ----
function onDragStart(opp: Opportunity, e: DragEvent) {
  dragId.value = opp.id
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(opp.id))
  }
}
function onDragEnd() {
  dragId.value = null
  overColumn.value = null
}
function onDragOver(status: string, e: DragEvent) {
  e.preventDefault()
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'
  overColumn.value = status
}
async function onDrop(status: string) {
  const id = dragId.value
  overColumn.value = null
  dragId.value = null
  if (id == null) return
  const opp = opportunities.value.find((o) => o.id === id)
  if (!opp || opp.status === status) return
  const old = opp.status
  opp.status = status // 乐观更新，失败回滚
  try {
    await api.updateOpportunity(id, { status })
    await load(true)
    message.success(`「${opp.company}」已移至「${statusLabel(status)}」`)
  } catch (e) {
    opp.status = old
    message.error((e as Error).message || '更新失败')
  }
}

// ---- 增删改查 ----
function openCreate() {
  editing.value = null
  modalShow.value = true
}
function openEdit(opp: Opportunity) {
  editing.value = opp
  modalShow.value = true
}
function openDetail(opp: Opportunity) {
  // 详情页承载全部信息（基本信息 / JD / 调研笔记 / 匹配度 / 轮次 / Offer），点击直接跳转
  if (openOpportunityDetail) {
    openOpportunityDetail(opp.id)
  } else {
    message.warning('详情页不可用')
  }
}
function onSaved(opp: Opportunity, isNew: boolean) {
  message.success(isNew ? `已添加「${opp.company} · ${opp.position}」` : '已保存')
  load(true)
}
function confirmDelete(opp: Opportunity) {
  dialog.warning({
    title: '删除岗位',
    content: `确定删除「${opp.company} · ${opp.position}」吗？该操作不可恢复。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.deleteOpportunity(opp.id)
        message.success('已删除')
        await load(true)
      } catch (e) {
        message.error((e as Error).message || '删除失败')
      }
    },
  })
}

// ---- 列表视图 ----
function nextChipClass(dt: string): string {
  const d = daysUntilLocal(dt)
  if (d <= 1) return 'bg-rose-50 text-rose-600'
  if (d <= 3) return 'bg-amber-50 text-amber-600'
  return 'bg-sky-50 text-sky-600'
}
function daysUntilLocal(dt: string): number {
  const d = new Date(dt)
  const startToday = new Date()
  startToday.setHours(0, 0, 0, 0)
  return Math.round(
    (new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime() -
      startToday.getTime()) /
      86400000,
  )
}

const tableColumns: DataTableColumns<Opportunity> = [
  {
    title: '岗位',
    key: 'company',
    minWidth: 170,
    render(row) {
      return h('div', { class: 'flex items-center gap-2.5' }, [
        h(
          'div',
          {
            class:
              'grid h-8 w-8 shrink-0 place-items-center rounded-lg text-[13px] font-bold text-white',
            style: { background: avatarGradient(row.company) },
          },
          row.company.slice(0, 1),
        ),
        h('div', { class: 'min-w-0' }, [
          h(
            'div',
            { class: 'truncate text-[13px] font-semibold text-zinc-800' },
            row.company,
          ),
          h(
            'div',
            { class: 'truncate text-[12px] text-zinc-500' },
            row.position + (row.department ? ` · ${row.department}` : ''),
          ),
        ]),
      ])
    },
  },
  {
    title: '状态',
    key: 'status',
    width: 110,
    render(row) {
      const meta = STATUSES.find((s) => s.key === row.status)
      return h('span', { class: 'inline-flex items-center gap-1.5 text-[12.5px] text-zinc-600' }, [
        h('span', {
          class: 'h-1.5 w-1.5 rounded-full',
          style: { background: meta?.color ?? '#94a3b8' },
        }),
        meta?.label ?? row.status,
      ])
    },
  },
  {
    title: '优先级',
    key: 'priority',
    width: 84,
    render(row) {
      return h(
        'span',
        {
          class:
            'rounded-md border px-1.5 text-[11px] font-bold leading-[18px] ' +
            (PRIORITY_CLASS[row.priority] ?? PRIORITY_CLASS.B),
        },
        row.priority,
      )
    },
  },
  {
    title: '投递时间',
    key: 'applied_at',
    width: 105,
    render: (row) =>
      row.applied_at
        ? h('span', { class: 'text-[12.5px] text-zinc-600 tabular-nums' }, shortDate(row.applied_at))
        : h('span', { class: 'text-[12px] text-zinc-300' }, '未投递'),
    sorter: (a, b) =>
      (a.applied_at ? Date.parse(a.applied_at) : Infinity) -
      (b.applied_at ? Date.parse(b.applied_at) : Infinity),
  },
  { title: '城市', key: 'city', width: 90, render: (row) => row.city ?? '—' },
  {
    title: '薪资',
    key: 'salary_range',
    width: 145,
    render: (row) =>
      row.salary_range
        ? h('span', { class: 'text-[12.5px] font-medium text-emerald-600' }, row.salary_range)
        : '—',
  },
  { title: '渠道', key: 'channel', width: 100, render: (row) => row.channel ?? '—' },
  {
    title: '下场面试',
    key: 'next_event',
    width: 175,
    render(row) {
      const ev = row.next_event
      if (!ev?.scheduled_at)
        return h('span', { class: 'text-[12px] text-zinc-300' }, '暂无安排')
      const label = ROUND_LABEL[ev.round_type] ?? '面试'
      return h(
        'span',
        {
          class:
            'inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11.5px] font-medium ' +
            nextChipClass(ev.scheduled_at),
        },
        `${label} · ${eventLabel(ev.scheduled_at)}`,
      )
    },
  },
  {
    title: '停留',
    key: 'days',
    width: 90,
    render: (row) =>
      h('span', { class: 'text-[12.5px] text-zinc-500' }, `${daysSince(row.status_changed_at)} 天`),
    sorter: (a, b) => daysSince(a.status_changed_at) - daysSince(b.status_changed_at),
  },
  {
    title: '操作',
    key: 'op',
    width: 164,
    render(row) {
      return h('div', { class: 'flex gap-1' }, [
        h(
          NButton,
          {
            size: 'tiny',
            quaternary: true,
            onClick: (e: MouseEvent) => {
              e.stopPropagation()
              openDetail(row)
            },
          },
          { default: () => '详情' },
        ),
        h(
          NButton,
          {
            size: 'tiny',
            quaternary: true,
            type: 'primary',
            onClick: (e: MouseEvent) => {
              e.stopPropagation()
              openEdit(row)
            },
          },
          { default: () => '编辑' },
        ),
        h(
          NButton,
          {
            size: 'tiny',
            quaternary: true,
            type: 'error',
            onClick: (e: MouseEvent) => {
              e.stopPropagation()
              confirmDelete(row)
            },
          },
          { default: () => '删除' },
        ),
      ])
    },
  },
]

const rowProps = (row: Opportunity) => ({
  style: 'cursor: pointer;',
  onClick: () => openDetail(row),
})
</script>

<template>
  <div class="flex h-full flex-col">
    <!-- 页头 -->
    <header class="fade-up flex flex-wrap items-end justify-between gap-4 px-7 pb-3 pt-6">
      <div>
        <h1 class="text-[21px] font-bold tracking-tight text-zinc-900">岗位跟踪</h1>
        <p class="mt-1 text-[13px] text-zinc-400">
          共 {{ opportunities.length }} 个在跟进岗位 · 看板拖拽更新进度，点击卡片或列表行查看详情
        </p>
      </div>
      <div class="flex items-center gap-3">
        <div class="hidden items-center gap-2 lg:flex">
          <span class="stat-chip"><span class="dot" style="background: #f59e0b" />面试中 {{ interviewingCount }}</span>
          <span class="stat-chip"><span class="dot" style="background: #10b981" />Offer {{ offerCount }}</span>
          <span class="stat-chip"><span class="dot" style="background: #8b5cf6" />7 天内面试 {{ upcomingCount }} 场</span>
        </div>
        <n-input
          v-model:value="search"
          round
          clearable
          placeholder="搜索公司 / 岗位 / 城市"
          size="small"
          style="width: 200px"
        >
          <template #prefix>
            <n-icon :component="SearchOutline" :size="15" class="text-zinc-400" />
          </template>
        </n-input>
        <button class="btn-gradient" @click="openCreate">
          <n-icon :component="AddOutline" :size="16" />
          新增岗位
        </button>
      </div>
    </header>

    <!-- 视图切换 + 多筛选 -->
    <div class="flex flex-wrap items-center justify-between gap-3 px-7 pb-3">
      <div class="seg">
        <button :class="view === 'board' && 'active'" @click="setView('board')">
          <n-icon :component="GridOutline" :size="14" /> 看板
        </button>
        <button :class="view === 'list' && 'active'" @click="setView('list')">
          <n-icon :component="ListOutline" :size="14" /> 列表
        </button>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <n-select
          v-model:value="fStatus"
          multiple
          clearable
          size="small"
          placeholder="状态"
          :options="statusOptions"
          max-tag-count="responsive"
          class="filter-select"
          style="width: 130px"
        />
        <n-select
          v-model:value="fPriority"
          multiple
          clearable
          size="small"
          placeholder="优先级"
          :options="priorityOptions"
          max-tag-count="responsive"
          class="filter-select"
          style="width: 110px"
        />
        <n-select
          v-model:value="fChannel"
          multiple
          clearable
          size="small"
          placeholder="渠道"
          :options="channelOptions"
          max-tag-count="responsive"
          class="filter-select"
          style="width: 150px"
        />
        <n-select
          v-model:value="fCity"
          multiple
          clearable
          size="small"
          placeholder="城市"
          :options="cityOptions"
          max-tag-count="responsive"
          class="filter-select"
          style="width: 130px"
        />
        <n-button v-if="hasActiveFilter" quaternary size="small" @click="clearFilters">
          清空筛选
        </n-button>
        <span class="text-[12px] tabular-nums text-zinc-400">
          {{ filtered.length }} / {{ opportunities.length }}
        </span>
      </div>
    </div>

    <!-- 看板视图 -->
    <div v-show="view === 'board'" class="min-h-0 flex-1 overflow-x-auto px-7 pb-4">
      <div v-if="loading" class="grid h-full place-items-center">
        <span class="text-sm text-zinc-400">正在加载看板…</span>
      </div>
      <div v-else class="fade-up-d1 flex h-full items-stretch gap-3.5">
        <section
          v-for="col in columns"
          :key="col.key"
          class="flex h-full min-w-[262px] max-w-[350px] flex-1 flex-col rounded-2xl bg-[#edeef3]/90 p-2.5 transition-all"
          :class="{ 'column-drag-over': overColumn === col.key }"
          @dragover="onDragOver(col.key, $event)"
          @drop.prevent="onDrop(col.key)"
        >
          <div class="flex items-center gap-2 px-1.5 pb-2.5 pt-1">
            <span class="h-2 w-2 rounded-full" :style="{ background: col.color }" />
            <span class="text-[13px] font-semibold text-zinc-600">{{ col.label }}</span>
            <span
              class="rounded-full border border-zinc-200/70 bg-white px-1.5 text-[11px] leading-[18px] text-zinc-500"
            >
              {{ col.items.length }}
            </span>
          </div>

          <div class="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto">
            <TransitionGroup name="card">
              <OpportunityCard
                v-for="opp in col.items"
                :key="opp.id"
                :opp="opp"
                :dragging="dragId === opp.id"
                @dragstart="onDragStart(opp, $event)"
                @dragend="onDragEnd"
                @detail="openDetail(opp)"
                @edit="openEdit(opp)"
                @delete="confirmDelete(opp)"
              />
            </TransitionGroup>
            <div
              v-if="col.items.length === 0"
              class="flex flex-1 items-center justify-center rounded-xl border-2 border-dashed border-zinc-200 py-7 text-center text-xs text-zinc-400"
            >
              {{ dragId != null ? '松手放到这里' : '暂无岗位' }}
            </div>
          </div>
        </section>
      </div>
    </div>

    <!-- 列表视图 -->
    <div v-show="view === 'list' && !loading" class="fade-up-d1 min-h-0 flex-1 px-7 pb-4">
      <div class="h-full overflow-auto rounded-2xl border border-zinc-200/70 bg-white p-2">
        <n-data-table
          :columns="tableColumns"
          :data="listRows"
          :row-key="(row: Opportunity) => row.id"
          :row-props="rowProps"
          :loading="loading"
          :bordered="false"
          :single-line="false"
          :pagination="false"
          :scroll-x="1240"
          size="small"
        />
      </div>
    </div>

    <OpportunityModal
      v-model:show="modalShow"
      :opportunity="editing"
      :resumes="resumes"
      @saved="onSaved"
    />
  </div>
</template>
