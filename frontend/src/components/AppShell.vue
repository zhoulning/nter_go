<script setup lang="ts">
import { computed, provide, reactive, ref } from 'vue'
import type { Component } from 'vue'
import { useMessage } from 'naive-ui'
import {
  BookOutline,
  CalendarOutline,
  DocumentTextOutline,
  GridOutline,
  HomeOutline,
  MenuOutline,
  MicOutline,
  PersonCircleOutline,
  PricetagOutline,
  SettingsOutline,
  FlashOutline,
  StatsChartOutline,
  PeopleOutline,
  TimeOutline,
} from '@vicons/ionicons5'
import { OPEN_AI_SETTINGS, FOCUS_BOARD, OPEN_RESUME_DETAIL, OPEN_OPPORTUNITY_DETAIL } from '../injectionKeys'
import { isAdmin, useAuth } from '../composables/useAuth'
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
import SettingsView from '../views/SettingsView.vue'
import UsersView from '../views/UsersView.vue'
import AuditLogView from '../views/AuditLogView.vue'
import CareerView from '../views/CareerView.vue'
import NotificationBell from './NotificationBell.vue'

interface NavItem {
  key: string
  label: string
  icon: Component
  ready?: boolean
  /** 标记为 AI 能力，导航文案右上角显示 AI 上标 */
  ai?: boolean
  /** 仅超级管理员可见 */
  adminOnly?: boolean
}
interface NavSection {
  title: string
  items: NavItem[]
}

const message = useMessage()
const auth = useAuth()
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
  'career',
  'settings',
  'users',
  'audit',
]
const initialParams = new URLSearchParams(location.search)
const initialPage = initialParams.get('page') ?? 'home'
const active = ref(PAGE_KEYS.includes(initialPage) ? initialPage : 'home')

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

// 详情页返回按钮文案：从列表视图进入时显示「返回列表」（看板视图状态镜像在 URL 的 view 参数里）
const oppDetailFromList = ref(initialParams.get('view') === 'list')

// 懒挂载：首次访问后才渲染对应视图
const visited = reactive<Record<string, boolean>>({ [active.value]: true })

provide(OPEN_AI_SETTINGS, () => {
  onNavGo('settings')
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
  openOppDetail(id)
})

/** 顶栏通知铃铛点击面试提醒时直达岗位详情 */
function openOppDetail(id: number) {
  oppDetailFromList.value = new URLSearchParams(location.search).get('view') === 'list'
  activeOppId.value = id
  visited['opportunity-detail'] = true
  active.value = 'opportunity-detail'
  setPageUrl('opportunity-detail', id)
}

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

const sections = computed<NavSection[]>(() => [
  {
    title: '工作台',
    items: [
      { key: 'home', label: '首页', icon: HomeOutline, ready: true },
      { key: 'board', label: '岗位跟踪', icon: GridOutline, ready: true },
      { key: 'calendar', label: '面试日程', icon: CalendarOutline, ready: true },
    ],
  },
  {
    title: '面试准备',
    items: [
      { key: 'questions', label: '题库管理', icon: BookOutline, ready: true, ai: true },
      { key: 'resumes', label: '简历管理', icon: DocumentTextOutline, ready: true, ai: true },
    ],
  },
  {
    title: '复盘与决策',
    items: [
      { key: 'recordings', label: '面试复盘', icon: MicOutline, ready: true },
      { key: 'stats', label: '数据洞察', icon: StatsChartOutline, ready: true },
      { key: 'offers', label: 'Offer 对比', icon: PricetagOutline, ready: true },
    ],
  },
  {
    title: '系统功能',
    items: [
      { key: 'career', label: '职业画像', icon: PersonCircleOutline, ready: true },
      { key: 'users', label: '用户管理', icon: PeopleOutline, ready: true, adminOnly: true },
      { key: 'audit', label: '操作日志', icon: TimeOutline, ready: true, adminOnly: true },
      { key: 'settings', label: '系统设置', icon: SettingsOutline, ready: true },
    ].filter((i) => !i.adminOnly || isAdmin.value),
  },
])

function onNavClick(item: NavItem) {
  if (!item.ready) {
    message.info('该模块已列入需求文档，将在后续里程碑实现')
    return
  }
  visited[item.key] = true
  active.value = item.key
  setPageUrl(item.key)
  moreShow.value = false
}

/** 供首页等视图跳转到指定页面 */
function onNavGo(page: string) {
  const item = sections.value.flatMap((s) => s.items).find((i) => i.key === page)
  if (item) onNavClick(item)
}

// ---- 登录用户：头像下拉 ----
const userMenuOptions = [
  { key: 'profile', label: '个人设置' },
  { key: 'logout', label: '退出登录' },
]

function onUserMenuSelect(key: string) {
  if (key === 'profile') onNavGo('settings')
  if (key === 'logout') {
    auth.logout().then(() => message.success('已退出登录'))
  }
}

