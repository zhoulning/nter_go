<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useDialog, useMessage } from 'naive-ui'
import {
  AddOutline,
  ChevronDownOutline,
  ChevronUpOutline,
  SearchOutline,
  SparklesOutline,
} from '@vicons/ionicons5'
import { api } from '../api'
import type { Opportunity, Question } from '../types'
import {
  DIFFICULTY_META,
  MASTERY_META,
  QUESTION_SOURCE_LABEL,
  ROUND_LABEL,
  avatarGradient,
} from '../types'
import { shortDate } from '../utils'
import QuestionModal from '../components/QuestionModal.vue'

const message = useMessage()
const dialog = useDialog()

const questions = ref<Question[]>([])
const opportunities = ref<Opportunity[]>([])
const dimensions = ref<string[]>([])
const loading = ref(true)
const mode = ref<'all' | 'wrong'>('all')

const search = ref('')
const fDimension = ref<string | null>(null)
const fMastery = ref<string | null>(null)
const fDifficulty = ref<string | null>(null)

const modalShow = ref(false)
const editing = ref<Question | null>(null)
const aiBusyId = ref<number | null>(null)
const expandedId = ref<number | null>(null)

async function load() {
  loading.value = true
  try {
    const [q, meta, opps] = await Promise.all([
      api.listQuestions(),
      api.questionMeta(),
      api.listOpportunities(),
    ])
    questions.value = q.items
    dimensions.value = meta.dimensions
    opportunities.value = opps.items
  } catch (e) {
    message.error((e as Error).message || '加载失败')
  } finally {
    loading.value = false
  }
}
onMounted(() => {
  load()
  document.addEventListener('click', onGlobalClick)
})
onBeforeUnmount(() => document.removeEventListener('click', onGlobalClick))

/** 错题判定：掌握状态为不会/模糊，或自评分 ≤ 3 */
function isWrong(q: Question): boolean {
  return q.mastery !== 'mastered' || (q.self_rating != null && q.self_rating <= 3)
}

const wrongCount = computed(() => questions.value.filter(isWrong).length)

const filtered = computed(() => {
  let list = questions.value
  if (mode.value === 'wrong') list = list.filter(isWrong)
  const kw = search.value.trim().toLowerCase()
  if (kw) {
    list = list.filter((q) => {
      const hay = [
        q.content,
        q.dimension,
        q.opportunity?.company,
        q.resume_name,
        ...(q.sources ?? []).map((s) => s.company ?? ''),
      ]
      return hay.some((v) => v?.toLowerCase().includes(kw))
    })
  }
  if (fDimension.value) list = list.filter((q) => q.dimension === fDimension.value)
  if (fMastery.value) list = list.filter((q) => q.mastery === fMastery.value)
  if (fDifficulty.value) list = list.filter((q) => q.difficulty === fDifficulty.value)
  return list
})

const hasActiveFilter = computed(
  () => !!search.value.trim() || !!fDimension.value || !!fMastery.value || !!fDifficulty.value,
)

function clearFilters() {
  search.value = ''
  fDimension.value = null
  fMastery.value = null
  fDifficulty.value = null
}

const dimensionOptions = computed(() => dimensions.value.map((d) => ({ label: d, value: d })))
const masteryOptions = Object.entries(MASTERY_META).map(([value, m]) => ({ label: m.label, value }))
const difficultyOptions = Object.entries(DIFFICULTY_META).map(([value, m]) => ({
  label: m.label,
  value,
}))

/** 来源摘要：单来源「公司 · 轮次」，多来源「A 等 N 处」 */
function sourceSummary(q: Question): string {
  const srcs = q.sources ?? []
  if (srcs.length === 0) return ''
  const parts = srcs.map(
    (s) => `${s.company ?? '未知公司'}${s.round_type ? ` · ${ROUND_LABEL[s.round_type] ?? '面试'}` : ''}`,
  )
  return parts.length === 1 ? parts[0] : `${parts[0]} 等 ${parts.length} 处`
}

function sourceCompanies(q: Question): string[] {
  return [...new Set((q.sources ?? []).map((s) => s.company ?? ''))] as string[]
}

function sourcesTitle(q: Question): string {
  return (q.sources ?? [])
    .map((s) => `${s.company ?? ''}${s.round_type ? ` · ${ROUND_LABEL[s.round_type] ?? ''}` : ''}`)
    .join('，')
}

/** 轻量 Markdown：编号要点 + **加粗**，用于答案的排版展示 */
function renderMdLite(text: string): string {
  const esc = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const bold = (s: string) =>
    s.replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-zinc-900">$1</strong>')
  return esc
    .split('\n')
    .map((raw) => {
      const t = raw.trim()
      if (!t) return ''
      const m = t.match(/^(\d{1,2})[.、)）]\s*(.+)$/)
      if (m) {
        return `<div class="mb-2 flex gap-2 last:mb-0"><span class="shrink-0 font-bold text-indigo-500">${m[1]}.</span><span>${bold(m[2])}</span></div>`
      }
      return `<p class="mb-2 last:mb-0">${bold(t)}</p>`
    })
    .join('')
}

