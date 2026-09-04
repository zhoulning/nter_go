<script setup lang="ts">
import { provide, reactive, ref } from 'vue'
import type { Component } from 'vue'
import { useMessage } from 'naive-ui'
import {
  BookOutline,
  CalendarOutline,
  DocumentTextOutline,
  GridOutline,
  HomeOutline,
  MicOutline,
  PricetagOutline,
  RocketOutline,
  SettingsOutline,
  StatsChartOutline,
} from '@vicons/ionicons5'
import { OPEN_AI_SETTINGS, FOCUS_BOARD, OPEN_RESUME_DETAIL, OPEN_OPPORTUNITY_DETAIL } from '../injectionKeys'
import BoardView from '../views/BoardView.vue'
import CalendarView from '../views/CalendarView.vue'
import HomeView from '../views/HomeView.vue'
import OffersView from '../views/OffersView.vue'
import OpportunityDetailView from '../views/OpportunityDetailView.vue'
import QuestionBankView from '../views/QuestionBankView.vue'
import ResumeDetailView from '../views/ResumeDetailView.vue'
import ResumeLibraryView from '../views/ResumeLibraryView.vue'
import RecordingsView from '../views/RecordingsView.vue'
import StatsView from '../views/StatsView.vue'
import AiSettingsModal from './AiSettingsModal.vue'

interface NavItem {
  key: string
  label: string
  icon: Component
  ready?: boolean
}
interface NavSection {
  title: string
  items: NavItem[]
}

const message = useMessage()
// 支持 ?page=calendar 直达指定页面（可收藏）
const PAGE_KEYS = [
  'home',
  'board',
  'calendar',
  'questions',
  'resumes',
  'resume-detail',
  'opportunity-detail',
  'recordings',
  'stats',
  'offers',
]
const initialParams = new URLSearchParams(location.search)
const initialPage = initialParams.get('page') ?? 'home'
const active = ref(PAGE_KEYS.includes(initialPage) ? initialPage : 'home')
const aiSettingsShow = ref(false)

/** 把当前页面写进地址栏（?page=xxx），保证刷新/收藏都停留在当前页。
 *  保留 page/id 之外的参数（如看板的 view=list、筛选条件），切页来回不丢。 */
function setPageUrl(page: string, id?: number | null) {
  const keep = new URLSearchParams()
  new URLSearchParams(location.search).forEach((v, k) => {
    if (k !== 'page' && k !== 'id') keep.set(k, v)
  })
  keep.set('page', page)
  if (id != null) keep.set('id', String(id))
  history.replaceState(null, '', `?${keep.toString()}`)
}

// 首次进入时把（可能缺省或非法的）页面名规范化写回地址栏
if (initialParams.get('page') !== active.value) setPageUrl(active.value)

// 简历详情页的简历 id（?page=resume-detail&id=2 可直达）
const activeResumeId = ref<number | null>(
  initialPage === 'resume-detail' ? Number(initialParams.get('id')) || null : null,
)

// 岗位详情页的岗位 id（?page=opportunity-detail&id=3 可直达）
const activeOppId = ref<number | null>(
  initialPage === 'opportunity-detail' ? Number(initialParams.get('id')) || null : null,
)

// 懒挂载：首次访问后才渲染对应视图
const visited = reactive<Record<string, boolean>>({ [active.value]: true })

provide(OPEN_AI_SETTINGS, () => {
  aiSettingsShow.value = true
})

provide(OPEN_RESUME_DETAIL, (id: number) => {
  activeResumeId.value = id
  visited['resume-detail'] = true
  active.value = 'resume-detail'
  setPageUrl('resume-detail', id)
})

function onResumeBack() {
  visited.resumes = true
  active.value = 'resumes'
  setPageUrl('resumes')
}

provide(OPEN_OPPORTUNITY_DETAIL, (id: number) => {
  activeOppId.value = id
  visited['opportunity-detail'] = true
  active.value = 'opportunity-detail'
  setPageUrl('opportunity-detail', id)
})

function onOpportunityBack() {
  visited.board = true
  active.value = 'board'
  setPageUrl('board')
}

// 首页待办点击 → 跳看板并按公司过滤
const boardSearch = ref<string | null>(null)
provide(FOCUS_BOARD, (q?: string) => {
  visited.board = true
  active.value = 'board'
  boardSearch.value = q ?? ''
  setPageUrl('board')
})

