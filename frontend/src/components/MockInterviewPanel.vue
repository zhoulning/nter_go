<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useDialog, useMessage } from 'naive-ui'
import { AddOutline, ChatbubbleEllipsesOutline, SparklesOutline } from '@vicons/ionicons5'
import { api } from '../api'
import type { MockInterviewInfo, Opportunity } from '../types'
import { DIFFICULTY_META, ROUND_LABEL } from '../types'

const props = defineProps<{ opportunity: Opportunity }>()

const message = useMessage()
const dialog = useDialog()

const sessions = ref<MockInterviewInfo[]>([])
const selectedId = ref<number | null>(null)
const loading = ref(true)
const starting = ref(false)
const sending = ref(false)
const finishing = ref(false)
const newRound = ref('first')
const draft = ref('')
const savedBank = ref<Set<number>>(new Set())
// 已结束会话的右栏视图：对话 / 分析
const viewMode = ref<'chat' | 'analysis'>('analysis')

async function load(keepSelection = true) {
  try {
    const data = await api.listMockInterviews(props.opportunity.id)
    sessions.value = data.items
    if (keepSelection && selectedId.value && data.items.some((s) => s.id === selectedId.value)) return
    selectedId.value = data.items[0]?.id ?? null
  } catch (e) {
    message.error((e as Error).message || '加载失败')
  } finally {
    loading.value = false
  }
}
onMounted(() => load(false))

const selected = computed(() => sessions.value.find((s) => s.id === selectedId.value) ?? null)

watch(selectedId, () => {
  viewMode.value = selected.value?.status === 'finished' ? 'analysis' : 'chat'
  savedBank.value.clear()
  scrollToBottom()
})

const chatEl = ref<HTMLDivElement | null>(null)
function scrollToBottom() {
  nextTick(() => {
    if (chatEl.value) chatEl.value.scrollTop = chatEl.value.scrollHeight
  })
}
watch(
  () => selected.value?.transcript.length,
  () => scrollToBottom(),
)

async function start() {
  starting.value = true
  try {
    const created = await api.createMockInterview(props.opportunity.id, newRound.value)
    sessions.value.unshift(created)
    selectedId.value = created.id
    viewMode.value = 'chat'
    message.success('模拟面试已开始，面试官已就位')
    scrollToBottom()
  } catch (e) {
    message.error((e as Error).message || '开始失败', { duration: 8000 })
  } finally {
    starting.value = false
  }
}

async function send(kind: 'answer' | 'skip' = 'answer') {
  const content = draft.value.trim()
  if (kind === 'answer' && (!content || !selected.value || sending.value)) return
  if (!selected.value || sending.value) return
  const id = selected.value.id
  sending.value = true
  try {
    const updated = await api.replyMockInterview(id, content, kind)
    replaceSession(updated)
    draft.value = ''
    scrollToBottom()
  } catch (e) {
    message.error((e as Error).message || '发送失败', { duration: 8000 })
  } finally {
    sending.value = false
  }
}

function finishConfirm() {
  if (!selected.value) return
  dialog.warning({
    title: '结束面试并生成分析',
    content: '将结束本轮模拟面试，并对整场对话生成逐题分析报告。确定结束？',
    positiveText: '结束并分析',
    negativeText: '继续面',
    onPositiveClick: finish,
  })
}

async function finish() {
  if (!selected.value || finishing.value) return
  finishing.value = true
  try {
    const updated = await api.finishMockInterview(selected.value.id)
    replaceSession(updated)
    viewMode.value = 'analysis'
    message.success('分析报告已生成')
  } catch (e) {
    message.error((e as Error).message || '分析生成失败', { duration: 8000 })
  } finally {
    finishing.value = false
  }
}

function replaceSession(updated: MockInterviewInfo) {
  const idx = sessions.value.findIndex((s) => s.id === updated.id)
  if (idx >= 0) sessions.value[idx] = updated
}