function openCreate() {
  editing.value = null
  modalShow.value = true
}
function openEdit(q: Question) {
  editing.value = q
  modalShow.value = true
}
function onSaved(_q: Question, isNew: boolean) {
  message.success(isNew ? '题目已加入题库' : '已保存')
  load()
}

function toggleDetail(q: Question) {
  expandedId.value = expandedId.value === q.id ? null : q.id
}

function genAnswer(q: Question) {
  // 已有答案：先确认是否覆盖
  if (q.answer_spoken) {
    const short = q.content.length > 30 ? `${q.content.slice(0, 30)}…` : q.content
    dialog.warning({
      title: '重新生成答案',
      content: `「${short}」已有 AI 口述版答案，重新生成将覆盖现有内容，确定继续吗？`,
      positiveText: '重新生成',
      negativeText: '取消',
      onPositiveClick: () => doGenerate(q),
    })
    return
  }
  doGenerate(q)
}

async function doGenerate(q: Question) {
  aiBusyId.value = q.id
  try {
    const res = await api.generateAnswer({ question_id: q.id })
    if (res.answer_spoken) {
      const local = questions.value.find((x) => x.id === q.id)
      if (local) local.answer_spoken = res.answer_spoken
      message.success('口述版答案已生成')
      expandedId.value = q.id // 生成后自动展开浮框展示
    } else {
      message.warning('AI 没有返回有效答案，请重试')
    }
  } catch (e) {
    message.error((e as Error).message || 'AI 生成失败', { duration: 6000 })
  } finally {
    aiBusyId.value = null
  }
}

// 点击浮框以外区域时收起
function onGlobalClick(e: MouseEvent) {
  if (expandedId.value == null) return
  const t = e.target as HTMLElement | null
  if (!t) return
  if (t.closest('[data-answer-panel]')) return // 浮框内部
  if (t.closest('[data-detail-toggle]')) return // 详情/收起按钮
  if (t.closest('[data-keep-panel]')) return // AI 答案按钮
  expandedId.value = null
}

async function markMastered(q: Question) {
  try {
    await api.updateQuestion(q.id, { mastery: 'mastered' })
    message.success('已标记掌握')
    await load()
  } catch (e) {
    message.error((e as Error).message || '操作失败')
  }
}

async function toggleReview(q: Question) {
  try {
    await api.updateQuestion(q.id, { review_done: !q.review_done })
    await load()
  } catch (e) {
    message.error((e as Error).message || '操作失败')
  }
}

function confirmDelete(q: Question) {
  dialog.warning({
    title: '删除题目',
    content: '确定从题库中删除这道题吗？',
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.deleteQuestion(q.id)
        message.success('已删除')
        await load()
      } catch (e) {
        message.error((e as Error).message || '删除失败')
      }
    },
  })
}
</script>