const avatarInitial = computed(() => {
  const name = auth.state.user?.display_name || auth.state.user?.username || '?'
  return name.slice(0, 1).toUpperCase()
})

// ---- 移动端导航（<768px）：顶栏 + 底部标签栏 + 「更多」抽屉；PC 端仍走侧边栏 ----
const moreShow = ref(false)

/** 底部标签栏固定展示的高频页面 */
const TAB_KEYS = ['home', 'board', 'calendar', 'questions']
const tabItems = computed(() =>
  sections.value
    .flatMap((s) => s.items)
    .filter((i) => TAB_KEYS.includes(i.key))
    .map((i) => ({
      key: i.key,
      label: i.key === 'board' ? '岗位' : i.key === 'calendar' ? '日程' : i.key === 'questions' ? '题库' : i.label,
      icon: i.icon,
    })),
)

/** 「更多」抽屉里展示的其余页面 */
const moreItems = computed(() =>
  sections.value.flatMap((s) => s.items).filter((i) => !TAB_KEYS.includes(i.key)),
)

const PAGE_TITLES: Record<string, string> = {
  home: '首页',
  board: '岗位跟踪',
  calendar: '面试日程',
  questions: '题库管理',
  resumes: '简历管理',
  'resume-detail': '简历详情',
  'opportunity-detail': '岗位详情',
  recordings: '面试复盘',
  stats: '数据洞察',
  offers: 'Offer 对比',
  career: '职业画像',
  settings: '系统设置',
  users: '用户管理',
  audit: '操作日志',
}
const pageTitle = computed(() => PAGE_TITLES[active.value] ?? '进击の面试')

/** 详情页自带返回顶栏，移动端顶栏让位隐藏 */
const hideMobileHeader = computed(
  () => active.value === 'resume-detail' || active.value === 'opportunity-detail',
)

const moreActive = computed(() =>
  ['resumes', 'resume-detail', 'recordings', 'stats', 'offers', 'settings', 'users', 'audit'].includes(
    active.value,
  ),
)

/** 底部标签是否高亮（岗位详情归入「岗位」标签） */
function tabActive(key: string) {
  if (key === 'board') return active.value === 'board' || active.value === 'opportunity-detail'
  return active.value === key
}
</script>

