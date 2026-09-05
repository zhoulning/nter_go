<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useDialog, useMessage } from 'naive-ui'
import {
  AddOutline,
  ChatbubblesOutline,
  MicOutline,
  SearchOutline,
  SparklesOutline,
} from '@vicons/ionicons5'
import { api } from '../api'
import type { QuestionOrigins } from '../api'
import type { Opportunity, Question } from '../types'
import {
  DIFFICULTY_META,
  MASTERY_META,
  QUESTION_SOURCE_LABEL,
  MOCK_ROUND_LABEL,
  avatarGradient,
  renderMdLite,
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

/** 前端分页：题库为个人数据量级，一次拉全量后本地筛选 + 分页 */
const page = ref(1)
const pageSize = ref(10)

const modalShow = ref(false)
const editing = ref<Question | null>(null)
const aiBusyId = ref<number | null>(null)

/** 多选：批量删除 / 导出 Markdown（题库_年月日时分秒.md） */
const selectedIds = ref<Set<number>>(new Set())
const deletingBatch = ref(false)
const exporting = ref(false)
const selectedCount = computed(() => selectedIds.value.size)

function toggleSelect(q: Question, e: Event) {
  const checked = (e.target as HTMLInputElement).checked
  const next = new Set(selectedIds.value)
  if (checked) next.add(q.id)
  else next.delete(q.id)
  selectedIds.value = next
}

/** 详情悬浮窗：当前查看的题目 */
const detailShow = ref(false)
const detailQ = ref<Question | null>(null)
/** 原回答回溯：模拟面试 / 真实面试录音中的原问原答 */
const origins = ref<QuestionOrigins | null>(null)
const originsLoading = ref(false)

async function load() {
  loading.value = true
  try {
    const [q, meta, opps] = await Promise.all([
      api.listQuestions(),
      api.questionMeta(),
      api.listOpportunities(),
    ])
    questions.value = q.items
    // 清理已不存在题目上的选中态
    const alive = new Set(q.items.map((x) => x.id))
    const next = new Set([...selectedIds.value].filter((id) => alive.has(id)))
    if (next.size !== selectedIds.value.size) selectedIds.value = next
    dimensions.value = meta.dimensions
    opportunities.value = opps.items
    // 详情悬浮窗开着时同步最新数据（编辑 / 掌握状态变更后）；题目被删则关闭
    if (detailQ.value) {
      detailQ.value = questions.value.find((x) => x.id === detailQ.value!.id) ?? null
      if (!detailQ.value) detailShow.value = false
    }
  } catch (e) {
    message.error((e as Error).message || '加载失败')
  } finally {
    loading.value = false
  }
}
onMounted(() => load())

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

/** 当前页的题目 */
const paged = computed(() =>
  filtered.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value),
)

// 筛选 / 搜索 / 模式变化时回到第一页；列表变短或每页条数变化时收回页码，避免停留在空页
watch([search, fDimension, fMastery, fDifficulty, mode], () => {
  page.value = 1
})
watch([filtered, pageSize], () => {
  const totalPages = Math.max(1, Math.ceil(filtered.value.length / pageSize.value))
  if (page.value > totalPages) page.value = totalPages
})

const hasActiveFilter = computed(
  () => !!search.value.trim() || !!fDimension.value || !!fMastery.value || !!fDifficulty.value,
)

/** 表头全选框只管当前筛选出的列表：全选中→勾选，部分选中→半选 */
const allFilteredSelected = computed(
  () => filtered.value.length > 0 && filtered.value.every((q) => selectedIds.value.has(q.id)),
)
const someFilteredSelected = computed(() => filtered.value.some((q) => selectedIds.value.has(q.id)))