<template>
  <div class="flex h-full flex-col">
    <!-- 页头 -->
    <header class="fade-up flex flex-wrap items-end justify-between gap-4 px-7 pb-3 pt-6">
      <div>
        <h1 class="text-[21px] font-bold tracking-tight text-zinc-900">题库 · 错题本</h1>
        <p class="mt-1 text-[13px] text-zinc-400">
          共 {{ questions.length }} 题，其中错题 {{ wrongCount }} 道 · 点「答案详情」查看排版好的参考答案
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <div class="seg">
          <button :class="mode === 'all' && 'active'" @click="mode = 'all'">
            全部题库 · {{ questions.length }}
          </button>
          <button :class="mode === 'wrong' && 'active'" @click="mode = 'wrong'">
            错题本 · {{ wrongCount }}
          </button>
        </div>
        <n-input
          v-model:value="search"
          round
          clearable
          placeholder="搜索题干 / 维度 / 公司 / 简历"
          size="small"
          style="width: 210px"
        >
          <template #prefix>
            <n-icon :component="SearchOutline" :size="15" class="text-zinc-400" />
          </template>
        </n-input>
        <button class="btn-gradient" @click="openCreate">
          <n-icon :component="AddOutline" :size="16" />
          新增题目
        </button>
      </div>
    </header>

    <!-- 筛选 -->
    <div class="flex flex-wrap items-center gap-2 px-7 pb-3">
      <n-select
        v-model:value="fDimension"
        clearable
        filterable
        size="small"
        placeholder="维度"
        :options="dimensionOptions"
        style="width: 150px"
      />
      <n-select
        v-model:value="fMastery"
        clearable
        size="small"
        placeholder="掌握状态"
        :options="masteryOptions"
        style="width: 130px"
      />
      <n-select
        v-model:value="fDifficulty"
        clearable
        size="small"
        placeholder="难度"
        :options="difficultyOptions"
        style="width: 110px"
      />
      <n-button v-if="hasActiveFilter" quaternary size="small" @click="clearFilters">清空筛选</n-button>
      <span class="text-[12px] tabular-nums text-zinc-400">
        {{ filtered.length }} / {{ questions.length }}
      </span>
    </div>

    <!-- 题目列表 -->
    <div class="min-h-0 flex-1 overflow-y-auto px-7 pb-6">
      <div v-if="loading" class="grid h-full place-items-center text-sm text-zinc-400">
        正在加载题库…
      </div>
      <div v-else-if="filtered.length === 0" class="grid h-full place-items-center">
        <div class="text-center">
          <div class="text-[42px]">📚</div>
          <p class="mt-3 text-[13px] text-zinc-400">
            {{ mode === 'wrong' ? '错题本是空的，继续保持！' : '还没有题目，把面试被问到的题沉淀下来吧' }}
          </p>
          <n-button type="primary" secondary class="mt-3" @click="openCreate">新增题目</n-button>
        </div>
      </div>
      <div v-else class="fade-up-d1 grid grid-cols-1 gap-3 xl:grid-cols-2">
        <article
          v-for="q in filtered"
          :key="q.id"
          class="relative flex flex-col rounded-2xl border border-zinc-200/80 bg-white p-4 shadow-[0_1px_2px_rgba(16,24,40,0.04)] transition-shadow hover:shadow-[0_8px_20px_-8px_rgba(16,24,40,0.15)]"
          :class="expandedId === q.id && 'z-20 shadow-[0_24px_60px_-12px_rgba(16,24,40,0.3)]'"
        >
          <div class="flex flex-wrap items-center gap-1.5">
            <span class="rounded-md bg-indigo-50 px-1.5 py-0.5 text-[11px] font-medium text-indigo-600">
              {{ q.dimension }}
            </span>
            <span
              class="rounded-md px-1.5 py-0.5 text-[11px] font-medium"
              :class="DIFFICULTY_META[q.difficulty]?.class"
            >
              {{ DIFFICULTY_META[q.difficulty]?.label }}
            </span>
            <span
              class="rounded-md border px-1.5 py-0.5 text-[11px] font-medium"
              :class="MASTERY_META[q.mastery]?.class"
            >
              {{ MASTERY_META[q.mastery]?.label }}
            </span>
            <span class="ml-auto flex items-center gap-1.5">
              <span
                v-if="sourceSummary(q)"
                class="flex items-center gap-1 rounded-full border border-zinc-200 bg-zinc-50 py-0.5 pl-0.5 pr-2"
                :title="sourcesTitle(q)"
              >
                <span class="flex -space-x-1.5">
                  <span
                    v-for="(comp, ci) in sourceCompanies(q).slice(0, 3)"
                    :key="ci"
                    class="grid h-4 w-4 place-items-center rounded-full text-[8px] font-bold text-white ring-1 ring-white"
                    :style="{ background: avatarGradient(comp) }"
                  >
                    {{ comp.slice(0, 1) }}
                  </span>
                </span>
                <span class="max-w-[150px] truncate text-[10.5px] text-zinc-500">
                  {{ sourceSummary(q) }}
                </span>
              </span>
              <span class="text-[11px] text-zinc-400">{{ QUESTION_SOURCE_LABEL[q.source] }}</span>
            </span>
          </div>

          <p class="mt-2.5 whitespace-pre-wrap text-[13.5px] font-medium leading-relaxed text-zinc-800">
            {{ q.content }}
          </p>

          <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-zinc-400">
            <span v-if="q.self_rating">自评 {{ q.self_rating }} 分</span>
            <span
              v-if="q.resume_name"
              class="max-w-[160px] truncate rounded bg-zinc-100 px-1 py-0.5"
              :title="`关联简历：${q.resume_name}`"
            >
              📄 {{ q.resume_name }}
            </span>
            <label
              v-if="mode === 'wrong' && isWrong(q)"
              class="flex cursor-pointer items-center gap-1 hover:text-zinc-600"
            >
              <input
                type="checkbox"
                :checked="q.review_done"
                class="accent-indigo-500"
                @change="toggleReview(q)"
              />
              已复习
            </label>
          </div>

          <!-- 操作行 -->
          <div class="mt-auto flex items-center justify-between gap-2 border-t border-zinc-100 pt-2.5" :class="(q.my_answer || q.answer_key || q.answer_spoken) && 'mt-3'">
            <div class="flex items-center gap-1.5">
              <n-rate
                v-if="q.self_rating"
                :value="q.self_rating"
                readonly
                allow-half
                size="small"
                color="#f59e0b"
              />
              <n-button
                v-if="mode === 'wrong' && q.mastery !== 'mastered'"
                size="tiny"
                type="primary"
                secondary
                @click="markMastered(q)"
              >
                标记已掌握
              </n-button>
            </div>
            <div class="flex shrink-0 items-center gap-1">
              <n-button
                size="tiny"
                quaternary
                type="primary"
                :loading="aiBusyId === q.id"
                data-keep-panel
                @click="genAnswer(q)"
              >
                <template #icon>
                  <n-icon :component="SparklesOutline" :size="12" />
                </template>
                AI 答案
              </n-button>
              <n-button
                size="tiny"
                :secondary="expandedId === q.id"
                :type="expandedId === q.id ? 'primary' : 'default'"
                :data-detail-toggle="q.id"
                @click="toggleDetail(q)"
              >
                {{ expandedId === q.id ? '收起' : '答案详情' }}
                <template #icon>
                  <n-icon
                    :component="expandedId === q.id ? ChevronUpOutline : ChevronDownOutline"
                    :size="12"
                  />
                </template>
              </n-button>
              <n-button size="tiny" quaternary type="primary" @click="openEdit(q)">编辑</n-button>
              <n-button size="tiny" quaternary type="error" @click="confirmDelete(q)">删除</n-button>
            </div>
          </div>

          <!-- 答案浮框 -->
          <div
            v-if="expandedId === q.id"
            data-answer-panel
              class="absolute inset-x-0 top-full z-30 mt-2 max-h-[65vh] overflow-y-auto rounded-2xl border border-zinc-200 bg-white p-4 shadow-[0_24px_60px_-12px_rgba(16,24,40,0.35)]"
            >
              <div class="mb-3 flex items-center justify-between">
                <span class="text-[12.5px] font-bold text-zinc-800">题目详情 · 参考答案</span>
                <span class="text-[10.5px] text-zinc-300">再次点击「收起」收回</span>
              </div>

              <section class="mb-3">
                <div class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-400">
                  我的回答要点
                </div>
                <p
                  v-if="q.my_answer"
                  class="whitespace-pre-wrap rounded-lg bg-zinc-50 px-3 py-2 text-[12.5px] leading-relaxed text-zinc-600"
                >
                  {{ q.my_answer }}
                </p>
                <p v-else class="text-[12px] text-zinc-300">还没有记录当时是怎么答的</p>
              </section>

              <section class="mb-3">
                <div class="mb-1 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-indigo-400">
                  <n-icon :component="SparklesOutline" :size="12" />
                  AI 口述版答案（面试现场怎么说）
                </div>
                <!-- 内容已做 HTML 转义后再注入轻量排版 -->
                <div
                  v-if="q.answer_spoken"
                  class="rounded-lg border border-indigo-100 bg-indigo-50/50 px-3 py-2.5 text-[12.5px] leading-relaxed text-zinc-700"
                  v-html="renderMdLite(q.answer_spoken)"
                />
                <div
                  v-else
                  class="rounded-lg border border-dashed border-indigo-200 bg-indigo-50/30 px-3 py-4 text-center text-[12px] text-zinc-400"
                >
                  还没有生成 · 点下方「AI 答案」按面试现场表达自动生成
                </div>
              </section>

              <section>
                <div class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-emerald-500">
                  参考答案要点 / 得分点
                </div>
                <!-- eslint-disable-next-line vue/no-v-html 内容已做 HTML 转义 -->
                <div
                  v-if="q.answer_key"
                  class="rounded-lg bg-emerald-50/60 px-3 py-2.5 text-[12.5px] leading-relaxed text-zinc-700"
                  v-html="renderMdLite(q.answer_key)"
                />
                <p v-else class="text-[12px] text-zinc-300">暂无</p>
              </section>

              <div class="mt-3 border-t border-zinc-100 pt-2 text-[10.5px] text-zinc-300">
                创建于 {{ shortDate(q.created_at) }} · 更新于 {{ shortDate(q.updated_at) }}
              </div>
          </div>
        </article>
      </div>
    </div>

    <QuestionModal
      v-model:show="modalShow"
      :question="editing"
      :dimensions="dimensions"
      :opportunities="opportunities"
      @saved="onSaved"
    />
  </div>
</template>

<style scoped>
/* 答案浮框弹出动画：CSS animation 实现，展开时浮入 */
[data-answer-panel] {
  animation: panelPop 0.18s cubic-bezier(0.2, 0.8, 0.3, 1);
}
@keyframes panelPop {
  from {
    opacity: 0;
    transform: translateY(-6px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
</style>