<template>
  <div class="flex h-full max-md:flex-col">
    <!-- 移动端顶栏：详情页自带返回顶栏时隐藏 -->
    <header
      v-if="!hideMobileHeader"
      class="flex shrink-0 items-center gap-2.5 border-b border-zinc-200/70 bg-white px-4 py-2.5 md:hidden"
    >
      <div
        class="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-500 text-white shadow-[0_2px_8px_rgba(99,102,241,0.35)]"
      >
        <n-icon :component="FlashOutline" :size="16" />
      </div>
      <div class="min-w-0">
        <div class="truncate text-[15px] font-bold leading-tight text-zinc-900">{{ pageTitle }}</div>
        <div class="mt-px text-[10px] leading-none text-zinc-400">进击の面试</div>
      </div>
      <div class="ml-auto flex items-center gap-1">
        <NotificationBell @open-opportunity="openOppDetail" />
        <n-dropdown trigger="click" :options="userMenuOptions" @select="onUserMenuSelect">
          <button class="grid h-9 w-9 place-items-center rounded-lg transition-colors hover:bg-zinc-100">
            <div
              class="grid h-8 w-8 place-items-center overflow-hidden rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 text-[12px] font-bold text-white"
            >
              <img
                v-if="auth.state.user?.avatar_url"
                :src="auth.state.user.avatar_url"
                class="h-full w-full object-cover"
                alt="头像"
              />
              <template v-else>{{ avatarInitial }}</template>
            </div>
          </button>
        </n-dropdown>
      </div>
    </header>

    <!-- 侧边栏：窄窗口折叠为图标栏；移动端隐藏，改用顶栏 + 底部标签栏 -->
    <aside class="flex w-[64px] shrink-0 flex-col border-r border-zinc-200/70 bg-white max-md:hidden lg:w-[224px]">
        <div class="flex items-center justify-center gap-2.5 px-5 pb-5 pt-6 lg:justify-start">
          <div
            class="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-500 text-white shadow-[0_4px_12px_rgba(99,102,241,0.4)]"
          >
            <n-icon :component="FlashOutline" :size="19" />
          </div>
          <div class="hidden lg:block">
            <div class="text-[15px] font-bold leading-tight tracking-tight text-zinc-900">
              进击の面试
            </div>
            <div class="mt-0.5 text-[11px] leading-none text-zinc-400">面试跟踪管理 · v0.2</div>
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
              <span class="hidden items-center gap-1 lg:inline-flex">
                {{ item.label }}
                <span
                  v-if="item.ai"
                  class="-translate-y-[6px] rounded-[3px] bg-gradient-to-r from-indigo-500 to-violet-500 px-[3px] text-[8px] font-bold leading-[12px] text-white"
                >AI</span>
              </span>
            </button>
          </div>
        </nav>

        <div class="border-t border-zinc-100 p-3">
          <!-- 用户卡片：头像 + 名字/角色 + 通知 -->
          <div
            class="flex flex-col items-center gap-1.5 rounded-2xl bg-zinc-50 p-2 max-lg:bg-transparent max-lg:p-0 lg:flex-row lg:gap-2.5"
          >
            <n-dropdown trigger="click" :options="userMenuOptions" @select="onUserMenuSelect">
              <div
                class="flex cursor-pointer items-center justify-center gap-2.5 rounded-lg lg:min-w-0 lg:flex-1 lg:justify-start"
              >
                <div
                  class="grid h-9 w-9 shrink-0 place-items-center overflow-hidden rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 text-[13px] font-bold text-white"
                >
                  <img
                    v-if="auth.state.user?.avatar_url"
                    :src="auth.state.user.avatar_url"
                    class="h-full w-full object-cover"
                    alt="头像"
                  />
                  <template v-else>{{ avatarInitial }}</template>
                </div>
                <div class="hidden min-w-0 lg:block">
                  <div class="truncate text-[13px] font-semibold leading-tight text-zinc-800">
                    {{ auth.state.user?.display_name || auth.state.user?.username }}
                  </div>
                  <div class="mt-0.5 text-[11px] leading-none text-zinc-400">
                    {{ auth.state.user?.role === 'admin' ? '超级管理员' : '普通用户' }}
                  </div>
                </div>
              </div>
            </n-dropdown>
            <NotificationBell @open-opportunity="openOppDetail" />
          </div>
        </div>
      </aside>

      <!-- 主内容区：移动端底部留出标签栏高度（含安全区） -->
      <main
        class="min-w-0 flex-1 overflow-hidden max-md:w-full max-md:pb-[calc(56px+env(safe-area-inset-bottom))]"
      >
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
          :from-list="oppDetailFromList"
          @back="onOpportunityBack"
        />
        <RecordingsView v-if="visited.recordings" v-show="active === 'recordings'" />
        <StatsView v-if="visited.stats" v-show="active === 'stats'" />
        <OffersView v-if="visited.offers" v-show="active === 'offers'" />
        <SettingsView v-if="visited.settings" v-show="active === 'settings'" />
        <CareerView v-if="visited.career" v-show="active === 'career'" />
        <UsersView v-if="visited.users" v-show="active === 'users'" />
        <AuditLogView v-if="visited.audit" v-show="active === 'audit'" />
      </main>

    <!-- 移动端底部标签栏 -->
    <nav
      class="fixed inset-x-0 bottom-0 z-40 flex border-t border-zinc-200/70 bg-white/95 backdrop-blur md:hidden"
      style="padding-bottom: env(safe-area-inset-bottom)"
    >
      <button
        v-for="t in tabItems"
        :key="t.key"
        class="flex flex-1 flex-col items-center gap-0.5 py-1.5 text-[10px] font-medium transition-colors"
        :class="tabActive(t.key) ? 'text-indigo-600' : 'text-zinc-400'"
        @click="onNavClick(sections.flatMap((s) => s.items).find((i) => i.key === t.key)!)"
      >
        <n-icon :component="t.icon" :size="20" />
        {{ t.label }}
      </button>
      <button
        class="flex flex-1 flex-col items-center gap-0.5 py-1.5 text-[10px] font-medium transition-colors"
        :class="moreActive ? 'text-indigo-600' : 'text-zinc-400'"
        @click="moreShow = true"
      >
        <n-icon :component="MenuOutline" :size="20" />
        更多
      </button>
    </nav>

    <!-- 移动端「更多」抽屉 -->
    <n-drawer v-model:show="moreShow" :placement="'bottom'" :height="380" :auto-focus="false">
      <n-drawer-content :body-content-style="{ padding: '16px 16px calc(16px + env(safe-area-inset-bottom))' }">
        <div class="mb-3 text-[13px] font-bold text-zinc-800">更多页面</div>
        <div class="grid grid-cols-2 gap-2">
          <button
            v-for="item in moreItems"
            :key="item.key"
            class="flex items-center gap-2.5 rounded-xl border px-3 py-2.5 text-left text-[13px] transition-colors"
            :class="
              active === item.key
                ? 'border-indigo-200 bg-indigo-50/90 font-semibold text-indigo-600'
                : 'border-zinc-100 bg-white text-zinc-600 active:bg-zinc-50'
            "
            @click="onNavClick(item)"
          >
            <n-icon
              :component="item.icon"
              :size="17"
              :class="active === item.key ? 'text-indigo-500' : 'text-zinc-400'"
            />
            <span class="min-w-0 flex-1 truncate">{{ item.label }}</span>
            <span
              v-if="item.ai"
              class="shrink-0 rounded-[3px] bg-gradient-to-r from-indigo-500 to-violet-500 px-[3px] text-[8px] font-bold leading-[12px] text-white"
            >AI</span>
          </button>
        </div>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>
