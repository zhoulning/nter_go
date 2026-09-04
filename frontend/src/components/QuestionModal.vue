<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  NButton,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NRadioGroup,
  NRadioButton,
  NRate,
  NSelect,
  useMessage,
} from 'naive-ui'
import { SparklesOutline, TrashOutline } from '@vicons/ionicons5'
import type { FormInst } from 'naive-ui'
import { api } from '../api'
import type { Opportunity, Question, QuestionPayload, QuestionSourceIn } from '../api'
import { ROUND_LABEL, DIFFICULTY_META, MASTERY_META } from '../types'
import { shortDate } from '../utils'

const props = defineProps<{
  show: boolean
  question: Question | null
  dimensions: string[]
  opportunities: Opportunity[]
}>()
const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
  (e: 'saved', q: Question, isNew: boolean): void
}>()

const message = useMessage()
const formRef = ref<FormInst | null>(null)
const saving = ref(false)
const aiGenerating = ref(false)
const isEdit = computed(() => !!props.question)

interface SourceRow {
  opportunity_id: number | null
  round_id: number | null
}

const emptyForm = () => ({
  content: '',
  dimension: '其他',
  difficulty: 'medium',
  source: 'manual',
  sources: [] as SourceRow[],
  resume_id: null as number | null,
  my_answer: '',
  answer_key: '',
  answer_spoken: '',
  self_rating: null as number | null,
  mastery: 'unknown',
})

const form = reactive(emptyForm())
const resumes = ref<{ id: number; name: string }[]>([])

watch(
  () => props.show,
  async (v) => {
    if (!v) return
    // 简历选项（轻量拉取）
    api
      .listResumes()
      .then((d) => (resumes.value = d.items.map((r) => ({ id: r.id, name: r.name }))))
      .catch(() => (resumes.value = []))

    if (props.question) {
      const q = props.question
      Object.assign(form, {
        content: q.content,
        dimension: q.dimension,
        difficulty: q.difficulty,
        source: q.source,
        sources:
          q.sources.length > 0
            ? q.sources.map((s) => ({ opportunity_id: s.opportunity_id, round_id: s.round_id }))
            : q.opportunity_id
              ? [{ opportunity_id: q.opportunity_id, round_id: null }]
              : [],
        resume_id: q.resume_id,
        my_answer: q.my_answer ?? '',
        answer_key: q.answer_key ?? '',
        answer_spoken: q.answer_spoken ?? '',
        self_rating: q.self_rating,
        mastery: q.mastery,
      })
    } else {
      Object.assign(form, emptyForm())
    }
  },
)

const rules = {
  content: { required: true, message: '请填写题干', trigger: 'blur' },
}

const dimensionOptions = computed(() => {
  const dims = new Set<string>(props.dimensions)
  if (form.dimension) dims.add(form.dimension)
  return [...dims].map((d) => ({ label: d, value: d }))
})
const masteryOptions = Object.entries(MASTERY_META).map(([value, m]) => ({
  label: m.label,
  value,
}))
const opportunityOptions = computed(() =>
  props.opportunities.map((o) => ({
    label: `${o.company} · ${o.position}`,
    value: o.id,
  })),
)
const resumeOptions = computed(() =>
  resumes.value.map((r) => ({ label: r.name, value: r.id })),
)

function roundOptionsFor(oppId: number | null) {
  if (!oppId) return []
  const opp = props.opportunities.find((o) => o.id === oppId)
  if (!opp) return []
  return opp.rounds
    .filter((r) => r.scheduled_at)
    .map((r) => ({
      label: `${ROUND_LABEL[r.round_type] ?? '面试'} · ${shortDate(r.scheduled_at)}`,
      value: r.id,
    }))
}

function addSource() {
  form.sources.push({ opportunity_id: null, round_id: null })
}

function onSourceOppChange(row: SourceRow) {
  row.round_id = null
}

// ---- AI 生成口述版答案 ----
async function genAnswer() {
  const content = form.content.trim()
  if (!content) {
    message.warning('请先填写题干，AI 才知道要答什么')
    return
  }
  aiGenerating.value = true
  try {
    const companies = form.sources
      .map((s) => props.opportunities.find((o) => o.id === s.opportunity_id)?.company)
      .filter((c): c is string => !!c)
    const res = await api.generateAnswer({
      question_id: isEdit.value ? props.question!.id : undefined,
      content,
      dimension: form.dimension,
      companies,
    })
    if (res.answer_spoken) form.answer_spoken = res.answer_spoken
    message.success('口述版答案已生成，可继续编辑')
  } catch (e) {
    message.error((e as Error).message || 'AI 生成失败', { duration: 6000 })
  } finally {
    aiGenerating.value = false
  }
}

