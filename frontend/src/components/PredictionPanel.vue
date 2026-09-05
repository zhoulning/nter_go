<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useDialog, useMessage } from 'naive-ui'
import { SparklesOutline } from '@vicons/ionicons5'
import { api } from '../api'
import type { Opportunity, PredictedQuestion, PredictionInfo } from '../types'
import { DIFFICULTY_META, MOCK_ROUND_LABEL, PREDICT_GROUPS } from '../types'
import MarkdownView from './MarkdownView.vue'

const props = defineProps<{ opportunity: Opportunity }>()

const message = useMessage()
const dialog = useDialog()

const predictions = ref<PredictionInfo[]>([])
const loading = ref(true)
const generating = ref(false)
const activeRound = ref<string | null>(null)
const selectedRoundType = ref('first')
const selfTest = ref(false)
const revealed = ref<Set<string>>(new Set())
// 题库已有题干（去重提示）与本次会话已录入题干；正在录入的题干用于按钮 loading
const bankContents = ref<Set<string>>(new Set())
const addedContents = ref<Set<string>>(new Set())
const addingKey = ref<string | null>(null)

// 可出题单的轮次：真实轮次 + 模拟面试专题
const ROUND_OPTIONS: Record<string, string> = {
  written: '笔试',
  first: '一面',
  second: '二面',
  third: '三面',
  comprehensive: '综合面',
  hr: 'HR 面',
  project: '项目经历面',
  stress: '压力面',
  other: '其他',
}

async function load() {
  loading.value = true
  try {
    const data = await api.listPredictions(props.opportunity.id)
    predictions.value = data.items
    if (data.items.length && !data.items.some((p) => p.round_type === activeRound.value)) {
      activeRound.value = data.items[0].round_type
    }
  } catch (e) {
    message.error((e as Error).message || '加载失败')
  } finally {
    loading.value = false
  }
}
onMounted(() => {
  load()
  // 拉题库做「已在题库」判断（同题干不重复录入）
  api
    .listQuestions()
    .then((d) => {
      bankContents.value = new Set(d.items.map((q) => q.content.trim()))
    })
    .catch(() => {})
})

const active = computed(() => predictions.value.find((p) => p.round_type === activeRound.value) ?? null)

const grouped = computed(() => {
  const qs = active.value?.report?.questions ?? []
  return PREDICT_GROUPS.map((g) => ({ group: g, questions: qs.filter((q) => q.group === g) })).filter(
    (g) => g.questions.length,
  )
})

async function generate() {
  generating.value = true
  try {
    const saved = await api.generatePrediction(props.opportunity.id, selectedRoundType.value)
    const idx = predictions.value.findIndex((p) => p.round_type === saved.round_type)
    if (idx >= 0) predictions.value[idx] = saved
    else predictions.value.push(saved)
    activeRound.value = saved.round_type
    revealed.value.clear()
    message.success(`「${MOCK_ROUND_LABEL[saved.round_type] ?? '面试'}」题单已生成（${saved.question_count} 题）`)
  } catch (e) {
    message.error((e as Error).message || '生成失败', { duration: 8000 })
  } finally {
    generating.value = false
  }
}

function regenerate() {
  if (!active.value) return
  dialog.warning({
    title: '重新生成题单',
    content: '当前题单将被新题单覆盖，确定继续？',
    positiveText: '重新生成',
    negativeText: '取消',
    onPositiveClick: () => {
      selectedRoundType.value = active.value!.round_type
      return generate()
    },
  })
}