function reanalyzeConfirm() {
  if (!selected.value) return
  dialog.warning({
    title: '重新分析',
    content: '将去掉未作答的题目，并按当前最新的评价标准（含语音转写容错与薪资职级校准）重新打分，覆盖现有分析。确定继续？',
    positiveText: '重新分析',
    negativeText: '取消',
    onPositiveClick: reanalyze,
  })
}

async function reanalyze() {
  if (!selected.value || finishing.value) return
  finishing.value = true
  try {
    const updated = await api.reanalyzeMockInterview(selected.value.id)
    replaceSession(updated)
    viewMode.value = 'analysis'
    message.success(`已重新打分：${updated.overall_score} 分`)
  } catch (e) {
    message.error((e as Error).message || '重新分析失败', { duration: 8000 })
  } finally {
    finishing.value = false
  }
}

function removeSession(s: MockInterviewInfo) {
  dialog.warning({
    title: '删除记录',
    content: `确定删除这场「${ROUND_LABEL[s.round_type] ?? '面试'}」模拟面试（含对话与分析）吗？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.deleteMockInterview(s.id)
        sessions.value = sessions.value.filter((x) => x.id !== s.id)
        if (selectedId.value === s.id) selectedId.value = sessions.value[0]?.id ?? null
        message.success('已删除')
      } catch (e) {
        message.error((e as Error).message || '删除失败')
      }
    },
  })
}

async function saveToBank(idx: number) {
  const q = selected.value?.analysis?.questions_for_bank[idx]
  if (!q || !selected.value) return
  savedBank.value.add(idx)
  try {
    await api.createQuestion({
      content: q.content,
      dimension: q.dimension || '其他',
      difficulty: q.difficulty,
      source: 'predicted',
      opportunity_id: selected.value.opportunity_id,
      resume_id: null,
      sources: null,
      my_answer: null,
      answer_key: null,
      answer_spoken: null,
      self_rating: null,
      mastery: 'unknown',
    })
    message.success('已存入题库')
  } catch (e) {
    savedBank.value.delete(idx)
    message.error((e as Error).message || '入题库失败')
  }
}

function fmtTime(dt: string): string {
  const d = new Date(dt)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
</script>

<template>
  <div class="flex h-[calc(100vh-190px)] gap-4">
    <!-- 左栏：会话列表 + 新建 -->
    <div class="flex w-[230px] shrink-0 flex-col gap-2">
      <div class="rounded-2xl border border-zinc-100 bg-white p-3">
        <div class="mb-2 text-[12.5px] font-semibold text-zinc-700">新建模拟面试</div>
        <div class="flex gap-2">
          <select
            v-model="newRound"
            class="min-w-0 flex-1 rounded-lg border border-zinc-200 bg-white px-2 py-1.5 text-[12.5px] text-zinc-700 outline-none"
          >
            <option value="first">一面</option>
            <option value="second">二面</option>
            <option value="third">三面</option>
            <option value="cross">交叉面</option>
            <option value="hr">HR 面</option>
            <option value="written">笔试</option>
          </select>
          <n-button size="small" type="primary" :loading="starting" @click="start">
            <template #icon><n-icon :component="AddOutline" :size="13" /></template>
            开始
          </n-button>
        </div>
        <p class="mt-2 text-[11px] leading-relaxed text-zinc-400">
          面试官从题库随机选题、大类穿插，项目题开放式追问；可随时结束生成分析。已生成「题目预测」的轮次会以该题单为候选题库
        </p>
      </div>

      <div class="min-h-0 flex-1 overflow-y-auto">
        <button
          v-for="s in sessions"
          :key="s.id"
          class="group mb-1.5 w-full rounded-xl border px-3 py-2.5 text-left transition-colors"
          :class="
            selectedId === s.id
              ? 'border-indigo-200 bg-indigo-50/80'
              : 'border-zinc-100 bg-white hover:border-zinc-200'
          "
          @click="selectedId = s.id"
        >
          <div class="flex items-center gap-2">
            <span
              class="h-1.5 w-1.5 shrink-0 rounded-full"
              :class="s.status === 'ongoing' ? 'bg-emerald-400' : 'bg-zinc-300'"
              :title="s.status === 'ongoing' ? '进行中' : '已结束'"
            />
            <span class="min-w-0 flex-1 truncate text-[12.5px] font-medium text-zinc-700">
              {{ ROUND_LABEL[s.round_type] ?? '面试' }}模拟
            </span>
            <span
              v-if="s.status === 'finished'"
              class="shrink-0 rounded-md bg-zinc-100 px-1.5 py-0.5 text-[10.5px] font-semibold"
              :class="s.overall_score >= 75 ? 'text-emerald-600' : s.overall_score >= 60 ? 'text-amber-600' : 'text-rose-600'"
            >{{ s.overall_score }}分</span>
            <span
              class="hidden shrink-0 text-[11px] text-zinc-400 group-hover:inline"
              @click.stop="removeSession(s)"
            >删除</span>
          </div>
          <div class="mt-0.5 text-[11px] text-zinc-400">{{ fmtTime(s.created_at) }}</div>
        </button>
        <div v-if="!sessions.length && !loading" class="rounded-xl border border-dashed border-zinc-200 px-3 py-5 text-center text-[12px] text-zinc-400">
          还没有模拟面试记录
        </div>
      </div>
    </div>

    <!-- 右栏：对话 / 分析 -->
    <div class="flex min-w-0 flex-1 flex-col rounded-2xl border border-zinc-100 bg-white">
      <template v-if="selected">
        <!-- 头部 -->
        <div class="flex shrink-0 items-center gap-2.5 border-b border-zinc-100 px-4 py-2.5">
          <n-icon :component="ChatbubbleEllipsesOutline" :size="16" class="text-indigo-400" />
          <span class="text-[13.5px] font-semibold text-zinc-800">
            {{ ROUND_LABEL[selected.round_type] ?? '面试' }}模拟
          </span>
          <span
            class="rounded-md px-1.5 py-0.5 text-[10.5px] font-medium"
            :class="selected.status === 'ongoing' ? 'bg-emerald-50 text-emerald-600' : 'bg-zinc-100 text-zinc-500'"
          >{{ selected.status === 'ongoing' ? '进行中' : '已结束' }}</span>
          <span class="text-[11px] text-zinc-400">{{ selected.model }}</span>
          <div v-if="selected.status === 'finished'" class="ml-auto flex items-center gap-1">
            <button
              class="rounded-lg px-2.5 py-1 text-[12px] font-medium"
              :class="viewMode === 'analysis' ? 'bg-indigo-50 text-indigo-600' : 'text-zinc-500 hover:bg-zinc-50'"
              @click="viewMode = 'analysis'"
            >分析报告</button>
            <button
              class="rounded-lg px-2.5 py-1 text-[12px] font-medium"
              :class="viewMode === 'chat' ? 'bg-indigo-50 text-indigo-600' : 'text-zinc-500 hover:bg-zinc-50'"
              @click="viewMode = 'chat'"
            >对话记录</button>
            <n-button size="tiny" type="primary" secondary class="ml-1" :loading="finishing" @click="reanalyzeConfirm">
              重新分析
            </n-button>
          </div>
        </div>

        <!-- 对话区 -->
        <div
          v-show="selected.status === 'ongoing' || viewMode === 'chat'"
          ref="chatEl"
          class="min-h-0 flex-1 overflow-y-auto bg-zinc-50/50 px-4 py-4"
        >
          <div class="flex flex-col gap-3">
            <div
              v-for="(turn, i) in selected.transcript"
              :key="i"
              class="flex"
              :class="turn.role === 'candidate' ? 'justify-end' : 'justify-start'"
            >
              <div class="max-w-[85%]">
                <div v-if="turn.role === 'interviewer'" class="mb-0.5 flex items-center gap-1.5">
                  <span class="text-[11px] font-medium text-zinc-400">面试官</span>
                  <span v-if="turn.dimension" class="rounded bg-zinc-200/60 px-1.5 text-[10.5px] text-zinc-500">{{ turn.dimension }}</span>
                  <span v-if="turn.action === 'followup'" class="rounded bg-amber-100/70 px-1.5 text-[10.5px] text-amber-600">追问</span>
                </div>
                <div
                  class="whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed"
                  :class="
                    turn.role === 'candidate'
                      ? 'rounded-br-md bg-indigo-500 text-white'
                      : 'rounded-bl-md border border-zinc-100 bg-white text-zinc-700'
                  "
                >{{ turn.content }}</div>
              </div>
            </div>
            <div v-if="sending" class="flex justify-start">
              <div class="rounded-2xl rounded-bl-md border border-zinc-100 bg-white px-3.5 py-2.5 text-[12.5px] text-zinc-400">
                面试官思考中…
              </div>
            </div>
          </div>
        </div>

        <!-- 输入区（进行中） -->
        <div v-if="selected.status === 'ongoing'" class="shrink-0 border-t border-zinc-100 p-3">
          <div class="flex items-end gap-2">
            <n-input
              v-model:value="draft"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="输入你的回答…（支持语音转文字，专业名词转写误差 AI 会按上下文理解；Enter 发送）"
              @keydown.enter.exact.prevent="send"
            />
            <n-button size="small" :disabled="sending" @click="send('skip')">跳过此题</n-button>
            <n-button type="primary" :loading="sending" :disabled="!draft.trim()" @click="send()">发送</n-button>
            <n-button type="error" secondary :loading="finishing" @click="finishConfirm">结束面试</n-button>
          </div>
        </div>

        <!-- 分析报告（已结束） -->
        <div
          v-if="selected.status === 'finished' && viewMode === 'analysis'"
          class="min-h-0 flex-1 overflow-y-auto px-4 py-4"
        >
          <template v-if="selected.analysis">
            <div class="flex items-center gap-3">
              <span
                class="text-[36px] font-bold leading-none"
                :class="
                  selected.overall_score >= 75
                    ? 'text-emerald-600'
                    : selected.overall_score >= 60
                      ? 'text-amber-600'
                      : 'text-rose-600'
                "
              >{{ selected.overall_score }}</span>
              <span class="text-[12px] text-zinc-400">/ 100</span>
              <p class="min-w-0 flex-1 text-[12.5px] leading-relaxed text-zinc-600">
                {{ selected.analysis.overall.summary }}
              </p>
            </div>

            <div v-if="selected.analysis.weak_dimensions.length" class="mt-3 flex flex-wrap gap-1.5">
              <span
                v-for="(w, i) in selected.analysis.weak_dimensions"
                :key="i"
                class="rounded-lg bg-rose-50 px-2 py-1 text-[11.5px] text-rose-600"
              >薄弱：{{ w }}</span>
            </div>

            <!-- 逐题复盘 -->
            <h3 class="mb-2 mt-4 text-[13.5px] font-semibold text-zinc-800">逐题复盘（{{ selected.analysis.questions.length }}）</h3>
            <div class="flex flex-col gap-2.5">
              <div
                v-for="(q, i) in selected.analysis.questions"
                :key="i"
                class="rounded-xl border border-zinc-100 px-3.5 py-2.5"
              >
                <div class="flex flex-wrap items-center gap-2">
                  <span class="min-w-0 flex-1 text-[13px] font-medium text-zinc-800">{{ q.question }}</span>
                  <template v-if="q.skipped">
                    <span class="shrink-0 rounded-md bg-zinc-100 px-1.5 py-0.5 text-[10.5px] font-medium text-zinc-400">未回答 · 不计分</span>
                  </template>
                  <template v-else>
                    <span
                      v-for="[label, val] in [['结构', q.scores?.structure], ['深度', q.scores?.depth], ['表达', q.scores?.clarity]] as const"
                      :key="label"
                      class="shrink-0 rounded-md px-1.5 py-0.5 text-[10.5px] font-medium"
                      :class="val >= 4 ? 'bg-emerald-50 text-emerald-600' : val >= 3 ? 'bg-amber-50 text-amber-600' : 'bg-rose-50 text-rose-600'"
                    >{{ label }} {{ val }}/5</span>
                  </template>
                </div>
                <p v-if="q.my_answer" class="mt-1.5 text-[12.5px] leading-relaxed text-zinc-500">
                  <span class="text-zinc-400">我的回答：</span>{{ q.my_answer }}
                </p>
                <div v-if="q.good.length" class="mt-1.5 flex flex-col gap-0.5">
                  <p v-for="(g, j) in q.good" :key="'g' + j" class="text-[12.5px] leading-relaxed text-emerald-700">✓ {{ g }}</p>
                </div>
                <div v-if="q.bad.length" class="mt-0.5 flex flex-col gap-0.5">
                  <p v-for="(b, j) in q.bad" :key="'b' + j" class="text-[12.5px] leading-relaxed text-rose-600">✗ {{ b }}</p>
                </div>
                <div v-if="q.reference" class="mt-1.5 rounded-lg bg-emerald-50/70 px-2.5 py-1.5 text-[12.5px] leading-relaxed text-emerald-800">
                  {{ q.reference }}
                </div>
              </div>
            </div>

            <!-- 行动清单 -->
            <div v-if="selected.analysis.action_items.length" class="mt-4 rounded-2xl border border-indigo-100 bg-indigo-50/50 p-4">
              <h3 class="mb-2 text-[13.5px] font-semibold text-indigo-800">行动清单</h3>
              <ol class="flex flex-col gap-1.5">
                <li v-for="(a, i) in selected.analysis.action_items" :key="i" class="flex gap-2 text-[12.5px] leading-relaxed text-zinc-700">
                  <span class="shrink-0 font-semibold text-indigo-500">{{ i + 1 }}.</span>
                  {{ a }}
                </li>
              </ol>
            </div>

            <!-- 入题库 -->
            <div v-if="selected.analysis.questions_for_bank.length" class="mt-4">
              <h3 class="mb-2 text-[13.5px] font-semibold text-zinc-800">模拟中被问到的题</h3>
              <div class="flex flex-col gap-1.5">
                <div
                  v-for="(q, i) in selected.analysis.questions_for_bank"
                  :key="i"
                  class="flex items-center gap-2 rounded-xl border border-zinc-100 px-3 py-2"
                >
                  <span
                    class="shrink-0 rounded-md px-1.5 py-0.5 text-[10.5px] font-medium"
                    :class="DIFFICULTY_META[q.difficulty]?.class ?? 'bg-zinc-100 text-zinc-500'"
                  >{{ DIFFICULTY_META[q.difficulty]?.label ?? q.difficulty }}</span>
                  <span class="shrink-0 rounded-md bg-zinc-100 px-1.5 py-0.5 text-[10.5px] text-zinc-500">{{ q.dimension }}</span>
                  <span class="min-w-0 flex-1 truncate text-[12.5px] text-zinc-700">{{ q.content }}</span>
                  <n-button size="tiny" type="primary" quaternary :disabled="savedBank.has(i)" @click="saveToBank(i)">
                    {{ savedBank.has(i) ? '已入题库' : '存入题库' }}
                  </n-button>
                </div>
              </div>
            </div>
          </template>
          <div v-else class="grid place-items-center py-10 text-[12.5px] text-zinc-400">该会话还没有分析报告</div>
        </div>
      </template>

      <!-- 空状态 -->
      <div v-else-if="!loading" class="grid flex-1 place-items-center">
        <div class="text-center">
          <div class="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-indigo-50 text-indigo-500">
            <n-icon :component="SparklesOutline" :size="24" />
          </div>
          <div class="mt-3 text-[14px] font-semibold text-zinc-700">AI 模拟面试</div>
          <p class="mt-1 max-w-[380px] text-[12.5px] leading-relaxed text-zinc-400">
            选择目标轮次开始一场模拟面试：AI 面试官从题库随机选题、大类穿插推进，根据你的回答开放式追问；结束后生成逐题分析，对话与分析都会保存
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