async function submit() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    const sources: QuestionSourceIn[] = form.sources
      .filter((s) => s.opportunity_id != null)
      .map((s) => ({ opportunity_id: s.opportunity_id!, round_id: s.round_id }))
    const payload: QuestionPayload = {
      content: form.content.trim(),
      dimension: form.dimension,
      difficulty: form.difficulty,
      source: form.source,
      opportunity_id: sources[0]?.opportunity_id ?? null,
      resume_id: form.resume_id,
      sources,
      my_answer: form.my_answer.trim() || null,
      answer_key: form.answer_key.trim() || null,
      answer_spoken: form.answer_spoken.trim() || null,
      self_rating: form.self_rating,
      mastery: form.mastery,
    }
    const saved = isEdit.value
      ? await api.updateQuestion(props.question!.id, payload)
      : await api.createQuestion(payload)
    emit('saved', saved, !isEdit.value)
    emit('update:show', false)
  } catch (e) {
    message.error((e as Error).message || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <n-modal :show="show" transform-origin="center" @update:show="emit('update:show', $event)">
    <div class="modal-card">
      <div class="mb-5">
        <h2 class="text-[16px] font-bold text-zinc-900">
          {{ isEdit ? '编辑题目' : '新增题目' }}
        </h2>
        <p class="mt-0.5 text-[12px] text-zinc-400">
          真实面试遇到的题建议标低自评分，会自动进入错题本
        </p>
      </div>

      <n-form ref="formRef" :model="form" :rules="rules" label-placement="top" size="small" :show-require-mark="false">
        <n-form-item label="题干" path="content">
          <n-input
            v-model:value="form.content"
            type="textarea"
            :rows="3"
            placeholder="面试官原话或题目内容"
          />
        </n-form-item>

        <!-- 题目来源：哪家公司的哪场面试，可多个 -->
        <n-form-item label="题目来源（哪家公司的哪场面试，可多个）">
          <div class="w-full">
            <div
              v-for="(row, i) in form.sources"
              :key="i"
              class="mb-2 flex items-center gap-2"
            >
              <n-select
                v-model:value="row.opportunity_id"
                filterable
                :options="opportunityOptions"
                placeholder="选择公司 / 岗位"
                class="flex-1"
                @update:value="onSourceOppChange(row)"
              />
              <n-select
                v-model:value="row.round_id"
                :options="roundOptionsFor(row.opportunity_id)"
                placeholder="轮次（选填）"
                clearable
                :disabled="!row.opportunity_id"
                style="width: 190px"
              />
              <n-button
                quaternary
                type="error"
                size="small"
                @click="form.sources.splice(i, 1)"
              >
                <n-icon :component="TrashOutline" :size="15" />
              </n-button>
            </div>
            <n-button dashed size="small" class="w-full" @click="addSource">
              + 添加来源
            </n-button>
          </div>
        </n-form-item>

        <div class="grid grid-cols-2 gap-x-4">
          <n-form-item label="考察维度" path="dimension">
            <n-select
              v-model:value="form.dimension"
              filterable
              tag
              creatable
              :options="dimensionOptions"
              placeholder="选择或输入新维度"
            />
          </n-form-item>
          <n-form-item label="关联简历（因哪版简历被问到）" path="resume_id">
            <n-select
              v-model:value="form.resume_id"
              filterable
              clearable
              :options="resumeOptions"
              placeholder="选填"
            />
          </n-form-item>
          <n-form-item label="难度" path="difficulty">
            <n-radio-group v-model:value="form.difficulty">
              <n-radio-button value="easy">简单</n-radio-button>
              <n-radio-button value="medium">中等</n-radio-button>
              <n-radio-button value="hard">困难</n-radio-button>
            </n-radio-group>
          </n-form-item>
          <n-form-item label="来源类型" path="source">
            <n-radio-group v-model:value="form.source">
              <n-radio-button value="manual">手动</n-radio-button>
              <n-radio-button value="real">真实面试</n-radio-button>
              <n-radio-button value="predicted">AI 预测</n-radio-button>
            </n-radio-group>
          </n-form-item>
          <n-form-item label="掌握状态" path="mastery">
            <n-select v-model:value="form.mastery" :options="masteryOptions" />
          </n-form-item>
          <n-form-item label="自评分（1-5，越低越薄弱）" path="self_rating">
            <n-rate v-model:value="form.self_rating" clearable />
          </n-form-item>
        </div>

        <n-form-item label="我的回答要点" path="my_answer">
          <n-input
            v-model:value="form.my_answer"
            type="textarea"
            :rows="3"
            placeholder="当时我是怎么答的（便于复盘对照）"
          />
        </n-form-item>

        <!-- AI 参考答案 -->
        <div class="mb-1 mt-1 flex items-center justify-between rounded-xl bg-indigo-50/60 px-3 py-2">
          <span class="text-[12px] font-semibold text-indigo-600">AI 参考答案</span>
          <n-button
            size="tiny"
            type="primary"
            secondary
            :loading="aiGenerating"
            @click="genAnswer"
          >
            <template #icon>
              <n-icon :component="SparklesOutline" :size="13" />
            </template>
            AI 生成口述版答案
          </n-button>
        </div>
        <n-form-item label="口述版（面试现场怎么说）" path="answer_spoken">
          <n-input
            v-model:value="form.answer_spoken"
            type="textarea"
            :rows="4"
            placeholder="第一人称自然口语；点上方按钮由 AI 生成，可编辑"
          />
        </n-form-item>
        <n-form-item label="参考答案要点 / 得分点" path="answer_key">
          <n-input
            v-model:value="form.answer_key"
            type="textarea"
            :rows="2"
            placeholder="面试后整理的标准答案 / 得分点"
          />
        </n-form-item>
      </n-form>

      <div class="mt-2 flex justify-end gap-2.5">
        <n-button quaternary @click="emit('update:show', false)">取消</n-button>
        <n-button type="primary" class="!px-5" :loading="saving" @click="submit">
          {{ isEdit ? '保存' : '添加' }}
        </n-button>
      </div>
    </div>
  </n-modal>
</template>

<style scoped>
.modal-card {
  width: 620px;
  max-width: calc(100vw - 48px);
  max-height: calc(100vh - 48px);
  overflow-y: auto;
  background: #fff;
  border-radius: 16px;
  padding: 24px;
  box-shadow:
    0 20px 50px -12px rgba(16, 24, 40, 0.25),
    0 0 0 1px rgba(16, 24, 40, 0.04);
}
</style>