function removePrediction() {
  if (!active.value) return
  const target = active.value
  dialog.warning({
    title: '删除题单',
    content: `确定删除「${MOCK_ROUND_LABEL[target.round_type] ?? '面试'}」的预测题单吗？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.deletePrediction(props.opportunity.id, target.id)
        predictions.value = predictions.value.filter((p) => p.id !== target.id)
        activeRound.value = predictions.value[0]?.round_type ?? null
        message.success('已删除')
      } catch (e) {
        message.error((e as Error).message || '删除失败')
      }
    },
  })
}

function toggleReveal(key: string) {
  const next = new Set(revealed.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  revealed.value = next
}

function inBank(q: PredictedQuestion): boolean {
  const key = q.q.trim()
  return bankContents.value.has(key) || addedContents.value.has(key)
}

/** 把预测题录入题库：来源「题目预测」；答案与要点一并带入，缺答案时走题库统一入口补生成 */
async function addToBank(q: PredictedQuestion) {
  const key = q.q.trim()
  addingKey.value = key
  try {
    const saved = await api.createQuestion({
      content: q.q,
      dimension: q.dimension,
      difficulty: q.difficulty,
      source: 'predicted',
      opportunity_id: props.opportunity.id,
      resume_id: props.opportunity.resume_id ?? null,
      sources: [{ opportunity_id: props.opportunity.id, round_id: null }],
      my_answer: null,
      answer_key: q.key_points || null,
      answer_spoken: q.answer?.trim() || null,
      self_rating: null,
      mastery: 'unknown',
    })
    addedContents.value = new Set([...addedContents.value, key])
    if (q.answer?.trim()) {
      message.success('已录入题库（来源：题目预测），参考答案已一并带入')
    } else {
      try {
        await api.generateAnswer({ question_id: saved.id })
        message.success('已录入题库（来源：题目预测），AI 答案已生成')
      } catch (err) {
        message.warning(`已录入题库，但 AI 答案生成失败：${(err as Error).message || '未知错误'}`, {
          duration: 8000,
        })
      }
    }
  } catch (e) {
    message.error((e as Error).message || '录入失败')
  } finally {
    addingKey.value = null
  }
}
</script>

<template>
  <div class="max-h-[calc(100vh-180px)] overflow-y-auto pb-8 max-md:max-h-[calc(100dvh-150px)]">
    <!-- 生成中 -->
    <div v-if="generating" class="grid place-items-center rounded-2xl border border-dashed border-indigo-200 bg-white py-16">
      <div class="text-center">
        <n-spin size="28" />
        <div class="mt-3 text-[14px] font-semibold text-zinc-700">正在生成「{{ MOCK_ROUND_LABEL[selectedRoundType] ?? '面试' }}」预测题单…</div>
        <p class="mt-1 text-[12.5px] text-zinc-400">AI 正在结合 JD、简历、匹配度缺口与题库弱项出题，并按题库同一标准逐题生成完整答案，大约需要两三分钟</p>
      </div>
    </div>

    <!-- 无任何题单 -->
    <div v-else-if="!predictions.length && !loading" class="grid place-items-center rounded-2xl border border-dashed border-zinc-200 bg-white py-16">
      <div class="w-[420px] text-center max-md:w-full max-md:px-2">
        <div class="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-indigo-50 text-indigo-500">
          <n-icon :component="SparklesOutline" :size="24" />
        </div>
        <div class="mt-3 text-[14px] font-semibold text-zinc-700">AI 题目预测</div>
        <p class="mt-1 text-[12.5px] leading-relaxed text-zinc-400">
          基于 JD、关联简历、匹配度报告缺口与题库弱项，按目标轮次生成分维度题单（附完整参考答案、考察意图与答题要点，可一键录入题库）
        </p>
        <div class="mt-4 flex items-center justify-center gap-2">
          <select
            v-model="selectedRoundType"
            class="rounded-lg border border-zinc-200 bg-white px-2.5 py-1.5 text-[13px] text-zinc-700 outline-none"
          >
            <option v-for="(label, key) in ROUND_OPTIONS" :key="key" :value="key">
              {{ label }}
            </option>
          </select>
          <n-button type="primary" :loading="generating" @click="generate">生成预测题单</n-button>
        </div>
      </div>
    </div>

    <!-- 题单内容 -->
    <template v-else>
      <!-- 工具栏 -->
      <div class="mb-3 flex flex-wrap items-center gap-2">
        <button
          v-for="p in predictions"
          :key="p.id"
          class="rounded-lg border px-2.5 py-1.5 text-[12.5px] font-medium transition-colors"
          :class="
            activeRound === p.round_type
              ? 'border-indigo-200 bg-indigo-50 text-indigo-600'
              : 'border-zinc-200 bg-white text-zinc-600 hover:border-zinc-300'
          "
          @click="activeRound = p.round_type"
        >
          {{ MOCK_ROUND_LABEL[p.round_type] ?? p.round_type }}
          <span class="ml-1 text-[11px] text-zinc-400">{{ p.question_count }} 题</span>
        </button>
        <div class="ml-auto flex items-center gap-2">
          <label class="flex cursor-pointer select-none items-center gap-1.5 text-[12.5px] text-zinc-600">
            <n-switch v-model:value="selfTest" size="small" />
            自测模式（隐藏答案）
          </label>
          <n-button size="small" @click="regenerate">重新生成</n-button>
          <n-button size="small" type="error" quaternary @click="removePrediction">删除</n-button>
          <select
            v-model="selectedRoundType"
            class="rounded-lg border border-zinc-200 bg-white px-2 py-1.5 text-[12.5px] text-zinc-700 outline-none"
          >
            <option v-for="(label, key) in ROUND_OPTIONS" :key="key" :value="key">
              新题单：{{ label }}
            </option>
          </select>
          <n-button size="small" type="primary" secondary @click="generate">生成新题单</n-button>
        </div>
      </div>

      <template v-if="active?.report">
        <!-- 整体建议 + 弱项聚焦 -->
        <div class="mb-3 rounded-2xl border border-indigo-100 bg-indigo-50/50 p-4">
          <div class="flex items-start gap-2">
            <n-icon :component="SparklesOutline" :size="15" class="mt-[3px] shrink-0 text-indigo-500" />
            <div class="min-w-0">
              <p v-if="active.report.overall_advice" class="text-[12.5px] leading-relaxed text-zinc-700">
                {{ active.report.overall_advice }}
              </p>
              <div v-if="active.report.weak_focus.length" class="mt-2 flex flex-wrap gap-1.5">
                <span
                  v-for="(w, i) in active.report.weak_focus"
                  :key="i"
                  class="rounded-lg bg-violet-50 px-2 py-1 text-[11.5px] text-violet-600"
                >弱项加权：{{ w }}</span>
              </div>
              <p v-if="active.report.answer_note" class="mt-2 text-[11.5px] leading-relaxed text-amber-600">
                {{ active.report.answer_note }}
              </p>
            </div>
          </div>
        </div>

        <!-- 分组题单 -->
        <div class="flex flex-col gap-4">
          <div v-for="g in grouped" :key="g.group">
            <h3 class="mb-2 text-[13.5px] font-semibold text-zinc-800">
              {{ g.group }}
              <span class="ml-1 text-[11.5px] font-normal text-zinc-400">{{ g.questions.length }} 题</span>
            </h3>
            <div class="flex flex-col gap-2">
              <div
                v-for="(q, i) in g.questions"
                :key="i"
                class="rounded-xl border border-zinc-100 bg-white px-3.5 py-2.5"
              >
                <div class="flex flex-wrap items-center gap-2">
                  <span
                    class="shrink-0 rounded-md px-1.5 py-0.5 text-[10.5px] font-medium"
                    :class="DIFFICULTY_META[q.difficulty]?.class ?? 'bg-zinc-100 text-zinc-500'"
                  >{{ DIFFICULTY_META[q.difficulty]?.label ?? q.difficulty }}</span>
                  <span class="shrink-0 rounded-md bg-zinc-100 px-1.5 py-0.5 text-[10.5px] text-zinc-500">{{ q.dimension }}</span>
                  <span class="min-w-0 flex-1 text-[13px] font-medium text-zinc-800">{{ q.q }}</span>
                  <n-button
                    v-if="!inBank(q)"
                    size="tiny"
                    type="primary"
                    secondary
                    class="shrink-0"
                    :loading="addingKey === q.q.trim()"
                    @click="addToBank(q)"
                  >录入题库</n-button>
                  <span
                    v-else
                    class="shrink-0 rounded-md bg-emerald-50 px-1.5 py-0.5 text-[10.5px] text-emerald-600"
                  >已在题库</span>
                  <button
                    v-if="selfTest && (q.intent || q.key_points || q.answer)"
                    class="shrink-0 text-[11.5px] text-indigo-500 hover:underline"
                    @click="toggleReveal(active!.id + ':' + g.group + ':' + i)"
                  >
                    {{ revealed.has(active!.id + ':' + g.group + ':' + i) ? '收起答案' : '看答案' }}
                  </button>
                </div>
                <template v-if="!selfTest || revealed.has(active!.id + ':' + g.group + ':' + i)">
                  <p v-if="q.intent" class="mt-1.5 text-[12.5px] leading-relaxed text-zinc-500">
                    <span class="text-zinc-400">考察意图：</span>{{ q.intent }}
                  </p>
                  <div v-if="q.key_points" class="mt-1 rounded-lg bg-emerald-50/70 px-2.5 py-1.5 text-[12.5px] leading-relaxed text-emerald-800">
                    {{ q.key_points }}
                  </div>
                  <div v-if="q.answer" class="mt-1.5 rounded-lg border border-indigo-100 bg-indigo-50/40 px-2.5 py-2">
                    <div class="mb-0.5 flex items-center gap-1 text-[11.5px] font-semibold text-indigo-500">
                      <n-icon :component="SparklesOutline" :size="12" />
                      参考答案（口述版）
                    </div>
                    <MarkdownView :source="q.answer" />
                  </div>
                </template>
              </div>
            </div>
          </div>
        </div>

        <p class="mt-3 text-[11px] text-zinc-400">
          生成于 {{ new Date(active.created_at).toLocaleString() }} · {{ active.model }}
        </p>
      </template>
    </template>
  </div>
</template>