function toggleSelectAll(e: Event) {
  const checked = (e.target as HTMLInputElement).checked
  const next = new Set(selectedIds.value)
  for (const q of filtered.value) {
    if (checked) next.add(q.id)
    else next.delete(q.id)
  }
  selectedIds.value = next
}

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
    (s) => `${s.company ?? '未知公司'}${s.round_type ? ` · ${MOCK_ROUND_LABEL[s.round_type] ?? '面试'}` : ''}`,
  )
  return parts.length === 1 ? parts[0] : `${parts[0]} 等 ${parts.length} 处`
}

function sourceCompanies(q: Question): string[] {
  return [...new Set((q.sources ?? []).map((s) => s.company ?? ''))] as string[]
}

function sourcesTitle(q: Question): string {
  return (q.sources ?? [])
    .map((s) => `${s.company ?? ''}${s.round_type ? ` · ${MOCK_ROUND_LABEL[s.round_type] ?? ''}` : ''}`)
    .join('，')
}

function openCreate() {
  editing.value = null
  modalShow.value = true
}

function openDetail(q: Question) {
  detailQ.value = q
  detailShow.value = true
  loadOrigins(q.id)
}

async function loadOrigins(id: number) {
  origins.value = null
  originsLoading.value = true
  try {
    origins.value = await api.questionOrigins(id)
  } catch {
    // 回溯失败不打断详情查看，只是不展示这两个区块
  } finally {
    originsLoading.value = false
  }
}

function openEdit(q: Question) {
  editing.value = q
  modalShow.value = true
}

function onSaved(saved: Question, _isNew: boolean) {
  // 成功提示由 QuestionModal 根据保存/生成结果给出，这里只负责同步详情窗并刷新列表
  if (detailQ.value?.id === saved.id) detailQ.value = saved
  load()
}

function patchLocalAnswer(id: number, answer: string) {
  const local = questions.value.find((x) => x.id === id)
  if (local) local.answer_spoken = answer
  if (detailQ.value?.id === id) detailQ.value.answer_spoken = answer
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
      // 不把 Promise 返回给 dialog：否则弹窗会原地干等且无 loading，看起来像卡死
      onPositiveClick: () => {
        doGenerate(q)
      },
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
      patchLocalAnswer(q.id, res.answer_spoken)
      message.success('口述版答案已生成')
    } else {
      message.warning('AI 没有返回有效答案，请重试')
    }
  } catch (e) {
    message.error((e as Error).message || 'AI 生成失败', { duration: 6000 })
  } finally {
    aiBusyId.value = null
  }
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
        if (detailQ.value?.id === q.id) detailShow.value = false
        await load()
      } catch (e) {
        message.error((e as Error).message || '删除失败')
      }
    },
  })
}