const sections: NavSection[] = [
  {
    title: '工作台',
    items: [
      { key: 'home', label: '首页', icon: HomeOutline, ready: true },
      { key: 'board', label: '岗位跟踪', icon: GridOutline, ready: true },
    ],
  },
  {
    title: '面试准备',
    items: [
      { key: 'calendar', label: '面试日历', icon: CalendarOutline, ready: true },
      { key: 'questions', label: '题库 · 错题本', icon: BookOutline, ready: true },
      { key: 'resumes', label: '简历库', icon: DocumentTextOutline, ready: true },
    ],
  },
  {
    title: '复盘与决策',
    items: [
      { key: 'recordings', label: '面试复盘', icon: MicOutline, ready: true },
      { key: 'stats', label: '统计漏斗', icon: StatsChartOutline, ready: true },
      { key: 'offers', label: 'Offer 对比', icon: PricetagOutline, ready: true },
    ],
  },
]

function onNavClick(item: NavItem) {
  if (!item.ready) {
    message.info('该模块已列入需求文档，将在后续里程碑实现')
    return
  }
  visited[item.key] = true
  active.value = item.key
  setPageUrl(item.key)
}

/** 供首页等视图跳转到指定页面 */
function onNavGo(page: string) {
  const item = sections.flatMap((s) => s.items).find((i) => i.key === page)
  if (item) onNavClick(item)
}
</script>

<template>
  <div class="flex h-full">
    <!-- 侧边栏：窄窗口折叠为图标栏 -->
    <aside class="flex w-[64px] shrink-0 flex-col border-r border-zinc-200/70 bg-white lg:w-[224px]">
      <div class="flex items-center justify-center gap-2.5 px-5 pb-5 pt-6 lg:justify-start">
        <div
          class="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-500 text-white shadow-[0_4px_12px_rgba(99,102,241,0.4)]"
        >
          <n-icon :component="RocketOutline" :size="19" />
        </div>
        <div class="hidden lg:block">
          <div class="text-[15px] font-bold leading-tight tracking-tight text-zinc-900">
            Go面试
          </div>
          <div class="mt-0.5 text-[11px] leading-none text-zinc-400">面试跟踪管理 · v0.1</div>
        </div>
      </div>

      <nav class="flex-1 overflow-y-auto px-3">
        <div v-for="sec in sections" :key="sec.title" class="mb-4">
          <div
            class="mb-1 hidden px-3 text-[11px] font-semibold uppercase tracking-wider text-zinc-400 lg:block"
          >
            {{ sec.title }}
          </div>
          <button
            v-for="item in sec.items"
            :key="item.key"
            class="flex w-full items-center justify-center gap-2.5 rounded-lg px-3 py-[7px] text-[13px] transition-colors lg:justify-start"
            :class="
              active === item.key
                ? 'bg-indigo-50/90 font-semibold text-indigo-600'
                : 'text-zinc-600 hover:bg-zinc-100/80'
            "
            @click="onNavClick(item)"
          >
            <n-icon
              :component="item.icon"
              :size="16"
              :class="active === item.key ? 'text-indigo-500' : 'text-zinc-400'"
            />
            <span class="hidden lg:inline">{{ item.label }}</span>
          </button>
        </div>
      </nav>

      <div class="border-t border-zinc-100 p-3">
        <button
          class="flex w-full items-center justify-center gap-2.5 rounded-lg px-3 py-[7px] text-[13px] text-zinc-600 transition-colors hover:bg-zinc-100/80 lg:justify-start"
          @click="aiSettingsShow = true"
        >
          <n-icon :component="SettingsOutline" :size="16" class="text-zinc-400" />
          <span class="hidden lg:inline">设置</span>
        </button>
        <div
          class="mt-1 hidden rounded-lg bg-zinc-50 px-3 py-2 text-[11px] leading-relaxed text-zinc-400 lg:block"
        >
          本地运行 · 数据存储于 SQLite<br />
          不上传任何云端
        </div>
      </div>
    </aside>

    <!-- 主内容区 -->
    <main class="min-w-0 flex-1 overflow-hidden">
      <HomeView v-if="visited.home" v-show="active === 'home'" :go="onNavGo" />
      <BoardView v-show="active === 'board'" :search-query="boardSearch" />
      <CalendarView v-if="visited.calendar" v-show="active === 'calendar'" />
      <QuestionBankView v-if="visited.questions" v-show="active === 'questions'" />
      <ResumeLibraryView v-if="visited.resumes" v-show="active === 'resumes'" />
      <ResumeDetailView
        v-if="visited['resume-detail']"
        v-show="active === 'resume-detail'"
        :resume-id="activeResumeId"
        @back="onResumeBack"
      />
      <OpportunityDetailView
        v-if="visited['opportunity-detail']"
        v-show="active === 'opportunity-detail'"
        :opp-id="activeOppId"
        @back="onOpportunityBack"
      />
      <RecordingsView v-if="visited.recordings" v-show="active === 'recordings'" />
      <StatsView v-if="visited.stats" v-show="active === 'stats'" />
      <OffersView v-if="visited.offers" v-show="active === 'offers'" />
    </main>

    <AiSettingsModal v-model:show="aiSettingsShow" />
  </div>
</template>