function confirmDeleteSelected() {
  const count = selectedCount.value
  dialog.warning({
    title: '批量删除题目',
    content: `确定从题库中删除选中的 ${count} 道题吗？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      deletingBatch.value = true
      let ok = 0
      let failed = 0
      for (const id of [...selectedIds.value]) {
        try {
          await api.deleteQuestion(id)
          ok++
        } catch {
          failed++
        }
      }
      deletingBatch.value = false
      await load()
      if (failed) message.error(`已删除 ${ok} 题，${failed} 题删除失败`)
      else message.success(`已删除 ${ok} 道题`)
    },
  })
}

/** 导出选中题目为 Markdown：题库_年月日时分秒.md */
async function exportSelected() {
  if (selectedCount.value === 0) return
  exporting.value = true
  try {
    const qs = questions.value.filter((q) => selectedIds.value.has(q.id))
    const now = new Date()
    const p = (n: number) => String(n).padStart(2, '0')
    const stamp = `${now.getFullYear()}${p(now.getMonth() + 1)}${p(now.getDate())}${p(now.getHours())}${p(now.getMinutes())}${p(now.getSeconds())}`
    const timeText = `${now.getFullYear()}/${p(now.getMonth() + 1)}/${p(now.getDate())} ${p(now.getHours())}:${p(now.getMinutes())}:${p(now.getSeconds())}`

    const lines: string[] = ['# 题库', '', `> 导出时间：${timeText} · 共 ${qs.length} 题`, '']
    qs.forEach((q, i) => {
      // 分隔线前必须留空行，否则上一行正文会被 Markdown setext 语法解析成标题
      lines.push('', '---', '', `### ${i + 1}. ${q.content}`, '')
      lines.push(`- 维度：${q.dimension}`)
      lines.push(`- 难度：${DIFFICULTY_META[q.difficulty]?.label ?? q.difficulty}`)
      lines.push(`- 掌握：${MASTERY_META[q.mastery]?.label ?? q.mastery}`)
      if (q.self_rating != null) lines.push(`- 自评：${q.self_rating} 分`)
      const srcs = (q.sources ?? []).map(
        (s) =>
          `${s.company ?? '未知公司'}${s.round_type ? ` · ${MOCK_ROUND_LABEL[s.round_type] ?? s.round_type}` : ''}`,
      )
      if (srcs.length) lines.push(`- 来源：${srcs.join('、')}`)
      if (q.opportunity) lines.push(`- 关联岗位：${q.opportunity.company}（${q.opportunity.position}）`)
      if (q.resume_name) lines.push(`- 关联简历：${q.resume_name}`)
      if (q.my_answer) lines.push('', '**我的回答**', '', q.my_answer)
      if (q.answer_spoken) lines.push('', '**AI 口述版答案**', '', q.answer_spoken)
      if (q.answer_key) lines.push('', '**参考答案要点**', '', q.answer_key)
    })

    const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `题库_${stamp}.md`
    a.click()
    URL.revokeObjectURL(url)
    message.success(`已导出 ${qs.length} 道题（题库_${stamp}.md）`)
  } catch (e) {
    message.error((e as Error).message || '导出失败')
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <div class="flex h-full flex-col">
    <!-- 页头 -->
    <header class="fade-up flex flex-wrap items-end justify-between gap-4 px-7 pb-3 pt-6 max-md:gap-2.5 max-md:px-4 max-md:pt-4">
      <div>
        <h1 class="text-[21px] font-bold tracking-tight text-zinc-900">题库管理</h1>
        <p class="mt-1 text-[13px] text-zinc-400">
          共 {{ questions.length }} 题，其中错题 {{ wrongCount }} 道 · 点「答案详情」在悬浮窗中查看与操作
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
          class="!w-[210px] max-md:!w-full max-md:!flex-1"
        >
          <template #prefix>
            <n-icon :component="SearchOutline" :size="15" class="text-zinc-400" />
          </template>
        </n-input>
        <button class="btn-gradient shrink-0 whitespace-nowrap" @click="openCreate">
          <n-icon :component="AddOutline" :size="16" />
          新增题目
        </button>
      </div>
    </header>

    <!-- 筛选 -->
    <div class="flex flex-wrap items-center gap-2 px-7 pb-3 max-md:px-4">
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
      <!-- 多选后的批量操作 -->
      <template v-if="selectedCount > 0">
        <span class="text-[12px] tabular-nums text-indigo-500">已选 {{ selectedCount }} 题</span>
        <n-button size="small" secondary type="primary" :loading="exporting" @click="exportSelected">
          导出题库
        </n-button>
        <n-button size="small" secondary type="error" :loading="deletingBatch" @click="confirmDeleteSelected">
          删除所选
        </n-button>
      </template>
    </div>

    <!-- 题目列表：表头 + 表格 -->
    <div class="min-h-0 flex-1 overflow-y-auto px-7 pb-6 max-md:px-4">
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
      <div v-else class="fade-up-d1 overflow-x-auto rounded-xl border border-zinc-200/80 bg-white">
        <table class="w-full min-w-[880px] border-collapse">
          <thead>
            <tr
              class="border-b border-zinc-200/80 bg-zinc-50/80 text-left text-[11px] font-semibold uppercase tracking-wide text-zinc-400"
            >
              <th class="w-10 px-3 py-2.5">
                <input
                  type="checkbox"
                  class="h-4 w-4 cursor-pointer accent-indigo-500"
                  :checked="allFilteredSelected"
                  :indeterminate.prop="someFilteredSelected && !allFilteredSelected"
                  :disabled="filtered.length === 0"
                  aria-label="全选当前列表"
                  @change="toggleSelectAll"
                />
              </th>
              <th class="px-4 py-2.5 font-semibold">题目</th>
              <th class="px-3 py-2.5 font-semibold">维度</th>
              <th class="px-3 py-2.5 font-semibold">难度</th>
              <th class="px-3 py-2.5 font-semibold">掌握</th>
              <th class="px-3 py-2.5 font-semibold">来源</th>
              <th class="px-3 py-2.5 font-semibold">自评</th>
              <th class="px-4 py-2.5 text-right font-semibold">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="q in paged"
              :key="q.id"
              class="cursor-pointer border-b border-zinc-100 transition-colors last:border-b-0 hover:bg-indigo-50/40"
              :class="selectedIds.has(q.id) && 'bg-indigo-50/60'"
              @click="openDetail(q)"
            >
              <td class="w-10 px-3 py-3 align-middle" @click.stop>
                <input
                  type="checkbox"
                  class="h-4 w-4 cursor-pointer accent-indigo-500"
                  :checked="selectedIds.has(q.id)"
                  :aria-label="`选择题目：${q.content.slice(0, 20)}`"
                  @change="toggleSelect(q, $event)"
                />
              </td>
              <td class="max-w-[420px] px-4 py-3">
                <p class="line-clamp-2 text-[13px] font-medium leading-relaxed text-zinc-800" :title="q.content">
                  {{ q.content }}
                </p>
                <div v-if="q.resume_name" class="mt-1 flex items-center text-[11px] text-zinc-400">
                  <span
                    class="max-w-[180px] truncate rounded bg-zinc-100 px-1 py-0.5"
                    :title="`关联简历：${q.resume_name}`"
                  >
                    📄 {{ q.resume_name }}
                  </span>
                </div>
              </td>
              <td class="px-3 py-3">
                <span class="rounded-md bg-indigo-50 px-1.5 py-0.5 text-[11px] font-medium text-indigo-600">
                  {{ q.dimension }}
                </span>
              </td>
              <td class="px-3 py-3">
                <span
                  class="rounded-md px-1.5 py-0.5 text-[11px] font-medium"
                  :class="DIFFICULTY_META[q.difficulty]?.class"
                >
                  {{ DIFFICULTY_META[q.difficulty]?.label }}
                </span>
              </td>
              <td class="px-3 py-3">
                <span
                  class="rounded-md border px-1.5 py-0.5 text-[11px] font-medium"
                  :class="MASTERY_META[q.mastery]?.class"
                >
                  {{ MASTERY_META[q.mastery]?.label }}
                </span>
              </td>
              <td class="max-w-[170px] px-3 py-3">
                <div
                  v-if="sourceSummary(q)"
                  class="flex items-center gap-1"
                  :title="sourcesTitle(q)"
                >
                  <span class="flex shrink-0 -space-x-1.5">
                    <span
                      v-for="(comp, ci) in sourceCompanies(q).slice(0, 3)"
                      :key="ci"
                      class="grid h-4 w-4 place-items-center rounded-full text-[8px] font-bold text-white ring-1 ring-white"
                      :style="{ background: avatarGradient(comp) }"
                    >
                      {{ comp.slice(0, 1) }}
                    </span>
                  </span>
                  <span class="truncate text-[11.5px] text-zinc-500">{{ sourceSummary(q) }}</span>
                </div>
                <span v-else class="text-[11.5px] text-zinc-300">—</span>
              </td>
              <td class="px-3 py-3 text-[12px] tabular-nums text-zinc-500">
                {{ q.self_rating != null ? `${q.self_rating} 分` : '—' }}
              </td>
              <td class="whitespace-nowrap px-4 py-3 text-right" @click.stop>
                <label
                  v-if="mode === 'wrong' && isWrong(q)"
                  class="mr-2 inline-flex cursor-pointer items-center gap-1 text-[11px] text-zinc-400 hover:text-zinc-600"
                >
                  <input
                    type="checkbox"
                    :checked="q.review_done"
                    class="accent-indigo-500"
                    @change="toggleReview(q)"
                  />
                  已复习
                </label>
                <n-button size="tiny" :secondary="!q.answer_spoken" type="primary" @click.stop="openDetail(q)">
                  答案详情
                </n-button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 分页：右侧页码 + 每页条数 -->
    <div
      v-if="filtered.length > 0"
      class="flex shrink-0 justify-end px-7 pb-4 max-md:justify-center max-md:px-4"
    >
      <n-pagination
        v-model:page="page"
        v-model:page-size="pageSize"
        :item-count="filtered.length"
        :page-sizes="[10, 20, 50, 100]"
        show-size-picker
        size="small"
      />
    </div>

    <!-- 详情悬浮窗：查看 + 操作集中在这里 -->
    <n-modal :show="detailShow" transform-origin="center" @update:show="detailShow = $event">
      <div v-if="detailQ" class="detail-card">
        <div class="detail-scroll">
        <div class="mb-3">
          <h2 class="text-[16px] font-bold text-zinc-900">题目详情</h2>
          <p class="mt-0.5 text-[12px] text-zinc-400">
            {{ QUESTION_SOURCE_LABEL[detailQ.source] }}
            <template v-if="sourceSummary(detailQ)"> · 来自 {{ sourceSummary(detailQ) }}</template>
            · 创建于 {{ shortDate(detailQ.created_at) }} · 更新于 {{ shortDate(detailQ.updated_at) }}
          </p>
        </div>

        <p class="whitespace-pre-wrap rounded-xl bg-zinc-50 px-3.5 py-3 text-[14px] font-medium leading-relaxed text-zinc-800">
          {{ detailQ.content }}
        </p>

        <div class="mt-2.5 flex flex-wrap items-center gap-1.5">
          <span class="rounded-md bg-indigo-50 px-1.5 py-0.5 text-[11px] font-medium text-indigo-600">
            {{ detailQ.dimension }}
          </span>
          <span
            class="rounded-md px-1.5 py-0.5 text-[11px] font-medium"
            :class="DIFFICULTY_META[detailQ.difficulty]?.class"
          >
            {{ DIFFICULTY_META[detailQ.difficulty]?.label }}
          </span>
          <span
            class="rounded-md border px-1.5 py-0.5 text-[11px] font-medium"
            :class="MASTERY_META[detailQ.mastery]?.class"
          >
            {{ MASTERY_META[detailQ.mastery]?.label }}
          </span>
          <span v-if="detailQ.self_rating" class="text-[11.5px] text-zinc-400">
            自评 {{ detailQ.self_rating }} 分
          </span>
          <span
            v-if="detailQ.resume_name"
            class="max-w-[200px] truncate rounded bg-zinc-100 px-1 py-0.5 text-[11px] text-zinc-500"
            :title="`关联简历：${detailQ.resume_name}`"
          >
            📄 {{ detailQ.resume_name }}
          </span>
        </div>

        <section class="mt-4">
          <div class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-400">
            我的回答要点
          </div>
          <p
            v-if="detailQ.my_answer"
            class="whitespace-pre-wrap rounded-lg bg-zinc-50 px-3 py-2 text-[12.5px] leading-relaxed text-zinc-600"
          >
            {{ detailQ.my_answer }}
          </p>
          <p v-else class="text-[12px] text-zinc-300">还没有记录当时是怎么答的</p>
        </section>

        <!-- 原回答回溯：模拟面试 / 真实面试录音 -->
        <section v-if="originsLoading" class="mt-3">
          <div class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-400">
            原回答回溯
          </div>
          <div class="rounded-lg bg-zinc-50 px-3 py-3 text-center text-[12px] text-zinc-400">
            正在匹配模拟面试与面试录音…
          </div>
        </section>
        <template v-else-if="origins && (origins.mock_answers.length || origins.recording_answers.length)">
          <section v-if="origins.mock_answers.length" class="mt-3">
            <div class="mb-1.5 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-violet-500">
              <n-icon :component="ChatbubblesOutline" :size="12" />
              模拟面试原回答 · 按时间{{ origins.mock_answers.length > 1 ? '，可对比是否进步' : '' }}
            </div>
            <div class="space-y-2">
              <div
                v-for="(m, mi) in origins.mock_answers"
                :key="m.mock_interview_id"
                class="rounded-lg border border-violet-100 bg-violet-50/40 px-3 py-2.5"
              >
                <div class="mb-1 flex flex-wrap items-center gap-2 text-[11px] text-zinc-400">
                  <span class="rounded bg-violet-100 px-1.5 py-0.5 font-medium text-violet-600">
                    第 {{ mi + 1 }} 次 · {{ MOCK_ROUND_LABEL[m.round_type] ?? '模拟面试' }}
                  </span>
                  <span v-if="m.company">{{ m.company }}</span>
                  <span>{{ shortDate(m.created_at) }}</span>
                  <span v-if="m.overall_score" class="ml-auto font-semibold text-zinc-500">
                    本场总分 {{ m.overall_score }}
                  </span>
                </div>
                <p v-if="m.my_answer" class="whitespace-pre-wrap text-[12.5px] leading-relaxed text-zinc-700">
                  {{ m.my_answer }}
                </p>
                <p v-else class="text-[12px] text-zinc-300">这场没有留下回答（可能跳过或未答完）</p>
                <p
                  v-if="origins.mock_answers.length > 1"
                  class="mt-1.5 border-t border-violet-100/80 pt-1.5 text-[11px] leading-relaxed text-zinc-400"
                >
                  面试官原话：{{ m.question }}
                </p>
              </div>
            </div>
          </section>

          <section v-if="origins.recording_answers.length" class="mt-3">
            <div class="mb-1.5 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-sky-600">
              <n-icon :component="MicOutline" :size="12" />
              真实面试录音 · 原话与上下文
            </div>
            <div class="space-y-2">
              <div
                v-for="r in origins.recording_answers"
                :key="r.recording_id"
                class="rounded-lg border border-sky-100 bg-sky-50/40 px-3 py-2.5"
              >
                <div class="mb-1.5 flex flex-wrap items-center gap-2 text-[11px] text-zinc-400">
                  <span class="rounded bg-sky-100 px-1.5 py-0.5 font-medium text-sky-700">
                    {{ r.company ?? '面试录音' }}
                  </span>
                  <span v-if="r.round_type">{{ MOCK_ROUND_LABEL[r.round_type] ?? r.round_type }}</span>
                  <span>{{ shortDate(r.created_at) }}</span>
                  <span v-if="r.timestamp" class="text-zinc-300">定位 [{{ r.timestamp }}]</span>
                </div>
                <p
                  v-if="r.context_before"
                  class="mb-1.5 border-l-2 border-sky-200 pl-2 text-[11.5px] leading-relaxed text-zinc-400"
                >
                  前文 · {{ r.context_before }}
                </p>
                <p class="text-[12.5px] font-medium leading-relaxed text-zinc-700">面试官：{{ r.question_text }}</p>
                <p v-if="r.my_answer" class="mt-1.5 whitespace-pre-wrap text-[12.5px] leading-relaxed text-zinc-600">
                  我的回答：{{ r.my_answer }}
                </p>
                <p
                  v-if="r.excerpt"
                  class="mt-1.5 whitespace-pre-wrap rounded bg-white/70 px-2 py-1.5 text-[11.5px] leading-relaxed text-zinc-500"
                >
                  {{ r.excerpt }}
                </p>
              </div>
            </div>
          </section>
        </template>

        <section class="mt-3">
          <div class="mb-1 flex items-center justify-between gap-2">
            <div class="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-indigo-400">
              <n-icon :component="SparklesOutline" :size="12" />
              AI 口述版答案（面试现场怎么说）
            </div>
            <n-button
              size="tiny"
              quaternary
              type="primary"
              :loading="aiBusyId === detailQ.id"
              @click="genAnswer(detailQ)"
            >
              <template #icon>
                <n-icon :component="SparklesOutline" :size="12" />
              </template>
              重新生成 AI 答案
            </n-button>
          </div>
          <!-- 内容已做 HTML 转义后再注入轻量排版 -->
          <div
            v-if="detailQ.answer_spoken"
            class="rounded-lg border border-indigo-100 bg-indigo-50/50 px-3 py-2.5 text-[12.5px] leading-relaxed text-zinc-700"
            v-html="renderMdLite(detailQ.answer_spoken)"
          />
          <div
            v-else
            class="rounded-lg border border-dashed border-indigo-200 bg-indigo-50/30 px-3 py-4 text-center text-[12px] text-zinc-400"
          >
            还没有生成 · 点右上「重新生成 AI 答案」按面试现场表达自动生成
          </div>
        </section>

        <section class="mt-3">
          <div class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-emerald-500">
            参考答案要点 / 得分点
          </div>
          <!-- eslint-disable-next-line vue/no-v-html 内容已做 HTML 转义 -->
          <div
            v-if="detailQ.answer_key"
            class="rounded-lg bg-emerald-50/60 px-3 py-2.5 text-[12.5px] leading-relaxed text-zinc-700"
            v-html="renderMdLite(detailQ.answer_key)"
          />
          <p v-else class="text-[12px] text-zinc-300">暂无</p>
        </section>

        <div class="mt-4 flex items-center justify-between gap-2 border-t border-zinc-100 pt-3">
          <div>
            <n-button
              v-if="detailQ.mastery !== 'mastered'"
              size="small"
              secondary
              type="primary"
              @click="markMastered(detailQ)"
            >
              标记已掌握
            </n-button>
          </div>
          <div class="flex items-center gap-2">
            <n-button size="small" quaternary @click="detailShow = false">关闭</n-button>
            <n-button size="small" quaternary type="error" @click="confirmDelete(detailQ)">删除</n-button>
            <n-button size="small" secondary type="primary" @click="openEdit(detailQ)">编辑</n-button>
          </div>
        </div>
        </div>
        <!-- AI 生成中遮罩：与模拟面试的分析等待一致，整卡转圈 -->
        <div v-if="aiBusyId === detailQ.id" class="absolute inset-0 z-10 grid place-items-center bg-white/85">
          <div class="flex flex-col items-center gap-3">
            <n-spin :size="32" />
            <p class="text-[13px] text-zinc-500">正在生成 AI 口述版答案，请稍候…</p>
          </div>
        </div>
      </div>
    </n-modal>

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
/* 详情悬浮窗：居中弹出、内部可滚动；滚动放在内层，让生成中的遮罩能盖住整卡 */
.detail-card {
  position: relative;
  display: flex;
  flex-direction: column;
  width: 720px;
  max-width: calc(100vw - 48px);
  max-height: calc(100vh - 48px);
  overflow: hidden;
  background: #fff;
  border-radius: 16px;
  box-shadow:
    0 20px 50px -12px rgba(16, 24, 40, 0.25),
    0 0 0 1px rgba(16, 24, 40, 0.04);
}
.detail-scroll {
  min-height: 0;
  overflow-y: auto;
  padding: 24px;
}
</style>
